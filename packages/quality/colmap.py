"""Read-only COLMAP text diagnostics without importing COLMAP or pycolmap."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import numpy as np


@dataclass(frozen=True)
class ColmapCameraPose:
    image_id: int
    image_name: str
    camera_id: int
    cam2world: np.ndarray


@dataclass(frozen=True)
class ColmapModelMetrics:
    registered_frames: int
    registered_images: int
    points: int
    observations: int
    mean_track_length: float
    mean_observations_per_image: float
    mean_reprojection_error_px: float


def _quaternion_wxyz_to_rotation(quaternion: np.ndarray) -> np.ndarray:
    q = np.asarray(quaternion, dtype=np.float64)
    norm = float(np.linalg.norm(q))
    if not np.isfinite(norm) or norm <= np.finfo(np.float64).eps:
        raise ValueError("invalid COLMAP quaternion")
    w, x, y, z = q / norm
    return np.array(
        [
            [1 - 2 * (y * y + z * z), 2 * (x * y - z * w), 2 * (x * z + y * w)],
            [2 * (x * y + z * w), 1 - 2 * (x * x + z * z), 2 * (y * z - x * w)],
            [2 * (x * z - y * w), 2 * (y * z + x * w), 1 - 2 * (x * x + y * y)],
        ],
        dtype=np.float64,
    )


def read_images_txt(path: Path) -> list[ColmapCameraPose]:
    """Read COLMAP world-to-camera poses and return OpenCV cam2world poses."""

    poses: list[ColmapCameraPose] = []
    expect_pose = True
    with Path(path).open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if line.startswith("#"):
                continue
            if not expect_pose:
                expect_pose = True
                continue
            if not line:
                continue
            fields = line.split(maxsplit=9)
            if len(fields) != 10:
                raise ValueError(f"invalid COLMAP image pose line: {line[:120]}")
            image_id = int(fields[0])
            quaternion = np.asarray([float(value) for value in fields[1:5]], dtype=np.float64)
            translation = np.asarray([float(value) for value in fields[5:8]], dtype=np.float64)
            camera_id = int(fields[8])
            rotation_world_to_camera = _quaternion_wxyz_to_rotation(quaternion)
            rotation_camera_to_world = rotation_world_to_camera.T
            camera_position = -(rotation_camera_to_world @ translation)
            cam2world = np.eye(4, dtype=np.float64)
            cam2world[:3, :3] = rotation_camera_to_world
            cam2world[:3, 3] = camera_position
            poses.append(
                ColmapCameraPose(
                    image_id=image_id,
                    image_name=fields[9],
                    camera_id=camera_id,
                    cam2world=cam2world,
                )
            )
            expect_pose = False
    if not expect_pose:
        raise ValueError("COLMAP images.txt is missing the final POINTS2D line")
    if not poses:
        raise ValueError("COLMAP images.txt contains no registered poses")
    names = [pose.image_name for pose in poses]
    if len(names) != len(set(names)):
        raise ValueError("COLMAP images.txt contains duplicate image names")
    return sorted(poses, key=lambda pose: pose.image_name)


_METRIC_PATTERNS: dict[str, tuple[str, type]] = {
    "registered_frames": (r"Registered frames:\s+(\d+)", int),
    "registered_images": (r"Registered images:\s+(\d+)", int),
    "points": (r"Points:\s+(\d+)", int),
    "observations": (r"Observations:\s+(\d+)", int),
    "mean_track_length": (r"Mean track length:\s+([0-9.eE+-]+)", float),
    "mean_observations_per_image": (r"Mean observations per image:\s+([0-9.eE+-]+)", float),
    "mean_reprojection_error_px": (r"Mean reprojection error:\s+([0-9.eE+-]+)px", float),
}


def parse_model_analyzer(text: str) -> ColmapModelMetrics:
    values: dict[str, int | float] = {}
    for field, (pattern, converter) in _METRIC_PATTERNS.items():
        match = re.search(pattern, text)
        if match is None:
            raise ValueError(f"missing COLMAP model analyzer metric: {field}")
        values[field] = converter(match.group(1))
    return ColmapModelMetrics(**values)  # type: ignore[arg-type]
