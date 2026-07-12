from __future__ import annotations

import json

import numpy as np
import pytest

from packages.scene_bundle import (
    GaussianTensors,
    SceneBundleIOError,
    TensorValidationError,
    load_scene_bundle,
    write_scene_bundle,
)


def test_safetensors_scene_bundle_round_trip(
    tmp_path, manifest_factory, gaussian_factory, cameras
):
    destination = tmp_path / "scene.bundle"
    source_gaussians = gaussian_factory(3)
    bundle = write_scene_bundle(
        destination,
        manifest_factory(3),
        cameras=cameras,
        gaussians=source_gaussians,
    )

    assert bundle.root == destination.absolute()
    assert bundle.manifest.payloads.cameras is not None
    assert bundle.manifest.payloads.gaussians is not None
    assert bundle.manifest.payloads.cameras.sha256
    assert bundle.manifest.payloads.gaussians.sha256
    np.testing.assert_array_equal(bundle.cameras.camtoworlds, cameras.camtoworlds)
    np.testing.assert_array_equal(bundle.gaussians.means, source_gaussians.means)
    np.testing.assert_array_equal(bundle.gaussians.sh_coeffs, source_gaussians.sh_coeffs)

    persisted = json.loads((destination / "manifest.json").read_text(encoding="utf-8"))
    assert persisted["payloads"]["gaussians"]["tensors"]["sh_coeffs"]["shape"] == [
        3,
        16,
        3,
    ]
    assert persisted["payloads"]["gaussians"]["tensors"]["sh_coeffs"][
        "dtype"
    ] == "float32"


def test_scene_bundle_detects_tampered_safetensors(
    tmp_path, manifest_factory, gaussian_factory
):
    destination = tmp_path / "scene.bundle"
    write_scene_bundle(destination, manifest_factory(), gaussians=gaussian_factory())
    gaussian_path = destination / "gaussians.safetensors"
    payload = bytearray(gaussian_path.read_bytes())
    payload[-1] ^= 1
    gaussian_path.write_bytes(payload)

    with pytest.raises(SceneBundleIOError, match="SHA-256 mismatch"):
        load_scene_bundle(destination)


def test_scene_bundle_commit_is_immutable(
    tmp_path, manifest_factory, gaussian_factory
):
    destination = tmp_path / "scene.bundle"
    write_scene_bundle(destination, manifest_factory(), gaussians=gaussian_factory())
    with pytest.raises(FileExistsError):
        write_scene_bundle(destination, manifest_factory(), gaussians=gaussian_factory())


def test_scene_bundle_rejects_sh_degree_mismatch(
    tmp_path, manifest_factory, gaussian_factory
):
    with pytest.raises(SceneBundleIOError, match="SH degree"):
        write_scene_bundle(
            tmp_path / "scene.bundle", manifest_factory(2), gaussians=gaussian_factory(3)
        )


def test_gaussian_tensor_validation_rejects_non_unit_quaternion(gaussian_factory):
    valid = gaussian_factory()
    invalid_quaternions = valid.quats_wxyz.copy()
    invalid_quaternions[0] = [2.0, 0.0, 0.0, 0.0]
    with pytest.raises(TensorValidationError, match="unit quaternions"):
        GaussianTensors(
            means=valid.means,
            log_scales=valid.log_scales,
            quats_wxyz=invalid_quaternions,
            opacity_logits=valid.opacity_logits,
            sh_coeffs=valid.sh_coeffs,
        )


def test_gaussian_tensor_validation_rejects_activated_scale_overflow(
    gaussian_factory,
):
    valid = gaussian_factory()
    invalid_scales = valid.log_scales.copy()
    invalid_scales[0, 0] = 100.0
    with pytest.raises(TensorValidationError, match=r"exp\(log_scales\)"):
        GaussianTensors(
            means=valid.means,
            log_scales=invalid_scales,
            quats_wxyz=valid.quats_wxyz,
            opacity_logits=valid.opacity_logits,
            sh_coeffs=valid.sh_coeffs,
        )


def test_gaussian_tensor_validation_rejects_saturated_float32_opacity(
    gaussian_factory,
):
    valid = gaussian_factory()
    saturated_logits = valid.opacity_logits.copy()
    saturated_logits[0, 0] = 100.0
    with pytest.raises(TensorValidationError, match="strictly within"):
        GaussianTensors(
            means=valid.means,
            log_scales=valid.log_scales,
            quats_wxyz=valid.quats_wxyz,
            opacity_logits=saturated_logits,
            sh_coeffs=valid.sh_coeffs,
        )
