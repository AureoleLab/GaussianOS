from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from apps.desktop.viewer import activate_gaussians, load_viewer_scene
from packages.contracts import SphericalHarmonicsSpec
from packages.exportkit import write_gaussian_ply, write_pointcloud_ply
from packages.scene_bundle import write_scene_bundle


def _scene(tmp_path, manifest_factory, gaussian_factory, cameras, pointcloud):
    gaussians = gaussian_factory(3)
    bundle = tmp_path / "scene.scene-bundle"
    ply = tmp_path / "scene.graphdeco-gs-v1.ply"
    points = tmp_path / "scene.pointcloud.ply"
    write_scene_bundle(bundle, manifest_factory(3), cameras=cameras, gaussians=gaussians)
    write_gaussian_ply(ply, gaussians, SphericalHarmonicsSpec(degree=3), color_space="linear_srgb")
    write_pointcloud_ply(points, pointcloud)
    return bundle, ply, points, gaussians


def test_viewer_loads_validated_bundle_ply_and_camera_track(tmp_path, manifest_factory, gaussian_factory, cameras, pointcloud):
    bundle, ply, points, gaussians = _scene(tmp_path, manifest_factory, gaussian_factory, cameras, pointcloud)
    scene = load_viewer_scene(bundle, ply, points)
    assert scene.gaussian_count == len(gaussians.means)
    assert scene.camera_count == 2
    assert scene.sh_degree == 3
    assert scene.pointcloud_path == points.resolve()
    np.testing.assert_allclose(scene.bounds_min, np.quantile(gaussians.means, 0.01, axis=0))


def test_viewer_reports_load_failure_for_mismatched_artifacts(tmp_path, manifest_factory, gaussian_factory, cameras, pointcloud):
    bundle, _, points, _ = _scene(tmp_path, manifest_factory, gaussian_factory, cameras, pointcloud)
    other = gaussian_factory(3, count=2)
    ply = tmp_path / "other.graphdeco-gs-v1.ply"
    write_gaussian_ply(ply, other, SphericalHarmonicsSpec(degree=3), color_space="linear_srgb")
    with pytest.raises(ValueError, match="counts do not match"):
        load_viewer_scene(bundle, ply, points)


def test_viewer_accepts_standard_graphdeco_and_pointcloud_ply(tmp_path, manifest_factory, gaussian_factory, cameras, pointcloud):
    bundle, ply, points, gaussians = _scene(tmp_path, manifest_factory, gaussian_factory, cameras, pointcloud)
    for path in (ply, points):
        payload = path.read_bytes()
        split = payload.index(b"end_header\n") + len(b"end_header\n")
        header = b"\n".join(
            line for line in payload[:split].splitlines()
            if not line.startswith(b"comment gaussian_factory_format")
        ) + b"\n"
        path.write_bytes(header + payload[split:])
    scene = load_viewer_scene(bundle, ply, points)
    assert scene.gaussian_count == len(gaussians.means)


def test_gaussian_parameter_activation_matches_contract():
    scales, opacity, quats = activate_gaussians(
        np.array([[0.0, np.log(2.0), np.log(0.5)]], dtype=np.float32),
        np.array([[0.0]], dtype=np.float32),
        np.array([[2.0, 0.0, 0.0, 0.0]], dtype=np.float32),
    )
    np.testing.assert_allclose(scales, [[1.0, 2.0, 0.5]])
    np.testing.assert_allclose(opacity, [[0.5]])
    np.testing.assert_allclose(quats, [[1.0, 0.0, 0.0, 0.0]])


def test_gaussian_activation_rejects_zero_quaternion():
    with pytest.raises(ValueError, match="zero length"):
        activate_gaussians(
            np.zeros((1, 3), dtype=np.float32),
            np.zeros((1, 1), dtype=np.float32),
            np.zeros((1, 4), dtype=np.float32),
        )
