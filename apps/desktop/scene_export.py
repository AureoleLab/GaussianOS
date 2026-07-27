"""Validated, atomic user-facing Scene Bundle export.

The training SceneBundle is authoritative for Gaussian and camera space.  The
reconstruction point cloud is transformed exactly once with the training
manifest's source-to-scene transform; Viewer presentation transforms are never
consulted.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import os
import re
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import numpy as np

from packages.exportkit import (
    read_gaussian_ply,
    read_gaussian_ply_payload,
    read_pointcloud_ply,
    read_pointcloud_ply_payload,
    write_pointcloud_ply,
)
from packages.quality.colmap import read_images_txt
from packages.scene_bundle import PointCloudTensors, load_scene_bundle

from .project_store import Project, ProjectStore, StageState


EXPORT_SCHEMA_VERSION = "gaussianos-scene-export/v1"
CAMERAS_SCHEMA_VERSION = "gaussianos-cameras/v1"
_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_WINDOWS_RESERVED = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
_PAYLOAD_PATHS = (
    "gaussian/scene_gaussian.ply",
    "pointcloud/scene_pointcloud.ply",
    "cameras/cameras.json",
    "cameras/cameras.csv",
    "cameras/colmap/cameras.txt",
    "cameras/colmap/images.txt",
    "cameras/colmap/points3D.txt",
)


class SceneExportError(RuntimeError):
    """The selected project/run cannot produce a trustworthy scene export."""


@dataclass(frozen=True, slots=True)
class SceneExportResult:
    path: Path
    total_bytes: int
    sha256: str
    gaussian_count: int
    point_count: int
    camera_count: int
    file_hashes: dict[str, str]

    def payload(self) -> dict[str, Any]:
        return {
            "status": "succeeded",
            "path": str(self.path),
            "total_bytes": self.total_bytes,
            "sha256": self.sha256,
            "gaussian_count": self.gaussian_count,
            "point_count": self.point_count,
            "camera_count": self.camera_count,
            "file_hashes": self.file_hashes,
        }


@dataclass(frozen=True, slots=True)
class _SourceReceipt:
    payload: dict[str, Any]
    receipt_path: Path | None
    training_data_dir: Path | None
    source_files: dict[str, dict[str, str]]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_bytes(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())


def _write_json(path: Path, payload: object) -> None:
    _write_bytes(
        path,
        (json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode(
            "utf-8"
        ),
    )


def _safe_export_name(project_name: str) -> str:
    value = _INVALID_FILENAME.sub("_", project_name).strip(" .")
    value = re.sub(r"\s+", " ", value)[:96].rstrip(" .")
    if not value:
        value = "Project"
    if value.upper() in _WINDOWS_RESERVED:
        value = f"{value}_Project"
    return f"{value}_Export"


def _quaternion_wxyz(rotation: np.ndarray) -> list[float]:
    """Convert a proper 3x3 rotation matrix to a stable unit quaternion."""

    matrix = np.asarray(rotation, dtype=np.float64)
    trace = float(np.trace(matrix))
    if trace > 0.0:
        root = math.sqrt(trace + 1.0) * 2.0
        values = np.array(
            [
                0.25 * root,
                (matrix[2, 1] - matrix[1, 2]) / root,
                (matrix[0, 2] - matrix[2, 0]) / root,
                (matrix[1, 0] - matrix[0, 1]) / root,
            ]
        )
    else:
        index = int(np.argmax(np.diag(matrix)))
        if index == 0:
            root = math.sqrt(1.0 + matrix[0, 0] - matrix[1, 1] - matrix[2, 2]) * 2.0
            values = np.array(
                [
                    (matrix[2, 1] - matrix[1, 2]) / root,
                    0.25 * root,
                    (matrix[0, 1] + matrix[1, 0]) / root,
                    (matrix[0, 2] + matrix[2, 0]) / root,
                ]
            )
        elif index == 1:
            root = math.sqrt(1.0 + matrix[1, 1] - matrix[0, 0] - matrix[2, 2]) * 2.0
            values = np.array(
                [
                    (matrix[0, 2] - matrix[2, 0]) / root,
                    (matrix[0, 1] + matrix[1, 0]) / root,
                    0.25 * root,
                    (matrix[1, 2] + matrix[2, 1]) / root,
                ]
            )
        else:
            root = math.sqrt(1.0 + matrix[2, 2] - matrix[0, 0] - matrix[1, 1]) * 2.0
            values = np.array(
                [
                    (matrix[1, 0] - matrix[0, 1]) / root,
                    (matrix[0, 2] + matrix[2, 0]) / root,
                    (matrix[1, 2] + matrix[2, 1]) / root,
                    0.25 * root,
                ]
            )
    values /= np.linalg.norm(values)
    if values[0] < 0.0:
        values = -values
    return [float(value) for value in values]


def _transform_pointcloud(
    pointcloud: PointCloudTensors, source_to_scene: np.ndarray
) -> PointCloudTensors:
    matrix = np.asarray(source_to_scene, dtype=np.float64)
    positions = pointcloud.positions.astype(np.float64)
    homogeneous = np.column_stack((positions, np.ones(len(positions), dtype=np.float64)))
    transformed_positions = (homogeneous @ matrix.T)[:, :3].astype(np.float32)
    transformed_normals = None
    if pointcloud.normals is not None:
        normal_matrix = np.linalg.inv(matrix[:3, :3]).T
        transformed = pointcloud.normals.astype(np.float64) @ normal_matrix.T
        lengths = np.linalg.norm(transformed, axis=1, keepdims=True)
        nonzero = lengths[:, 0] > np.finfo(np.float64).eps
        transformed[nonzero] /= lengths[nonzero]
        transformed_normals = transformed.astype(np.float32)
    return PointCloudTensors(
        positions=np.ascontiguousarray(transformed_positions),
        normals=(
            np.ascontiguousarray(transformed_normals)
            if transformed_normals is not None
            else None
        ),
        colors_rgb=pointcloud.colors_rgb,
    )


def _stage(project: Project, name: str) -> StageState:
    state = project.stages.get(name)
    if state is None or state.status != "succeeded":
        raise SceneExportError(
            f"No valid model is available: the {name} stage has not succeeded."
        )
    return state


def _load_source_receipt(
    store: ProjectStore, project: Project, requested_run_id: str
) -> _SourceReceipt:
    if not requested_run_id or requested_run_id != project.run_id:
        raise SceneExportError(
            f"Stale run: requested {requested_run_id or '(none)'}, "
            f"but the active run is {project.run_id or '(none)'}."
        )
    paths = store.paths(project)
    run_root = paths.run(requested_run_id).root
    if project.workspace_kind == "isolated" and not run_root.is_dir():
        raise SceneExportError(f"Stale run: active run {requested_run_id} is missing.")
    receipt_path = paths.viewer_manifest
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        if project.workspace_kind != "isolated":
            return _load_legacy_source_receipt(
                store, project, requested_run_id
            )
        raise SceneExportError(
            "Source artifact receipt is missing; reload or rerun the current project."
        ) from exc
    except (OSError, ValueError, TypeError) as exc:
        raise SceneExportError(f"Source artifact receipt is unreadable: {exc}") from exc
    if (
        receipt.get("schema_version") != "gaussianos-viewer-scene/v1"
        or receipt.get("project_id") != project.project_id
        or receipt.get("run_id") != requested_run_id
        or receipt.get("committed") is not True
    ):
        raise SceneExportError(
            "Source artifact receipt does not belong to the active project/run."
        )
    return _SourceReceipt(
        payload=receipt,
        receipt_path=receipt_path,
        training_data_dir=None,
        source_files={
            "viewer_receipt": {
                "path": receipt_path.relative_to(paths.workspace).as_posix(),
                "sha256": _sha256(receipt_path),
            }
        },
    )


def _load_legacy_source_receipt(
    store: ProjectStore, project: Project, run_id: str
) -> _SourceReceipt:
    validate = _stage(project, "validate")
    if len(validate.artifact_paths) < 2:
        raise SceneExportError(
            "Legacy validate state does not identify a SceneBundle and Gaussian PLY."
        )
    gaussian = Path(validate.artifact_paths[1]).resolve()
    artifact_manifest_path = gaussian.parent / "artifact.manifest.json"
    try:
        artifact_manifest = json.loads(
            artifact_manifest_path.read_text(encoding="utf-8")
        )
    except (OSError, ValueError, TypeError) as exc:
        raise SceneExportError(
            f"Legacy source artifact manifest is unavailable: {exc}"
        ) from exc
    attempt_id = str(artifact_manifest.get("source_attempt_id", ""))
    request_id = str(artifact_manifest.get("source_request_id", ""))
    artifact_id = str(artifact_manifest.get("artifact_id", ""))
    if (
        artifact_manifest.get("schema_version") != "1.0.0"
        or not attempt_id
        or not request_id
        or not artifact_id
        or gaussian.parent.name != artifact_id
    ):
        raise SceneExportError("Legacy source artifact manifest is invalid.")
    attempt_root = (
        store.root.parent
        / "artifact-store"
        / "completed_attempts"
        / run_id
        / "train"
        / attempt_id
    )
    final_path = attempt_root / "attempt.final.json"
    request_path = attempt_root / "request.json"
    try:
        final = json.loads(final_path.read_text(encoding="utf-8"))
        request = json.loads(request_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, TypeError) as exc:
        raise SceneExportError(
            f"Legacy Worker receipt chain is unavailable: {exc}"
        ) from exc
    if (
        final.get("state") != "succeeded"
        or final.get("run_id") != run_id
        or final.get("request_id") != request_id
        or final.get("attempt_id") != attempt_id
        or artifact_id not in final.get("details", {}).get("artifact_ids", [])
        or request.get("run_id") != run_id
        or request.get("request_id") != request_id
        or request.get("attempt_id") != attempt_id
        or request.get("stage_id") != "train"
    ):
        raise SceneExportError(
            "Legacy Worker receipt does not belong to the active project/run."
        )
    indexed = {
        str(item.get("relative_path")): item
        for item in artifact_manifest.get("files", [])
        if isinstance(item, dict)
    }
    for source in (Path(validate.artifact_paths[0]).resolve(), gaussian):
        relative = source.relative_to(gaussian.parent).as_posix()
        item = indexed.get(relative)
        if source.is_file():
            if not item or item.get("sha256") != _sha256(source):
                raise SceneExportError(
                    f"Legacy artifact manifest hash mismatch: {relative}"
                )
        elif source.is_dir():
            for child in source.rglob("*"):
                if child.is_file():
                    child_relative = child.relative_to(gaussian.parent).as_posix()
                    child_item = indexed.get(child_relative)
                    if not child_item or child_item.get("sha256") != _sha256(child):
                        raise SceneExportError(
                            f"Legacy artifact manifest hash mismatch: {child_relative}"
                        )
        else:
            raise SceneExportError(f"Legacy source artifact is missing: {source}")
    data_dir_value = request.get("config", {}).get("data_dir")
    data_dir = (
        Path(str(data_dir_value)).resolve()
        if isinstance(data_dir_value, str) and data_dir_value
        else None
    )
    payload = {
        "schema_version": "gaussianos-legacy-worker-receipt/v1",
        "project_id": project.project_id,
        "run_id": run_id,
        "committed": True,
        "artifact_id": artifact_id,
        "request_id": request_id,
        "attempt_id": attempt_id,
        "producer_plugin_id": artifact_manifest.get("producer_plugin_id"),
        "producer_plugin_version": artifact_manifest.get(
            "producer_plugin_version"
        ),
    }
    return _SourceReceipt(
        payload=payload,
        receipt_path=None,
        training_data_dir=data_dir,
        source_files={
            "artifact_manifest": {
                "path": str(artifact_manifest_path),
                "sha256": _sha256(artifact_manifest_path),
            },
            "attempt_final": {
                "path": str(final_path),
                "sha256": _sha256(final_path),
            },
            "request": {
                "path": str(request_path),
                "sha256": _sha256(request_path),
            },
        },
    )


def _source_artifacts(
    store: ProjectStore, project: Project, source_receipt: _SourceReceipt
) -> tuple[Path, Path, Path]:
    receipt = source_receipt.payload
    validate = _stage(project, "validate")
    _stage(project, "export")
    if len(validate.artifact_paths) < 2:
        raise SceneExportError("Validate receipt does not identify a SceneBundle and Gaussian PLY.")
    bundle = Path(validate.artifact_paths[0]).resolve()
    gaussian = Path(validate.artifact_paths[1]).resolve()
    pointcloud_value = receipt.get("pointcloud")
    if not pointcloud_value and project.workspace_kind != "isolated":
        pointcloud_value = next(
            (
                value
                for value in project.stages["export"].artifact_paths
                if value.endswith(".pointcloud.ply")
            ),
            None,
        )
    if not isinstance(pointcloud_value, str) or not pointcloud_value:
        raise SceneExportError("The active run has no point-cloud artifact.")
    pointcloud = Path(pointcloud_value).resolve()
    if project.workspace_kind == "isolated":
        if str(bundle) != str(Path(str(receipt.get("bundle", ""))).resolve()):
            raise SceneExportError("Source receipt SceneBundle does not match the validated run.")
        if str(gaussian) != str(Path(str(receipt.get("gaussian", ""))).resolve()):
            raise SceneExportError("Source receipt Gaussian does not match the validated run.")
    paths = store.paths(project)
    for label, path in (
        ("SceneBundle", bundle),
        ("Gaussian", gaussian),
        ("point cloud", pointcloud),
    ):
        if project.workspace_kind == "isolated" and not paths.contains(path):
            raise SceneExportError(f"{label} artifact is outside the owning project.")
        if not path.exists():
            raise SceneExportError(f"{label} artifact is missing: {path}")
    return bundle, gaussian, pointcloud


def _camera_metadata(
    store: ProjectStore,
    project: Project,
    run_id: str,
    camera_count: int,
    source_receipt: _SourceReceipt,
) -> tuple[list[str], dict[str, dict[str, Any]], dict[str, Any]]:
    paths = store.paths(project)
    run_paths = paths.run(run_id)
    training_data = source_receipt.training_data_dir or run_paths.training
    sparse = training_data / "sparse" / "0"
    poses = read_images_txt(sparse / "images.txt")
    names = [pose.image_name for pose in poses]
    if len(names) != camera_count:
        raise SceneExportError(
            "Frozen training camera names do not match the SceneBundle camera count."
        )
    timeline_source: dict[str, Any]
    if run_paths.timeline_manifest.is_file():
        try:
            timeline_receipt = json.loads(
                run_paths.timeline_manifest.read_text(encoding="utf-8")
            )
        except (OSError, ValueError, TypeError) as exc:
            raise SceneExportError(f"Camera timeline receipt is unavailable: {exc}") from exc
        if (
            timeline_receipt.get("project_id") != project.project_id
            or timeline_receipt.get("run_id") != run_id
            or timeline_receipt.get("stage") != "timeline"
        ):
            raise SceneExportError("Camera timeline receipt is stale or belongs to another run.")
        timeline_source = {
            "kind": "timeline_receipt",
            "path": str(run_paths.timeline_manifest),
            "sha256": _sha256(run_paths.timeline_manifest),
            "schema_version": timeline_receipt.get("schema_version"),
        }
    else:
        records = project.sampling.get("camera_timeline", [])
        if not isinstance(records, list) or not records:
            dataset_path = training_data / "dataset.manifest.json"
            try:
                dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
                records = []
                for scene in dataset.get("scenes", []):
                    for frame in scene.get("frames", []):
                        image_name = Path(str(frame.get("image_path", ""))).name
                        records.append(
                            {
                                "registration_status": "registered",
                                "source_frame_index": frame.get("sample_index"),
                                "timestamp_seconds": frame.get(
                                    "nominal_timestamp_seconds"
                                ),
                                "frame_id": frame.get("frame_id"),
                                "camera": {"image_name": image_name},
                            }
                        )
            except (OSError, ValueError, TypeError) as exc:
                raise SceneExportError(
                    f"Legacy camera metadata is unavailable: {exc}"
                ) from exc
        timeline_receipt = {"records": records}
        canonical = (
            json.dumps(records, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        ).encode("utf-8")
        timeline_source = {
            "kind": "durable_project_sampling",
            "sha256": hashlib.sha256(canonical).hexdigest(),
        }
    by_name: dict[str, dict[str, Any]] = {}
    for record in timeline_receipt.get("records", []):
        camera = record.get("camera")
        if record.get("registration_status") == "registered" and isinstance(camera, dict):
            name = str(camera.get("image_name", ""))
            if name:
                by_name[name] = record
    return names, by_name, timeline_source


def _camera_records(
    cameras: Any,
    names: list[str],
    timeline: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for index, image_name in enumerate(names):
        world_from_camera = cameras.camtoworlds[index].astype(np.float64)
        camera_from_world = np.linalg.inv(world_from_camera)
        if not np.allclose(
            world_from_camera @ camera_from_world,
            np.eye(4),
            rtol=1e-8,
            atol=1e-8,
        ):
            raise SceneExportError(f"Camera matrix inversion failed for {image_name}.")
        intrinsics = cameras.intrinsics[index]
        width, height = (int(value) for value in cameras.image_sizes[index])
        source = timeline.get(image_name, {})
        source_index = source.get("source_frame_index")
        timestamp = source.get("timestamp_seconds")
        records.append(
            {
                "frame_id": str(
                    source.get("frame_id")
                    or (
                        f"scene:{int(source_index):06d}"
                        if source_index is not None
                        else f"scene:{index:06d}"
                    )
                ),
                "image_name": image_name,
                "width": width,
                "height": height,
                "fx": float(intrinsics[0, 0]),
                "fy": float(intrinsics[1, 1]),
                "cx": float(intrinsics[0, 2]),
                "cy": float(intrinsics[1, 2]),
                "distortion": {"model": "none", "parameters": []},
                "world_from_camera": world_from_camera.tolist(),
                "camera_from_world": camera_from_world.tolist(),
                "position": [float(value) for value in world_from_camera[:3, 3]],
                "quaternion": _quaternion_wxyz(world_from_camera[:3, :3]),
                "timestamp": float(timestamp) if timestamp is not None else None,
                "source_frame_index": (
                    int(source_index) if source_index is not None else None
                ),
            }
        )
    return records


def _write_cameras_json(path: Path, records: list[dict[str, Any]]) -> None:
    _write_json(
        path,
        {
            "schema_version": CAMERAS_SCHEMA_VERSION,
            "camera_convention": "opencv_cam2world",
            "quaternion_order": "wxyz",
            "cameras": records,
        },
    )


def _write_cameras_csv(path: Path, records: list[dict[str, Any]]) -> None:
    matrix_fields = [
        f"{prefix}_{row}{column}"
        for prefix in ("world_from_camera", "camera_from_world")
        for row in range(4)
        for column in range(4)
    ]
    fields = [
        "frame_id", "image_name", "width", "height", "fx", "fy", "cx", "cy",
        "distortion_model", "distortion_parameters", "position_x", "position_y",
        "position_z", "quaternion_w", "quaternion_x", "quaternion_y",
        "quaternion_z", "timestamp", "source_frame_index", *matrix_fields,
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for record in records:
            row: dict[str, Any] = {
                key: record[key]
                for key in ("frame_id", "image_name", "width", "height", "fx", "fy", "cx", "cy")
            }
            row.update(
                {
                    "distortion_model": record["distortion"]["model"],
                    "distortion_parameters": json.dumps(
                        record["distortion"]["parameters"], separators=(",", ":")
                    ),
                    **{
                        f"position_{axis}": record["position"][index]
                        for index, axis in enumerate(("x", "y", "z"))
                    },
                    **{
                        f"quaternion_{axis}": record["quaternion"][index]
                        for index, axis in enumerate(("w", "x", "y", "z"))
                    },
                    "timestamp": "" if record["timestamp"] is None else record["timestamp"],
                    "source_frame_index": (
                        ""
                        if record["source_frame_index"] is None
                        else record["source_frame_index"]
                    ),
                }
            )
            for prefix in ("world_from_camera", "camera_from_world"):
                matrix = record[prefix]
                for matrix_row in range(4):
                    for column in range(4):
                        row[f"{prefix}_{matrix_row}{column}"] = matrix[matrix_row][column]
            writer.writerow(row)
        stream.flush()
        os.fsync(stream.fileno())


def _write_colmap(
    root: Path, records: list[dict[str, Any]], pointcloud: PointCloudTensors
) -> None:
    camera_lines = [
        "# Camera list with one line of data per camera:",
        "# CAMERA_ID, MODEL, WIDTH, HEIGHT, PARAMS[]",
        f"# Number of cameras: {len(records)}",
    ]
    image_lines = [
        "# Image list with two lines of data per image:",
        "# IMAGE_ID, QW, QX, QY, QZ, TX, TY, TZ, CAMERA_ID, NAME",
        f"# Number of images: {len(records)}, mean observations per image: 0",
    ]
    for index, record in enumerate(records, start=1):
        camera_lines.append(
            f"{index} PINHOLE {record['width']} {record['height']} "
            f"{record['fx']:.17g} {record['fy']:.17g} "
            f"{record['cx']:.17g} {record['cy']:.17g}"
        )
        camera_from_world = np.asarray(record["camera_from_world"], dtype=np.float64)
        quaternion = _quaternion_wxyz(camera_from_world[:3, :3])
        translation = camera_from_world[:3, 3]
        image_lines.append(
            f"{index} {' '.join(f'{value:.17g}' for value in quaternion)} "
            f"{' '.join(f'{value:.17g}' for value in translation)} "
            f"{index} {record['image_name']}"
        )
        image_lines.append("")
    point_lines = [
        "# 3D point list with one line of data per point:",
        "# POINT3D_ID, X, Y, Z, R, G, B, ERROR, TRACK[]",
        f"# Number of points: {len(pointcloud.positions)}, mean track length: 0",
    ]
    colors = pointcloud.colors_rgb
    for index, position in enumerate(pointcloud.positions, start=1):
        color = colors[index - 1] if colors is not None else (255, 255, 255)
        point_lines.append(
            f"{index} {' '.join(f'{float(value):.9g}' for value in position)} "
            f"{int(color[0])} {int(color[1])} {int(color[2])} 0"
        )
    _write_bytes(root / "cameras.txt", ("\n".join(camera_lines) + "\n").encode("utf-8"))
    _write_bytes(root / "images.txt", ("\n".join(image_lines) + "\n").encode("utf-8"))
    _write_bytes(root / "points3D.txt", ("\n".join(point_lines) + "\n").encode("utf-8"))


def validate_scene_export(directory: str | os.PathLike[str]) -> dict[str, Any]:
    """Reload and integrity-check one committed export without display transforms."""

    root = Path(directory).resolve(strict=True)
    manifest_path = root / "scene_manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != EXPORT_SCHEMA_VERSION:
        raise SceneExportError("Unsupported scene export manifest.")
    files = manifest.get("files")
    hashes = manifest.get("sha256")
    if not isinstance(files, dict) or not isinstance(hashes, dict):
        raise SceneExportError("Scene manifest file index is invalid.")
    for relative in _PAYLOAD_PATHS:
        path = root / relative
        if not path.is_file() or hashes.get(relative) != _sha256(path):
            raise SceneExportError(f"Scene export hash mismatch: {relative}")
    gaussian = read_gaussian_ply_payload(root / files["gaussian"])
    pointcloud = read_pointcloud_ply_payload(root / files["pointcloud"])
    camera_payload = json.loads((root / files["cameras_json"]).read_text(encoding="utf-8"))
    records = camera_payload.get("cameras", [])
    for record in records:
        forward = np.asarray(record["world_from_camera"], dtype=np.float64)
        inverse = np.asarray(record["camera_from_world"], dtype=np.float64)
        if not np.allclose(forward @ inverse, np.eye(4), rtol=1e-7, atol=1e-7):
            raise SceneExportError(f"Camera matrices are not inverse: {record['image_name']}")
    counts = manifest.get("counts", {})
    actual = {
        "gaussians": int(len(gaussian.means)),
        "points": int(len(pointcloud.positions)),
        "cameras": int(len(records)),
    }
    if counts != actual:
        raise SceneExportError(f"Scene export count mismatch: {counts} != {actual}")
    return {"manifest": manifest, "counts": actual}


class SceneBundleExporter:
    """Resolve the current durable run and publish a complete atomic bundle."""

    def __init__(self, store: ProjectStore) -> None:
        self.store = store

    def export(
        self,
        project_id: str,
        run_id: str,
        parent_directory: str | os.PathLike[str],
        *,
        checkpoint: Callable[[], None] | None = None,
    ) -> SceneExportResult:
        check = checkpoint or (lambda: None)
        try:
            project = self.store.load(project_id)
        except Exception as exc:
            raise SceneExportError(f"Project is unavailable: {exc}") from exc
        if project.archived:
            raise SceneExportError("Archived projects must be restored before export.")
        if project.status == "running":
            raise SceneExportError("Wait for the current run to finish before exporting.")
        if project.status != "succeeded":
            raise SceneExportError("No valid model is available for export.")
        source_receipt = _load_source_receipt(self.store, project, run_id)
        bundle_path, gaussian_path, pointcloud_path = _source_artifacts(
            self.store, project, source_receipt
        )
        check()
        bundle = load_scene_bundle(bundle_path)
        if bundle.gaussians is None or bundle.cameras is None:
            raise SceneExportError("Validated SceneBundle lacks Gaussian or camera tensors.")
        gaussian = read_gaussian_ply(gaussian_path)
        for field in (
            "means", "log_scales", "quats_wxyz", "opacity_logits", "sh_coeffs"
        ):
            if not np.array_equal(
                getattr(bundle.gaussians, field), getattr(gaussian, field)
            ):
                raise SceneExportError(
                    f"Gaussian PLY {field} does not match the authoritative SceneBundle."
                )
        source_pointcloud = read_pointcloud_ply(pointcloud_path)
        world_from_reconstruction = np.asarray(
            bundle.manifest.normalization_transform.source_to_scene,
            dtype=np.float64,
        )
        pointcloud = _transform_pointcloud(
            source_pointcloud, world_from_reconstruction
        )
        names, timeline, timeline_source = _camera_metadata(
            self.store,
            project,
            run_id,
            len(bundle.cameras.camtoworlds),
            source_receipt,
        )
        camera_records = _camera_records(bundle.cameras, names, timeline)
        check()

        parent = Path(parent_directory).expanduser().resolve()
        if not parent.is_dir():
            raise SceneExportError(f"Selected save directory does not exist: {parent}")
        destination = parent / _safe_export_name(project.name)
        if destination.exists():
            raise SceneExportError(f"Export target already exists: {destination}")
        staging = Path(
            tempfile.mkdtemp(prefix=f".{destination.name}.staging-", dir=str(parent))
        )
        try:
            gaussian_target = staging / "gaussian" / "scene_gaussian.ply"
            gaussian_target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(gaussian_path, gaussian_target)
            if _sha256(gaussian_target) != _sha256(gaussian_path):
                raise SceneExportError("Gaussian copy failed SHA-256 verification.")
            read_gaussian_ply_payload(gaussian_target)
            check()

            temporary_pointcloud = staging / "pointcloud" / "scene.pointcloud.ply"
            write_pointcloud_ply(temporary_pointcloud, pointcloud)
            pointcloud_target = temporary_pointcloud.with_name("scene_pointcloud.ply")
            os.replace(temporary_pointcloud, pointcloud_target)
            reloaded_points = read_pointcloud_ply_payload(pointcloud_target)
            if not np.array_equal(reloaded_points.positions, pointcloud.positions):
                raise SceneExportError("Point cloud round-trip changed scene coordinates.")

            cameras_root = staging / "cameras"
            _write_cameras_json(cameras_root / "cameras.json", camera_records)
            _write_cameras_csv(cameras_root / "cameras.csv", camera_records)
            _write_colmap(cameras_root / "colmap", camera_records, pointcloud)
            check()

            file_hashes = {
                relative: _sha256(staging / relative) for relative in _PAYLOAD_PATHS
            }
            manifest = {
                "schema_version": EXPORT_SCHEMA_VERSION,
                "project_id": project.project_id,
                "run_id": run_id,
                "coordinate_system": {
                    **bundle.manifest.coordinate_system.model_dump(mode="json"),
                    "camera_convention": bundle.manifest.camera_convention,
                    "quaternion_order": bundle.manifest.quaternion_order,
                    "unit": bundle.manifest.world_unit,
                    "has_metric_scale": bundle.manifest.has_metric_scale,
                },
                "world_from_reconstruction": world_from_reconstruction.tolist(),
                "world_transform_applied": {
                    "gaussian": "already_in_scene_world",
                    "pointcloud": "world_from_reconstruction",
                    "cameras": "already_in_scene_world",
                    "viewer_display_transform": "not_applied",
                },
                "files": {
                    "gaussian": _PAYLOAD_PATHS[0],
                    "pointcloud": _PAYLOAD_PATHS[1],
                    "cameras_json": _PAYLOAD_PATHS[2],
                    "cameras_csv": _PAYLOAD_PATHS[3],
                    "colmap_cameras": _PAYLOAD_PATHS[4],
                    "colmap_images": _PAYLOAD_PATHS[5],
                    "colmap_points3D": _PAYLOAD_PATHS[6],
                },
                "counts": {
                    "gaussians": int(len(gaussian.means)),
                    "points": int(len(pointcloud.positions)),
                    "cameras": int(len(camera_records)),
                },
                "sha256": file_hashes,
                "source_artifact_receipt": {
                    "receipt": source_receipt.payload,
                    "source_files": source_receipt.source_files,
                    "camera_metadata": timeline_source,
                },
            }
            _write_json(staging / "scene_manifest.json", manifest)
            validate_scene_export(staging)
            check()

            # The single visibility boundary: no partial bundle is ever exposed.
            os.replace(staging, destination)
        except Exception:
            if staging.exists() and staging.parent == parent:
                shutil.rmtree(staging)
            raise

        validated = validate_scene_export(destination)
        total_bytes = sum(
            path.stat().st_size for path in destination.rglob("*") if path.is_file()
        )
        return SceneExportResult(
            path=destination,
            total_bytes=total_bytes,
            sha256=_sha256(destination / "scene_manifest.json"),
            gaussian_count=validated["counts"]["gaussians"],
            point_count=validated["counts"]["points"],
            camera_count=validated["counts"]["cameras"],
            file_hashes=file_hashes,
        )
