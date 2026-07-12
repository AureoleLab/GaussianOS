"""Small, dependency-free data adapter for the QML reconstruction viewer."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from packages.exportkit import read_gaussian_ply
from packages.scene_bundle import load_scene_bundle


def _project(points: np.ndarray, maximum: int = 20_000) -> list[list[float]]:
    if len(points) > maximum:
        points = points[np.linspace(0, len(points) - 1, maximum, dtype=np.int64)]
    if not len(points):
        return []
    xy = points[:, :2].astype(np.float64)
    low, high = xy.min(axis=0), xy.max(axis=0)
    span = np.maximum(high - low, 1e-6)
    normalized = (xy - low) / span
    return normalized.tolist()


def viewer_payload(bundle_path: str | Path, ply_path: str | Path | None = None) -> str:
    """Return bounded 2D preview samples; the original assets stay in the store."""
    bundle = load_scene_bundle(bundle_path)
    cameras = [] if bundle.cameras is None else _project(bundle.cameras.camtoworlds[:, :3, 3], 2_000)
    gaussians = []
    if ply_path:
        gaussians = _project(read_gaussian_ply(ply_path).means)
    elif bundle.gaussians is not None:
        gaussians = _project(bundle.gaussians.means)
    return json.dumps({"cameras": cameras, "points": gaussians, "gaussians": gaussians}, separators=(",", ":"))
