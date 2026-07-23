"""Validated scene descriptor for the GPU Gaussian viewer.

The desktop control plane validates assets once.  The WebGL component reads
the original Graphdeco PLY itself and performs activation, projection, SH
evaluation, sorting and blending on the GPU/JavaScript side; Python is never
in the frame loop.
"""

from __future__ import annotations

from dataclasses import dataclass
import math
from pathlib import Path
import re
from typing import Any

import numpy as np

from packages.exportkit import PlyFormatError, read_gaussian_ply_document, read_pointcloud_ply
from packages.scene_bundle import GaussianTensors, PointCloudTensors, load_scene_bundle


# SceneBundle stores OpenCV-style axes (x right, y down, z forward).  The
# renderer exposes a conventional right-handed Y-up world.  This is the only
# root transform used by the Viewer and is applied uniformly to Gaussians,
# points and camera geometry.
SCENE_ROOT_TRANSFORM = np.asarray(
    ((1.0, 0.0, 0.0, 0.0),
     (0.0, -1.0, 0.0, 0.0),
     (0.0, 0.0, -1.0, 0.0),
     (0.0, 0.0, 0.0, 1.0)),
    dtype=np.float64,
)


@dataclass(frozen=True, slots=True)
class ViewerScene:
    bundle_path: Path
    gaussian_path: Path
    pointcloud_path: Path | None
    pointcloud_bytes: bytes | None
    gaussian_count: int
    camera_count: int
    sh_degree: int
    bounds_min: tuple[float, float, float]
    bounds_max: tuple[float, float, float]
    camera_positions: tuple[tuple[float, float, float], ...]
    cameras: tuple[dict[str, Any], ...]
    initial_camera_position: tuple[float, float, float] | None
    initial_camera_forward: tuple[float, float, float] | None
    initial_camera_up: tuple[float, float, float] | None
    initial_focus_distance: float | None
    scene_root_transform: tuple[tuple[float, float, float, float], ...]
    canonical_world_up: tuple[float, float, float]


_PLY_SCALAR_DTYPES = {
    "char": "i1", "int8": "i1", "uchar": "u1", "uint8": "u1",
    "short": "<i2", "int16": "<i2", "ushort": "<u2", "uint16": "<u2",
    "int": "<i4", "int32": "<i4", "uint": "<u4", "uint32": "<u4",
    "float": "<f4", "float32": "<f4", "double": "<f8", "float64": "<f8",
}


def _read_compatible_pointcloud(path: Path) -> PointCloudTensors:
    """Read ExportKit or a scalar binary little-endian point PLY.

    Compatibility PLYs are accepted here rather than in ExportKit because
    they do not carry the interchange-format comments required by that API.
    """
    try:
        return read_pointcloud_ply(path)
    except PlyFormatError:
        payload = path.read_bytes()
        match = re.search(br"end_header\r?\n", payload[: 1024 * 1024])
        if match is None:
            raise ValueError("unsupported standard point-cloud PLY layout")
        try:
            lines = payload[:match.end()].decode("ascii").splitlines()
        except UnicodeDecodeError as exc:
            raise ValueError("point-cloud PLY header must be ASCII") from exc
        if not lines or lines[0] != "ply" or "format binary_little_endian 1.0" not in lines:
            raise ValueError("only binary little-endian point-cloud PLY is supported")
        vertex_count: int | None = None
        properties: list[tuple[str, str]] = []
        in_vertices = False
        for line in lines:
            fields = line.split()
            if len(fields) == 3 and fields[:2] == ["element", "vertex"]:
                vertex_count = int(fields[2]); in_vertices = True
            elif fields[:1] == ["element"]:
                in_vertices = False
            elif in_vertices and fields[:1] == ["property"]:
                if len(fields) != 3 or fields[1] not in _PLY_SCALAR_DTYPES:
                    raise ValueError("unsupported point-cloud PLY vertex property")
                properties.append((fields[2], _PLY_SCALAR_DTYPES[fields[1]]))
        names = [name for name, _ in properties]
        if vertex_count is None or vertex_count <= 0 or not all(name in names for name in ("x", "y", "z")):
            raise ValueError("point-cloud PLY is missing scalar xyz vertices")
        dtype = np.dtype(properties)
        expected = vertex_count * dtype.itemsize
        body = payload[match.end():]
        if len(body) != expected:
            raise ValueError("point-cloud PLY payload size does not match its header")
        vertices = np.frombuffer(body, dtype=dtype, count=vertex_count)
        positions = np.column_stack([vertices[name] for name in ("x", "y", "z")]).astype(np.float32)
        colors = None
        if all(name in names for name in ("red", "green", "blue")):
            colors = np.column_stack([vertices[name] for name in ("red", "green", "blue")]).astype(np.uint8)
        return PointCloudTensors(positions=positions, colors_rgb=colors)


def _canonical_pointcloud_bytes(pointcloud: PointCloudTensors, source_to_scene: np.ndarray) -> bytes:
    """Return a viewer-only PLY in the SceneBundle's stored world.

    Reconstruction point clouds are source-world artifacts, whereas trained
    Gaussians and cameras are already stored in normalized SceneBundle world.
    Applying the manifest transform once at this boundary prevents the Viewer
    from maintaining independent transforms for its render layers.
    """
    homogeneous = np.column_stack(
        (pointcloud.positions.astype(np.float64), np.ones(len(pointcloud.positions), dtype=np.float64))
    )
    positions = (homogeneous @ source_to_scene.T)[:, :3].astype("<f4")
    has_color = pointcloud.colors_rgb is not None
    fields: list[tuple[str, str]] = [(name, "<f4") for name in ("x", "y", "z")]
    if has_color:
        fields.extend((name, "u1") for name in ("red", "green", "blue"))
    vertices = np.empty(len(positions), dtype=np.dtype(fields))
    for index, name in enumerate(("x", "y", "z")):
        vertices[name] = positions[:, index]
    if has_color:
        assert pointcloud.colors_rgb is not None
        for index, name in enumerate(("red", "green", "blue")):
            vertices[name] = pointcloud.colors_rgb[:, index]
    header = [
        "ply", "format binary_little_endian 1.0",
        "comment gaussian_factory_viewer_space scene_bundle_world",
        f"element vertex {len(vertices)}",
        "property float x", "property float y", "property float z",
    ]
    if has_color:
        header.extend(("property uchar red", "property uchar green", "property uchar blue"))
    header.append("end_header")
    return ("\n".join(header) + "\n").encode("ascii") + vertices.tobytes(order="C")


def activate_gaussians(
    log_scales: np.ndarray, opacity_logits: np.ndarray, quats_wxyz: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Reference activation used by tests and metadata validation.

    Rendering performs the same operations in GLSL.  Keeping this small
    reference makes the graphdeco parameter contract independently testable.
    """
    scales = np.exp(log_scales.astype(np.float64)).astype(np.float32)
    logits = opacity_logits.astype(np.float64)
    opacity = np.where(
        logits >= 0,
        1.0 / (1.0 + np.exp(-logits)),
        np.exp(logits) / (1.0 + np.exp(logits)),
    ).astype(np.float32)
    quats = quats_wxyz.astype(np.float64)
    norms = np.linalg.norm(quats, axis=1, keepdims=True)
    if np.any(norms <= 1e-12):
        raise ValueError("Gaussian quaternion has zero length")
    normalized = (quats / norms).astype(np.float32)
    return scales, opacity, normalized


def load_viewer_scene(
    bundle_path: str | Path,
    gaussian_path: str | Path,
    pointcloud_path: str | Path | None = None,
    camera_timeline: list[dict[str, Any]] | None = None,
) -> ViewerScene:
    """Validate and describe a SceneBundle + graphdeco-gs-v1 PLY pair."""
    bundle_file = Path(bundle_path).resolve()
    gaussian_file = Path(gaussian_path).resolve()
    bundle = load_scene_bundle(bundle_file)
    try:
        gaussians = read_gaussian_ply_document(gaussian_file).gaussians
    except PlyFormatError:
        # Standard Graphdeco files do not carry ExportKit's semantic comments.
        # gsply is the pinned desktop compatibility reader and exposes their
        # raw log-scale/logit/SH layout without silently activating values.
        try:
            import gsply
        except ImportError as exc:
            raise ValueError("standard Graphdeco PLY loading requires the desktop gsply dependency") from exc
        loaded = gsply.plyread(gaussian_file)
        if not (loaded.is_scales_ply and loaded.is_opacities_ply and loaded.is_sh0_sh):
            raise ValueError("Gaussian PLY is not in raw Graphdeco scale/opacity/SH encoding")
        sh_coeffs = np.concatenate((loaded.sh0[:, None, :], loaded.shN), axis=1).astype(np.float32)
        quats = loaded.quats.astype(np.float32)
        quats /= np.linalg.norm(quats.astype(np.float64), axis=1, keepdims=True).astype(np.float32)
        gaussians = GaussianTensors(
            means=loaded.means.astype(np.float32),
            log_scales=loaded.scales.astype(np.float32),
            quats_wxyz=quats,
            opacity_logits=loaded.opacities.astype(np.float32).reshape(-1, 1),
            sh_coeffs=sh_coeffs,
        )
    if bundle.gaussians is None:
        raise ValueError("SceneBundle has no Gaussian tensors")
    if len(bundle.gaussians.means) != len(gaussians.means):
        raise ValueError("SceneBundle and Gaussian PLY counts do not match")
    if not np.allclose(bundle.gaussians.means, gaussians.means, rtol=1e-6, atol=1e-7):
        raise ValueError("SceneBundle and Gaussian PLY positions do not share one canonical world")
    # Exercise all semantic activations during load; invalid values fail before
    # the WebEngine receives the scene.
    activate_gaussians(gaussians.log_scales, gaussians.opacity_logits, gaussians.quats_wxyz)

    source_to_scene = np.asarray(
        bundle.manifest.normalization_transform.source_to_scene, dtype=np.float64
    )
    points_file = Path(pointcloud_path).resolve() if pointcloud_path else None
    pointcloud_bytes = None
    if points_file is not None:
        pointcloud_bytes = _canonical_pointcloud_bytes(
            _read_compatible_pointcloud(points_file), source_to_scene
        )

    camera_records: tuple[dict[str, Any], ...] = ()
    if camera_timeline:
        joined: list[dict[str, Any]] = []
        for entry in camera_timeline:
            if entry.get("registration_status") != "registered":
                continue
            camera = entry.get("camera")
            if not isinstance(camera, dict):
                raise ValueError("registered timeline frame is missing a real camera")
            cam2world = np.asarray(camera.get("cam2world"), dtype=np.float64)
            intrinsics = np.asarray(camera.get("intrinsics"), dtype=np.float64)
            width, height = int(camera.get("width", 0)), int(camera.get("height", 0))
            if cam2world.shape != (4, 4) or intrinsics.shape != (3, 3):
                raise ValueError("timeline camera matrix shape is invalid")
            if not np.isfinite(cam2world).all() or not np.isfinite(intrinsics).all() or width <= 0 or height <= 0:
                raise ValueError("timeline camera has invalid pose, intrinsics, or image size")
            joined.append({
                **camera,
                "source_frame_index": int(entry["source_frame_index"]),
                "selected_order": int(entry["selected_order"]),
                "colmap_image_id": int(entry["colmap_image_id"]),
            })
        joined.sort(key=lambda item: item["selected_order"])
        if joined:
            if bundle.cameras is None or len(joined) != len(bundle.cameras.camtoworlds):
                raise ValueError("registered COLMAP timeline does not match SceneBundle camera count")
            normalized: list[dict[str, Any]] = []
            for index, item in enumerate(joined):
                cam2world = bundle.cameras.camtoworlds[index].astype(np.float64)
                intrinsics = bundle.cameras.intrinsics[index].astype(np.float64)
                width, height = (int(value) for value in bundle.cameras.image_sizes[index])
                normalized.append({
                    **item,
                    "colmap_cam2world": item["cam2world"],
                    "colmap_intrinsics": item["intrinsics"],
                    "cam2world": cam2world.tolist(),
                    "intrinsics": intrinsics.tolist(),
                    "width": width,
                    "height": height,
                    "aspect_ratio": width / height,
                    "fov_y_degrees": math.degrees(2.0 * math.atan(height / (2.0 * float(intrinsics[1, 1])))),
                    "coordinate_space": "scene_normalized",
                })
            camera_records = tuple(normalized)

    cameras: tuple[tuple[float, float, float], ...] = ()
    initial_position = initial_forward = initial_up = None
    initial_focus = None
    if camera_records:
        matrices = np.asarray([item["cam2world"] for item in camera_records], dtype=np.float64)
        cameras = tuple(tuple(float(value) for value in row) for row in matrices[:, :3, 3])
        first = matrices[0]
    elif bundle.cameras is not None:
        cameras = tuple(
            tuple(float(value) for value in row)
            for row in bundle.cameras.camtoworlds[:, :3, 3]
        )
        first = bundle.cameras.camtoworlds[0]
    else:
        first = None
    if first is not None:
        eye = first[:3, 3].astype(np.float64)
        forward = first[:3, 2].astype(np.float64)
        forward /= np.linalg.norm(forward)
        up = -first[:3, 1].astype(np.float64)
        up /= np.linalg.norm(up)
        depths = (gaussians.means.astype(np.float64) - eye) @ forward
        positive_depths = depths[depths > 1e-4]
        focus = float(np.median(positive_depths)) if len(positive_depths) else 1.0
        initial_position = tuple(float(value) for value in eye)
        initial_forward = tuple(float(value) for value in forward)
        initial_up = tuple(float(value) for value in up)
        initial_focus = max(focus, 0.01)
    # A tiny number of low-opacity training outliers can otherwise shrink the
    # useful reconstruction to a speck on first open.
    low = np.quantile(gaussians.means, 0.01, axis=0)
    high = np.quantile(gaussians.means, 0.99, axis=0)
    return ViewerScene(
        bundle_path=bundle_file,
        gaussian_path=gaussian_file,
        pointcloud_path=points_file,
        pointcloud_bytes=pointcloud_bytes,
        gaussian_count=int(len(gaussians.means)),
        camera_count=len(cameras),
        sh_degree=gaussians.sh_degree,
        bounds_min=tuple(float(value) for value in low),
        bounds_max=tuple(float(value) for value in high),
        camera_positions=cameras,
        cameras=camera_records,
        initial_camera_position=initial_position,
        initial_camera_forward=initial_forward,
        initial_camera_up=initial_up,
        initial_focus_distance=initial_focus,
        scene_root_transform=tuple(
            tuple(float(value) for value in row) for row in SCENE_ROOT_TRANSFORM
        ),
        canonical_world_up=(0.0, 1.0, 0.0),
    )
