from __future__ import annotations

import json
from pathlib import Path

import pytest

import apps.desktop.project_store as project_store_module
from apps.desktop.pipeline import PipelineController
from apps.desktop.project_store import (
    Project,
    ProjectLifecycleError,
    ProjectStore,
    ProjectStoreError,
    StageState,
    UnsafeProjectWorkspaceError,
)


def _completed_project(
    store: ProjectStore, library: Path, name: str = "complete"
) -> tuple[Project, dict[str, Path]]:
    project = store.create(name, library)
    paths = store.paths(project)
    run = paths.run("run-valid")
    run.ensure()
    run.frames.mkdir(parents=True, exist_ok=True)
    frames = run.frames
    (frames / "frame.png").write_bytes(b"frame")
    reconstruction = run.artifacts / "artifacts" / "reconstruction"
    reconstruction.mkdir(parents=True)
    (reconstruction / "model.txt").write_text("model", encoding="utf-8")
    training = run.artifacts / "artifacts" / "training"
    bundle = training / "scene.scene-bundle"
    bundle.mkdir(parents=True)
    gaussian = training / "scene.graphdeco-gs-v1.ply"
    gaussian.write_bytes(b"ply")
    export = run.exports / "scene.graphdeco-gs-v1.ply"
    export.write_bytes(b"export")
    run.timeline_manifest.write_text(
        json.dumps(
            {
                "schema_version": "gaussianos-camera-timeline/v1",
                "project_id": project.project_id,
                "run_id": "run-valid",
                "stage": "timeline",
                "records": [],
            }
        ),
        encoding="utf-8",
    )
    paths.viewer_manifest.write_text(
        json.dumps(
            {
                "schema_version": "gaussianos-viewer-scene/v1",
                "project_id": project.project_id,
                "run_id": "run-valid",
                "stage": "viewer",
                "bundle": str(bundle),
                "gaussian": str(gaussian),
                "pointcloud": None,
                "committed": True,
            }
        ),
        encoding="utf-8",
    )

    def finish(current: Project) -> None:
        current.input_path = str(library / "source.mp4")
        current.input_kind = "video"
        current.status = "succeeded"
        current.run_id = "run-valid"
        current.sampling = {"selection_config_hash": "hash", "camera_timeline": []}
        current.stages = {
            "ingest": StageState("succeeded", [str(frames)]),
            "colmap": StageState("succeeded", [str(reconstruction)]),
            "fallback": StageState("skipped"),
            "train": StageState("succeeded", [str(training)]),
            "validate": StageState("succeeded", [str(bundle), str(gaussian)]),
            "export": StageState("succeeded", [str(export)]),
        }

    project, _ = store.update_project(project.project_id, finish)
    return project, {
        "frames": frames,
        "reconstruction": reconstruction,
        "training": training,
        "export": export,
        "bundle": bundle,
        "gaussian": gaussian,
    }


def test_rename_changes_only_display_name(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "metadata")
    project = store.create("before", tmp_path / "library")
    original = (project.project_id, project.root, project.library_root)

    renamed = store.rename(project.project_id, "after")

    assert renamed.name == "after"
    assert (renamed.project_id, renamed.root, renamed.library_root) == original


def test_input_copy_has_new_identity_and_independent_files(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "metadata")
    source = store.create("source", tmp_path / "library")
    source_paths = store.paths(source)
    (source_paths.inputs / "input.txt").write_text("source", encoding="utf-8")
    store.update_project(
        source.project_id,
        lambda current: (
            setattr(current, "input_path", str(tmp_path / "video.mp4")),
            setattr(current, "status", "ready"),
            current.sampling.update({"selection_config_hash": "same"}),
        ),
    )

    copied = store.duplicate(source.project_id, "copy", mode="inputs")
    copied_input = store.paths(copied).inputs / "input.txt"
    copied_input.write_text("copy", encoding="utf-8")

    assert copied.project_id != source.project_id
    assert copied.root != source.root
    assert copied.run_id is None
    assert copied.stages == {}
    assert (source_paths.inputs / "input.txt").read_text(encoding="utf-8") == "source"


def test_complete_copy_rebases_current_viewer_receipt(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "metadata")
    source, _ = _completed_project(store, tmp_path / "library")

    copied = store.duplicate(source.project_id, "complete copy", mode="complete")
    copied_paths = store.paths(copied)
    receipt = json.loads(copied_paths.viewer_manifest.read_text(encoding="utf-8"))

    assert copied.status == "succeeded"
    assert copied.run_id == source.run_id
    assert receipt["project_id"] == copied.project_id
    assert copied_paths.contains(receipt["bundle"])
    assert copied_paths.contains(receipt["gaussian"])
    assert Path(receipt["bundle"]).is_dir()
    assert Path(receipt["gaussian"]).is_file()


def test_archive_unarchive_and_restart_are_consistent(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "metadata")
    project = store.create("archive", tmp_path / "library")

    archived = store.set_archived(project.project_id, True)
    restarted = ProjectStore(store.root).load(project.project_id)
    restored = store.set_archived(project.project_id, False)

    assert archived.archived and archived.archived_at
    assert restarted.archived and restarted.root == project.root
    assert not restored.archived and restored.archived_at is None


def test_soft_delete_restore_and_permanent_delete_are_targeted(
    tmp_path: Path,
) -> None:
    store = ProjectStore(tmp_path / "metadata")
    first = store.create("first", tmp_path / "library")
    second = store.create("second", tmp_path / "library")
    second_root = Path(second.root)
    (second_root / "payload.bin").write_bytes(b"x" * 32)

    store.delete(second.project_id)
    entry = store.trash_entries()[0]
    restored = store.restore(second.project_id)
    assert Path(restored.root).is_dir()
    store.delete(second.project_id)
    released = store.purge(second.project_id)

    assert entry.estimated_bytes >= 32
    assert released >= 32
    assert store.load(first.project_id).project_id == first.project_id
    assert Path(first.root).is_dir()
    assert not second_root.exists()
    assert store.trash_entries() == []


@pytest.mark.parametrize(
    ("target", "kept", "removed"),
    [
        ("reconstruction", ("frames",), ("reconstruction", "training", "export")),
        ("training", ("frames", "reconstruction"), ("training", "export")),
        ("exports", ("frames", "reconstruction", "training"), ("export",)),
    ],
)
def test_selective_cleanup_preserves_inputs_and_other_project(
    tmp_path: Path,
    target: str,
    kept: tuple[str, ...],
    removed: tuple[str, ...],
) -> None:
    store = ProjectStore(tmp_path / "metadata")
    project, artifacts = _completed_project(store, tmp_path / "library", target)
    other = store.create("other", tmp_path / "library")
    other_sentinel = Path(other.root) / "keep.txt"
    other_sentinel.write_text("keep", encoding="utf-8")
    controller = PipelineController(store, tmp_path / "legacy-artifacts")

    cleaned = controller.cleanup_project(project.project_id, target)

    assert cleaned.status == "ready"
    assert cleaned.run_id is None
    assert cleaned.stages["ingest"].status == "succeeded"
    assert all(artifacts[name].exists() for name in kept)
    assert all(not artifacts[name].exists() for name in removed)
    assert other_sentinel.read_text(encoding="utf-8") == "keep"
    assert not store.paths(cleaned).viewer_manifest.exists()


def test_viewer_timeline_cleanup_invalidates_current_publication(
    tmp_path: Path,
) -> None:
    store = ProjectStore(tmp_path / "metadata")
    project, artifacts = _completed_project(store, tmp_path / "library")
    paths = store.paths(project)
    timeline = paths.run(project.run_id or "").timeline_manifest
    controller = PipelineController(store, tmp_path / "legacy-artifacts")

    cleaned = controller.cleanup_project(project.project_id, "viewer")

    assert cleaned.run_id is None
    assert cleaned.status == "ready"
    assert cleaned.stages["export"].status == "pending"
    assert cleaned.sampling["camera_mapping_stale"] is True
    assert not paths.viewer_manifest.exists()
    assert not timeline.exists()
    assert artifacts["training"].exists()
    assert artifacts["export"].exists()


def test_cleanup_metadata_failure_rolls_files_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ProjectStore(tmp_path / "metadata")
    project, artifacts = _completed_project(store, tmp_path / "library")
    controller = PipelineController(store, tmp_path / "legacy-artifacts")

    def fail_update(_project_id: str, _update: object) -> tuple[Project, None]:
        raise OSError("simulated metadata failure")

    monkeypatch.setattr(store, "update_project", fail_update)
    with pytest.raises(OSError, match="simulated"):
        controller.cleanup_project(project.project_id, "training")

    assert artifacts["training"].is_dir()
    assert artifacts["export"].is_file()
    assert store.paths(project).viewer_manifest.is_file()
    assert not list(store.paths(project).transactions.glob("cleanup-*"))


def test_legacy_shared_lifecycle_never_removes_shared_files(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "metadata")
    shared = tmp_path / "shared"
    shared.mkdir()
    sentinel = shared / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    store.save(Project("legacy-a", "A", str(shared)))
    store.save(Project("legacy-b", "B", str(shared)))
    controller = PipelineController(store, tmp_path / "artifacts")

    with pytest.raises(UnsafeProjectWorkspaceError):
        store.duplicate("legacy-a", "copy")
    with pytest.raises(ProjectStoreError):
        controller.cleanup_project("legacy-a", "training")
    store.delete("legacy-a")
    store.purge("legacy-a")

    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_startup_recovers_owned_cleanup_transaction_but_preserves_unknown(
    tmp_path: Path,
) -> None:
    store = ProjectStore(tmp_path / "metadata")
    project = store.create("recovery", tmp_path / "library")
    paths = store.paths(project)
    source = paths.viewer_manifest
    source.write_text("valid", encoding="utf-8")
    transaction = paths.transactions / "cleanup-crash"
    transaction.mkdir()
    quarantine = transaction / "000-scene.json"
    source.replace(quarantine)
    (transaction / "transaction.json").write_text(
        json.dumps(
            {
                "schema_version": "gaussianos-cleanup-transaction/v1",
                "project_id": project.project_id,
                "target": "viewer",
                "phase": "moved",
                "moves": [
                    {"source": str(source), "quarantine": str(quarantine)}
                ],
            }
        ),
        encoding="utf-8",
    )
    unknown = paths.transactions / "user-data"
    unknown.mkdir()
    (unknown / "keep.txt").write_text("keep", encoding="utf-8")

    actions = PipelineController(
        ProjectStore(store.root), tmp_path / "artifacts"
    ).recover_lifecycle_residuals()

    assert source.read_text(encoding="utf-8") == "valid"
    assert not transaction.exists()
    assert (unknown / "keep.txt").read_text(encoding="utf-8") == "keep"
    assert actions


def test_complete_copy_rejects_stale_or_foreign_viewer_receipt(
    tmp_path: Path,
) -> None:
    store = ProjectStore(tmp_path / "metadata")
    project, _ = _completed_project(store, tmp_path / "library")
    receipt = store.paths(project).viewer_manifest
    payload = json.loads(receipt.read_text(encoding="utf-8"))
    payload["project_id"] = "foreign"
    receipt.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ProjectLifecycleError, match="current valid run"):
        store.duplicate(project.project_id, "unsafe copy", mode="complete")


def test_duplicate_metadata_failure_removes_unpublished_copy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ProjectStore(tmp_path / "metadata")
    project = store.create("source", tmp_path / "library")
    original_replace = project_store_module.os.replace

    def fail_duplicate_metadata(source: str | Path, destination: str | Path) -> None:
        target = Path(destination)
        if target.parent == store.root and target.suffix == ".json":
            raise PermissionError("simulated duplicate metadata failure")
        original_replace(source, destination)

    monkeypatch.setattr(
        project_store_module.os, "replace", fail_duplicate_metadata
    )
    with pytest.raises(ProjectStoreError, match="atomically save"):
        store.duplicate(project.project_id, "copy", mode="inputs")

    assert store.all() == [store.load(project.project_id)]
    projects_root = Path(project.root).parent
    assert [item.name for item in projects_root.iterdir()] == [project.project_id]


def test_profile_change_invalidates_image_project_viewer_run(
    tmp_path: Path,
) -> None:
    store = ProjectStore(tmp_path / "metadata")
    project, _ = _completed_project(store, tmp_path / "library")
    store.update_project(
        project.project_id,
        lambda current: setattr(current, "input_kind", "images"),
    )
    controller = PipelineController(store, tmp_path / "artifacts")

    changed = controller.set_profile(project.project_id, "quality")

    assert changed.status == "ready"
    assert changed.run_id is None
    assert changed.sampling["camera_mapping_stale"] is True
    assert changed.stages["validate"].status == "stale"
    assert changed.stages["export"].status == "stale"
