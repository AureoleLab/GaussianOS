"""Validated scene descriptor for the GPU Gaussian viewer.

The desktop control plane validates assets once.  The WebGL component reads
the original Graphdeco PLY itself and performs activation, projection, SH
evaluation, sorting and blending on the GPU/JavaScript side; Python is never
in the frame loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from packages.exportkit import PlyFormatError, read_gaussian_ply_document, read_pointcloud_ply
from packages.scene_bundle import GaussianTensors, load_scene_bundle


@dataclass(frozen=True, slots=True)
class ViewerScene:
    bundle_path: Path
    gaussian_path: Path
    pointcloud_path: Path | None
    gaussian_count: int
    camera_count: int
    sh_degree: int
    bounds_min: tuple[float, float, float]
    bounds_max: tuple[float, float, float]
    camera_positions: tuple[tuple[float, float, float], ...]
    initial_camera_position: tuple[float, float, float] | None
    initial_camera_forward: tuple[float, float, float] | None
    initial_camera_up: tuple[float, float, float] | None
    initial_focus_distance: float | None


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
    # Exercise all semantic activations during load; invalid values fail before
    # the WebEngine receives the scene.
    activate_gaussians(gaussians.log_scales, gaussians.opacity_logits, gaussians.quats_wxyz)

    points_file = Path(pointcloud_path).resolve() if pointcloud_path else None
    if points_file is not None:
        try:
            read_pointcloud_ply(points_file)
        except PlyFormatError:
            header = points_file.read_bytes()[: 1024 * 1024]
            end = header.find(b"end_header\n")
            required = (b"format binary_little_endian 1.0", b"property float x", b"property float y", b"property float z")
            if end < 0 or any(item not in header[:end] for item in required):
                raise ValueError("unsupported standard point-cloud PLY layout")

    cameras: tuple[tuple[float, float, float], ...] = ()
    initial_position = initial_forward = initial_up = None
    initial_focus = None
    if bundle.cameras is not None:
        cameras = tuple(
            tuple(float(value) for value in row)
            for row in bundle.cameras.camtoworlds[:, :3, 3]
        )
        first = bundle.cameras.camtoworlds[0]
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
        gaussian_count=int(len(gaussians.means)),
        camera_count=len(cameras),
        sh_degree=gaussians.sh_degree,
        bounds_min=tuple(float(value) for value in low),
        bounds_max=tuple(float(value) for value in high),
        camera_positions=cameras,
        initial_camera_position=initial_position,
        initial_camera_forward=initial_forward,
        initial_camera_up=initial_up,
        initial_focus_distance=initial_focus,
    )
