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


def test_viewer_uses_only_registered_real_timeline_cameras(tmp_path, manifest_factory, gaussian_factory, cameras, pointcloud):
    bundle, ply, points, _ = _scene(tmp_path, manifest_factory, gaussian_factory, cameras, pointcloud)
    real = {
        "image_id": 44,
        "image_name": "frame_000060.png",
        "cam2world": [[1, 0, 0, 3], [0, 1, 0, 4], [0, 0, 1, 5], [0, 0, 0, 1]],
        "intrinsics": [[900, 0, 640], [0, 910, 360], [0, 0, 1]],
        "width": 1280,
        "height": 720,
    }
    second = {**real, "image_id": 45, "image_name": "frame_000062.png", "cam2world": [[1, 0, 0, 6], [0, 1, 0, 7], [0, 0, 1, 8], [0, 0, 0, 1]]}
    timeline = [
        {"source_frame_index": 60, "selected_order": 0, "registration_status": "registered", "colmap_image_id": 44, "camera": real},
        {"source_frame_index": 61, "selected_order": 1, "registration_status": "unregistered", "colmap_image_id": None, "camera": None},
        {"source_frame_index": 62, "selected_order": 2, "registration_status": "registered", "colmap_image_id": 45, "camera": second},
    ]
    scene = load_viewer_scene(bundle, ply, points, timeline)
    assert scene.camera_count == 2
    assert scene.cameras[0]["colmap_image_id"] == 44
    assert scene.cameras[0]["source_frame_index"] == 60
    assert scene.cameras[0]["coordinate_space"] == "scene_normalized"
    assert scene.cameras[0]["colmap_cam2world"][0][3] == 3
    assert scene.cameras[0]["cam2world"][0][3] == 0
    assert scene.camera_positions == ((0.0, 0.0, 0.0), (1.0, 2.0, 3.0))


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


def test_web_viewer_exposes_real_camera_and_free_view_bridge() -> None:
    html = (Path(__file__).parents[2] / "apps" / "desktop" / "viewer_web" / "index.html").read_text(encoding="utf-8")
    assert "window.viewerCamera={setCamera:setCameraByImageId,setFreeView:freeView" in html
    assert "cameraProjection(currentCamera)" in html
    assert "currentCamera.width/currentCamera.height" in html
    assert "highlightCamera(rec)" in html
