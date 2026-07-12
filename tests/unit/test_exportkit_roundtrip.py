from __future__ import annotations

import numpy as np
import pytest

from packages.exportkit import (
    gaussian_ply_to_scene_bundle,
    scene_bundle_to_gaussian_ply,
)
from packages.scene_bundle import write_scene_bundle


def test_scene_bundle_gaussian_ply_scene_bundle_round_trip(
    tmp_path, manifest_factory, gaussian_factory, cameras
):
    manifest = manifest_factory(3)
    source_gaussians = gaussian_factory(3)
    source_bundle = write_scene_bundle(
        tmp_path / "source.bundle",
        manifest,
        cameras=cameras,
        gaussians=source_gaussians,
    )

    ply_path = tmp_path / "scene.graphdeco-gs-v1.ply"
    scene_bundle_to_gaussian_ply(source_bundle, ply_path)
    restored_bundle = gaussian_ply_to_scene_bundle(
        ply_path,
        tmp_path / "restored.bundle",
        manifest=source_bundle.manifest,
        cameras=source_bundle.cameras,
    )

    np.testing.assert_array_equal(restored_bundle.gaussians.means, source_gaussians.means)
    np.testing.assert_array_equal(
        restored_bundle.gaussians.log_scales, source_gaussians.log_scales
    )
    np.testing.assert_array_equal(
        restored_bundle.gaussians.quats_wxyz, source_gaussians.quats_wxyz
    )
    np.testing.assert_array_equal(
        restored_bundle.gaussians.opacity_logits, source_gaussians.opacity_logits
    )
    np.testing.assert_array_equal(
        restored_bundle.gaussians.sh_coeffs, source_gaussians.sh_coeffs
    )
    np.testing.assert_array_equal(restored_bundle.cameras.camtoworlds, cameras.camtoworlds)
    assert restored_bundle.manifest.model_dump(exclude={"payloads"}) == (
        source_bundle.manifest.model_dump(exclude={"payloads"})
    )


def test_ply_import_rejects_manifest_color_space_mismatch(
    tmp_path, manifest_factory, gaussian_factory
):
    source_bundle = write_scene_bundle(
        tmp_path / "source.bundle",
        manifest_factory(3),
        gaussians=gaussian_factory(3),
    )
    ply_path = tmp_path / "scene.graphdeco-gs-v1.ply"
    scene_bundle_to_gaussian_ply(source_bundle, ply_path)
    mismatched_manifest = source_bundle.manifest.model_copy(
        update={"color_space": "srgb"}
    )

    with pytest.raises(ValueError, match="color space"):
        gaussian_ply_to_scene_bundle(
            ply_path,
            tmp_path / "must-not-exist.bundle",
            manifest=mismatched_manifest,
        )
    assert not (tmp_path / "must-not-exist.bundle").exists()
