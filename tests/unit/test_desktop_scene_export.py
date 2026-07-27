from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest

import apps.desktop.scene_export as scene_export_module
from apps.desktop.project_store import ProjectStore, StageState
from apps.desktop.scene_export import (
    SceneBundleExporter,
    SceneExportError,
    validate_scene_export,
)
from packages.contracts import NormalizationTransform
from packages.exportkit import (
    read_gaussian_ply_payload,
    read_pointcloud_ply_payload,
    write_gaussian_ply,
    write_pointcloud_ply,
)
from packages.quality.colmap import read_images_txt
from packages.scene_bundle import PointCloudTensors, write_scene_bundle


def _write_text(path: Path, value: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value, encoding="utf-8")


def _ready_project(
    tmp_path: Path,
    manifest_factory,
    gaussian_factory,
    cameras,
    *,
    name: str = "Scene A",
):
    store = ProjectStore(tmp_path / "metadata")
    project = store.create(name, tmp_path / "library")
    run_id = f"run-{project.project_id[:8]}"
    paths = store.paths(project)
    run = paths.run(run_id)
    run.ensure()

    transform = (
        (2.0, 0.0, 0.0, -4.0),
        (0.0, 2.0, 0.0, 6.0),
        (0.0, 0.0, 2.0, 1.0),
        (0.0, 0.0, 0.0, 1.0),
    )
    manifest = manifest_factory(3).model_copy(
        update={
            "normalization_transform": NormalizationTransform(
                source_to_scene=transform
            )
        }
    )
    gaussians = gaussian_factory(3)
    artifact = run.artifacts / "train-output"
    bundle = write_scene_bundle(
        artifact / "scene.scene-bundle",
        manifest,
        cameras=cameras,
        gaussians=gaussians,
    )
    gaussian_path = artifact / "scene.graphdeco-gs-v1.ply"
    write_gaussian_ply(
        gaussian_path,
        gaussians,
        manifest.spherical_harmonics,
        color_space=manifest.color_space,
    )
    source_points = PointCloudTensors(
        positions=np.array(
            [[2.0, -3.0, 1.0], [2.5, -2.0, 2.0], [1.5, -4.0, 0.0]],
            dtype=np.float32,
        ),
        normals=np.array(
            [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
            dtype=np.float32,
        ),
        colors_rgb=np.array(
            [[255, 0, 0], [0, 255, 0], [0, 0, 255]], dtype=np.uint8
        ),
    )
    pointcloud_path = run.exports / "scene.pointcloud.ply"
    write_pointcloud_ply(pointcloud_path, source_points)

    _write_text(
        run.training / "sparse" / "0" / "cameras.txt",
        "# cameras\n1 PINHOLE 640 480 800 810 320 240\n"
        "2 PINHOLE 640 480 805 815 320 240\n",
    )
    _write_text(
        run.training / "sparse" / "0" / "images.txt",
        "# images\n"
        "10 1 0 0 0 0 0 0 1 frame_000010.png\n\n"
        "20 1 0 0 0 -1 -2 -3 2 frame_000020.png\n\n",
    )
    timeline = {
        "schema_version": "gaussianos-camera-timeline/v1",
        "project_id": project.project_id,
        "run_id": run_id,
        "stage": "timeline",
        "records": [
            {
                "registration_status": "registered",
                "source_frame_index": 10,
                "timestamp_seconds": 0.5,
                "camera": {"image_name": "frame_000010.png"},
            },
            {
                "registration_status": "registered",
                "source_frame_index": 20,
                "timestamp_seconds": 1.0,
                "camera": {"image_name": "frame_000020.png"},
            },
        ],
    }
    _write_text(run.timeline_manifest, json.dumps(timeline))
    receipt = {
        "schema_version": "gaussianos-viewer-scene/v1",
        "project_id": project.project_id,
        "run_id": run_id,
        "generation": 3,
        "stage": "viewer",
        "bundle": str(bundle.root),
        "gaussian": str(gaussian_path),
        "pointcloud": str(pointcloud_path),
        "committed": True,
    }
    _write_text(paths.viewer_manifest, json.dumps(receipt))

    project.run_id = run_id
    project.status = "succeeded"
    project.stages = {
        "validate": StageState(
            "succeeded", [str(bundle.root), str(gaussian_path)]
        ),
        "export": StageState(
            "succeeded",
            [str(gaussian_path), str(pointcloud_path), str(bundle.root)],
        ),
    }
    store.save(project)
    return store, project, gaussians, source_points, np.asarray(transform)


def test_complete_scene_bundle_export_round_trip_and_alignment(
    tmp_path, manifest_factory, gaussian_factory, cameras
):
    store, project, gaussians, source_points, transform = _ready_project(
        tmp_path, manifest_factory, gaussian_factory, cameras
    )
    parent = tmp_path / "user-exports"
    parent.mkdir()

    result = SceneBundleExporter(store).export(
        project.project_id, project.run_id, parent
    )

    assert result.path.name == "Scene A_Export"
    assert {
        path.relative_to(result.path).as_posix()
        for path in result.path.rglob("*")
        if path.is_file()
    } == {
        "gaussian/scene_gaussian.ply",
        "pointcloud/scene_pointcloud.ply",
        "cameras/cameras.json",
        "cameras/cameras.csv",
        "cameras/colmap/cameras.txt",
        "cameras/colmap/images.txt",
        "cameras/colmap/points3D.txt",
        "scene_manifest.json",
    }
    restored_gaussians = read_gaussian_ply_payload(
        result.path / "gaussian" / "scene_gaussian.ply"
    )
    for field in (
        "means", "log_scales", "quats_wxyz", "opacity_logits", "sh_coeffs"
    ):
        np.testing.assert_array_equal(
            getattr(restored_gaussians, field), getattr(gaussians, field)
        )

    restored_points = read_pointcloud_ply_payload(
        result.path / "pointcloud" / "scene_pointcloud.ply"
    )
    homogeneous = np.column_stack(
        (source_points.positions, np.ones(len(source_points.positions)))
    )
    expected_points = (homogeneous @ transform.T)[:, :3].astype(np.float32)
    np.testing.assert_array_equal(restored_points.positions, expected_points)
    np.testing.assert_array_equal(restored_points.normals, source_points.normals)

    cameras_json = json.loads(
        (result.path / "cameras" / "cameras.json").read_text(encoding="utf-8")
    )
    assert [item["image_name"] for item in cameras_json["cameras"]] == [
        "frame_000010.png", "frame_000020.png"
    ]
    assert cameras_json["cameras"][0]["source_frame_index"] == 10
    assert cameras_json["cameras"][0]["timestamp"] == 0.5
    for index, record in enumerate(cameras_json["cameras"]):
        forward = np.asarray(record["world_from_camera"])
        inverse = np.asarray(record["camera_from_world"])
        np.testing.assert_allclose(forward @ inverse, np.eye(4), atol=1e-7)
        np.testing.assert_allclose(forward, cameras.camtoworlds[index], atol=1e-7)

    colmap_poses = read_images_txt(
        result.path / "cameras" / "colmap" / "images.txt"
    )
    for index, pose in enumerate(colmap_poses):
        np.testing.assert_allclose(
            pose.cam2world, cameras.camtoworlds[index], atol=1e-6
        )

    verified = validate_scene_export(result.path)
    assert verified["counts"] == {"gaussians": 3, "points": 3, "cameras": 2}
    manifest = verified["manifest"]
    assert manifest["project_id"] == project.project_id
    assert manifest["run_id"] == project.run_id
    assert manifest["world_from_reconstruction"] == transform.tolist()
    assert manifest["world_transform_applied"]["viewer_display_transform"] == "not_applied"
    assert set(manifest["sha256"]) == {
        value for value in manifest["files"].values()
    }


def test_export_rejects_cross_project_and_stale_run(
    tmp_path, manifest_factory, gaussian_factory, cameras
):
    first_store, first, *_ = _ready_project(
        tmp_path / "first", manifest_factory, gaussian_factory, cameras
    )
    _, second, *_ = _ready_project(
        tmp_path / "second", manifest_factory, gaussian_factory, cameras
    )
    parent = tmp_path / "exports"
    parent.mkdir()
    exporter = SceneBundleExporter(first_store)

    with pytest.raises(SceneExportError, match="Stale run"):
        exporter.export(first.project_id, second.run_id, parent)
    with pytest.raises(SceneExportError, match="Project is unavailable"):
        exporter.export(second.project_id, second.run_id, parent)
    assert list(parent.iterdir()) == []


def test_interrupted_export_leaves_no_partial_bundle(
    tmp_path, manifest_factory, gaussian_factory, cameras
):
    store, project, *_ = _ready_project(
        tmp_path, manifest_factory, gaussian_factory, cameras
    )
    parent = tmp_path / "exports"
    parent.mkdir()
    calls = 0

    def interrupt() -> None:
        nonlocal calls
        calls += 1
        if calls == 4:
            raise InterruptedError("test interruption")

    with pytest.raises(InterruptedError, match="test interruption"):
        SceneBundleExporter(store).export(
            project.project_id, project.run_id, parent, checkpoint=interrupt
        )

    assert not (parent / "Scene A_Export").exists()
    assert not list(parent.glob(".*.staging-*"))


def test_final_publish_uses_staging_and_os_replace(
    tmp_path, manifest_factory, gaussian_factory, cameras, monkeypatch
):
    store, project, *_ = _ready_project(
        tmp_path, manifest_factory, gaussian_factory, cameras
    )
    parent = tmp_path / "exports"
    parent.mkdir()
    replacements: list[tuple[Path, Path]] = []
    real_replace = scene_export_module.os.replace

    def record_replace(source, destination):
        replacements.append((Path(source), Path(destination)))
        return real_replace(source, destination)

    monkeypatch.setattr(scene_export_module.os, "replace", record_replace)
    result = SceneBundleExporter(store).export(
        project.project_id, project.run_id, parent
    )

    source, destination = replacements[-1]
    assert ".staging-" in source.name
    assert destination == result.path
    assert result.path.is_dir()
