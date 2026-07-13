"""Durable source-frame to reconstructed-COLMAP-camera mapping."""

from __future__ import annotations

import math
import re
from copy import deepcopy
from pathlib import Path
from typing import Any

from packages.quality.colmap import read_images_txt


_FRAME_NAME = re.compile(r"frame_(\d+)\.[^.]+$", re.IGNORECASE)


def _cameras(path: Path) -> dict[int, tuple[list[list[float]], int, int]]:
    result: dict[int, tuple[list[list[float]], int, int]] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        if not raw or raw.startswith("#"):
            continue
        fields = raw.split()
        camera_id, model, width, height = int(fields[0]), fields[1], int(fields[2]), int(fields[3])
        values = [float(value) for value in fields[4:]]
        if model in {"SIMPLE_PINHOLE", "SIMPLE_RADIAL"}:
            fx = fy = values[0]; cx, cy = values[1:3]
        elif model in {"PINHOLE", "OPENCV"}:
            fx, fy, cx, cy = values[:4]
        else:
            raise ValueError(f"unsupported COLMAP camera model for timeline: {model}")
        result[camera_id] = ([[fx, 0.0, cx], [0.0, fy, cy], [0.0, 0.0, 1.0]], width, height)
    if not result:
        raise ValueError("COLMAP cameras.txt contains no cameras")
    return result


def build_camera_timeline(
    sampling: dict[str, Any], images_dir: str | Path, sparse_dir: str | Path,
) -> list[dict[str, Any]]:
    """Join selection provenance to extracted images and registered cameras."""
    images = Path(images_dir).resolve()
    sparse = Path(sparse_dir).resolve()
    intrinsics = _cameras(sparse / "cameras.txt")
    registered = {pose.image_name: pose for pose in read_images_txt(sparse / "images.txt")}
    fps = float(sampling.get("fps", 1.0))
    selected = [int(value) for value in sampling.get("selected_frame_indices", [])]
    selected_order = {value: order for order, value in enumerate(selected)}
    records = {int(item["index"]): deepcopy(item) for item in sampling.get("timeline", [])}
    for source_index in selected:
        records.setdefault(source_index, {
            "index": source_index,
            "timestamp_seconds": source_index / max(fps, 1e-9),
            "status": "selected",
            "candidate": True,
            "reason": None,
            "thumbnail_path": None,
        })

    result: list[dict[str, Any]] = []
    for source_index, record in sorted(records.items()):
        is_selected = source_index in selected_order
        extracted = images / f"frame_{source_index:06d}.png"
        pose = registered.get(extracted.name) if is_selected and extracted.is_file() else None
        entry = {
            **record,
            "index": source_index,
            "source_frame_index": source_index,
            "timestamp_seconds": float(record.get("timestamp_seconds", source_index / max(fps, 1e-9))),
            "selection_status": "selected" if is_selected else "rejected",
            "selected_order": selected_order.get(source_index),
            "extracted_image_path": str(extracted) if is_selected and extracted.is_file() else None,
            "registration_status": "registered" if pose is not None else ("unregistered" if is_selected else "not_applicable"),
            "colmap_image_id": pose.image_id if pose is not None else None,
            "colmap_camera_id": pose.camera_id if pose is not None else None,
            "camera": None,
        }
        if not entry.get("thumbnail_path") and entry["extracted_image_path"]:
            entry["thumbnail_path"] = entry["extracted_image_path"]
        if pose is not None:
            matrix, width, height = intrinsics[pose.camera_id]
            fy = float(matrix[1][1])
            entry["camera"] = {
                "image_id": pose.image_id,
                "image_name": pose.image_name,
                "cam2world": pose.cam2world.tolist(),
                "intrinsics": matrix,
                "width": width,
                "height": height,
                "aspect_ratio": width / height,
                "fov_y_degrees": math.degrees(2.0 * math.atan(height / (2.0 * fy))),
            }
        result.append(entry)
    return result

