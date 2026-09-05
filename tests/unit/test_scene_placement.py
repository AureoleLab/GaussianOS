from __future__ import annotations

import math

import numpy as np
import pytest

from apps.desktop.project_store import Project
from apps.desktop.scene_placement import (
    BLENDER_FROM_SCENE_BUNDLE,
    default_scene_placement,
    normalize_scene_placement,
    world_from_scene,
)


def test_legacy_project_defaults_to_identity_placement() -> None:
    project = Project.from_dict({"project_id": "p", "name": "P", "root": "C:/P"})
    assert project.scene_placement == default_scene_placement()


def test_world_from_scene_maps_scene_bundle_to_blender_z_up() -> None:
    np.testing.assert_allclose(world_from_scene(None), BLENDER_FROM_SCENE_BUNDLE)
    matrix = np.asarray(world_from_scene(None))
    np.testing.assert_allclose(matrix @ [1, 0, 0, 1], [1, 0, 0, 1])
    np.testing.assert_allclose(matrix @ [0, 1, 0, 1], [0, 0, -1, 1])
    np.testing.assert_allclose(matrix @ [0, 0, 1, 1], [0, 1, 0, 1])


def test_world_from_scene_composes_translation_rotation_and_xyz_scale() -> None:
    placement = {
        "translation": [4, 5, 6],
        "rotation_xyz_degrees": [0, 0, 90],
        "scale_xyz": [2, 3, 4],
        "scale_locked": False,
    }
    matrix = np.asarray(world_from_scene(placement))
    np.testing.assert_allclose(matrix[:3, 3], [4, 5, 6])
    assert math.isclose(abs(np.linalg.det(matrix[:3, :3])), 24.0)


@pytest.mark.parametrize(
    "value",
    [
        {"translation": [0, float("nan"), 0]},
        {"scale_xyz": [0, 1, 1]},
        {"scale_xyz": [1, 1, 10001]},
        {"rotation_xyz_degrees": [0, 1]},
        {"scale_locked": "yes"},
    ],
)
def test_scene_placement_rejects_invalid_values(value) -> None:
    with pytest.raises(ValueError):
        normalize_scene_placement(value)
