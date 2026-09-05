"""Validated project-level placement into the Blender-style viewer world."""

from __future__ import annotations

import math
from typing import Any, Iterable


IDENTITY_SCENE_PLACEMENT: dict[str, Any] = {
    "translation": [0.0, 0.0, 0.0],
    "rotation_xyz_degrees": [0.0, 0.0, 0.0],
    "scale_xyz": [1.0, 1.0, 1.0],
    "scale_locked": True,
}

# SceneBundle: X right, Y down, Z forward -> Blender: X right, Y forward, Z up.
BLENDER_FROM_SCENE_BUNDLE: tuple[tuple[float, float, float, float], ...] = (
    (1.0, 0.0, 0.0, 0.0),
    (0.0, 0.0, 1.0, 0.0),
    (0.0, -1.0, 0.0, 0.0),
    (0.0, 0.0, 0.0, 1.0),
)

BLENDER_TARGET_COORDINATE_SYSTEM: dict[str, str] = {
    "handedness": "right_handed",
    "x_axis": "right",
    "y_axis": "forward",
    "z_axis": "up",
}


def default_scene_placement() -> dict[str, Any]:
    return {
        "translation": list(IDENTITY_SCENE_PLACEMENT["translation"]),
        "rotation_xyz_degrees": list(
            IDENTITY_SCENE_PLACEMENT["rotation_xyz_degrees"]
        ),
        "scale_xyz": list(IDENTITY_SCENE_PLACEMENT["scale_xyz"]),
        "scale_locked": True,
    }


def _vector(value: object, name: str) -> list[float]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise ValueError(f"{name} must contain exactly three numbers")
    result: list[float] = []
    for component in value:
        if isinstance(component, bool):
            raise ValueError(f"{name} must contain only finite numbers")
        try:
            number = float(component)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must contain only finite numbers") from exc
        if not math.isfinite(number):
            raise ValueError(f"{name} must contain only finite numbers")
        result.append(number)
    return result


def normalize_scene_placement(value: object | None) -> dict[str, Any]:
    """Return a canonical JSON-safe placement or raise for invalid state."""

    if value is None:
        return default_scene_placement()
    if not isinstance(value, dict):
        raise ValueError("scene_placement must be an object")
    translation = _vector(value.get("translation", (0.0, 0.0, 0.0)), "translation")
    rotation = _vector(
        value.get("rotation_xyz_degrees", (0.0, 0.0, 0.0)),
        "rotation_xyz_degrees",
    )
    scale = _vector(value.get("scale_xyz", (1.0, 1.0, 1.0)), "scale_xyz")
    if any(component < 0.0001 or component > 10000.0 for component in scale):
        raise ValueError("scale_xyz components must be between 0.0001 and 10000")
    locked = value.get("scale_locked", True)
    if not isinstance(locked, bool):
        raise ValueError("scale_locked must be a boolean")
    return {
        "translation": translation,
        "rotation_xyz_degrees": rotation,
        "scale_xyz": scale,
        "scale_locked": locked,
    }


def _multiply(
    left: Iterable[Iterable[float]], right: Iterable[Iterable[float]]
) -> tuple[tuple[float, float, float, float], ...]:
    a = tuple(tuple(float(value) for value in row) for row in left)
    b = tuple(tuple(float(value) for value in row) for row in right)
    return tuple(
        tuple(sum(a[row][k] * b[k][column] for k in range(4)) for column in range(4))
        for row in range(4)
    )


def world_from_scene(
    value: object | None,
) -> tuple[tuple[float, float, float, float], ...]:
    """Compose ``T * Rz * Ry * Rx * S * blender_from_scene_bundle``."""

    placement = normalize_scene_placement(value)
    tx, ty, tz = placement["translation"]
    rx, ry, rz = (
        math.radians(component) for component in placement["rotation_xyz_degrees"]
    )
    scale_x, scale_y, scale_z = placement["scale_xyz"]
    cos_x, sin_x = math.cos(rx), math.sin(rx)
    cos_y, sin_y = math.cos(ry), math.sin(ry)
    cos_z, sin_z = math.cos(rz), math.sin(rz)
    translation = (
        (1.0, 0.0, 0.0, tx),
        (0.0, 1.0, 0.0, ty),
        (0.0, 0.0, 1.0, tz),
        (0.0, 0.0, 0.0, 1.0),
    )
    rotate_x = (
        (1.0, 0.0, 0.0, 0.0),
        (0.0, cos_x, -sin_x, 0.0),
        (0.0, sin_x, cos_x, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )
    rotate_y = (
        (cos_y, 0.0, sin_y, 0.0),
        (0.0, 1.0, 0.0, 0.0),
        (-sin_y, 0.0, cos_y, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )
    rotate_z = (
        (cos_z, -sin_z, 0.0, 0.0),
        (sin_z, cos_z, 0.0, 0.0),
        (0.0, 0.0, 1.0, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )
    scale_matrix = (
        (scale_x, 0.0, 0.0, 0.0),
        (0.0, scale_y, 0.0, 0.0),
        (0.0, 0.0, scale_z, 0.0),
        (0.0, 0.0, 0.0, 1.0),
    )
    result = translation
    for matrix in (rotate_z, rotate_y, rotate_x, scale_matrix, BLENDER_FROM_SCENE_BUNDLE):
        result = _multiply(result, matrix)
    return result

