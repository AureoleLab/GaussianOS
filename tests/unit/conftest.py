from __future__ import annotations

import numpy as np
import pytest

from packages.contracts import (
    InputFileHash,
    PluginProvenance,
    SceneBundleManifest,
    SphericalHarmonicsSpec,
)
from packages.scene_bundle import CameraTensors, GaussianTensors, PointCloudTensors


def make_manifest(degree: int = 3) -> SceneBundleManifest:
    reconstruction = PluginProvenance(
        plugin_id="recon_colmap",
        plugin_version="1.0.0",
        upstream_commit="1" * 40,
        config_sha256="2" * 64,
        weight_sha256=(),
        code_license="BSD-3-Clause",
        checkpoint_license="NO_CHECKPOINT",
    )
    trainer = PluginProvenance(
        plugin_id="train_gsplat",
        plugin_version="1.0.0",
        upstream_commit="3" * 40,
        config_sha256="4" * 64,
        weight_sha256=(),
        code_license="Apache-2.0",
        checkpoint_license="NO_CHECKPOINT",
    )
    return SceneBundleManifest(
        world_unit="scene_units",
        has_metric_scale=False,
        spherical_harmonics=SphericalHarmonicsSpec(degree=degree),
        color_space="linear_srgb",
        input_files=(
            InputFileHash(logical_path="inputs/frame-0001.png", sha256="5" * 64),
        ),
        reconstruction_plugin=reconstruction,
        trainer_plugin=trainer,
    )


def make_gaussians(degree: int = 3, count: int = 3) -> GaussianTensors:
    coefficient_count = (degree + 1) ** 2
    means = np.array(
        [[0.25, -0.5, 1.0], [2.0, 3.0, -4.0], [-1.25, 0.0, 8.5]],
        dtype=np.float32,
    )[:count]
    log_scales = np.array(
        [[-2.0, -1.0, -0.5], [0.0, 0.1, 0.2], [1.0, -3.0, -4.0]],
        dtype=np.float32,
    )[:count]
    root_half = np.float32(np.sqrt(0.5))
    quats = np.array(
        [[1.0, 0.0, 0.0, 0.0], [root_half, 0.0, root_half, 0.0], [0.0, 1.0, 0.0, 0.0]],
        dtype=np.float32,
    )[:count]
    opacity = np.array([[-2.5], [0.0], [3.25]], dtype=np.float32)[:count]
    sh = (
        np.arange(count * coefficient_count * 3, dtype=np.float32).reshape(
            count, coefficient_count, 3
        )
        / np.float32(100.0)
        - np.float32(0.5)
    )
    return GaussianTensors(
        means=means,
        log_scales=log_scales,
        quats_wxyz=quats,
        opacity_logits=opacity,
        sh_coeffs=sh,
    )


def make_cameras() -> CameraTensors:
    camtoworlds = np.repeat(np.eye(4, dtype=np.float32)[None, :, :], 2, axis=0)
    camtoworlds[1, :3, 3] = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    intrinsics = np.array(
        [
            [[800.0, 0.0, 320.0], [0.0, 810.0, 240.0], [0.0, 0.0, 1.0]],
            [[805.0, 0.0, 320.0], [0.0, 815.0, 240.0], [0.0, 0.0, 1.0]],
        ],
        dtype=np.float32,
    )
    return CameraTensors(
        camtoworlds=camtoworlds,
        intrinsics=intrinsics,
        image_sizes=np.array([[640, 480], [640, 480]], dtype=np.int32),
        camera_ids=np.array([100, 101], dtype=np.int64),
    )


@pytest.fixture
def manifest_factory():
    return make_manifest


@pytest.fixture
def gaussian_factory():
    return make_gaussians


@pytest.fixture
def cameras() -> CameraTensors:
    return make_cameras()


@pytest.fixture
def pointcloud() -> PointCloudTensors:
    return PointCloudTensors(
        positions=np.array(
            [[0.0, 0.5, 1.0], [-2.0, 3.0, 4.5], [8.0, -1.0, 2.0]],
            dtype=np.float32,
        ),
        normals=np.array(
            [[0.0, 0.0, 1.0], [0.0, 1.0, 0.0], [1.0, 0.0, 0.0]],
            dtype=np.float32,
        ),
        colors_rgb=np.array(
            [[255, 0, 17], [8, 128, 64], [0, 1, 2]], dtype=np.uint8
        ),
    )
