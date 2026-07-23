from __future__ import annotations

import json
import multiprocessing
from pathlib import Path

import pytest

import apps.desktop.pipeline as pipeline_module
import apps.desktop.project_store as project_store_module
from apps.desktop.pipeline import PipelineController
from apps.desktop.project_session import AsyncIdentity, ProjectSession
from apps.desktop.project_store import (
    Project,
    ProjectDeleteError,
    ProjectStore,
    UnsafeProjectWorkspaceError,
)
from packages.file_lock import ProjectLockError


def _hold_run_lock(
    store_root: str, project_id: str, ready: object, release: object
) -> None:
    store = ProjectStore(store_root)
    with store.run_lock(project_id):
        ready.set()
        release.wait(15)


def test_new_projects_have_distinct_stable_internal_workspaces(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "metadata")
    library = tmp_path / "library"

    first = store.create("same display name", library)
    second = store.create("same display name", library)

    assert first.project_id != second.project_id
    assert first.root != second.root
    assert first.workspace_kind == second.workspace_kind == "isolated"
    assert Path(first.root) == library / ".gaussianos" / "projects" / first.project_id
    assert Path(second.root) == library / ".gaussianos" / "projects" / second.project_id
    assert ProjectStore(store.root).load(first.project_id).root == first.root
    assert ProjectStore(store.root).load(second.project_id).root == second.root


def test_two_projects_cannot_bind_the_same_internal_workspace(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "metadata")
    first = store.create("first", tmp_path / "library")
    second = store.create("second", tmp_path / "library")
    second.root = first.root

    with pytest.raises((ValueError, UnsafeProjectWorkspaceError)):
        store.save(second)

    assert store.load(second.project_id).root != first.root


def test_project_paths_isolate_every_mutable_surface(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "metadata")
    first = store.create("first", tmp_path / "library")
    second = store.create("second", tmp_path / "library")
    first_paths = store.paths(first)
    second_paths = store.paths(second)
    first_run = first_paths.run("run-first")
    second_run = second_paths.run("run-second")
    first_run.ensure()
    second_run.ensure()

    surfaces = (
        (first_paths.analysis, second_paths.analysis),
        (first_run.frames, second_run.frames),
        (first_run.training, second_run.training),
        (first_run.artifacts, second_run.artifacts),
        (first_run.staging, second_run.staging),
        (first_run.timeline, second_run.timeline),
        (first_run.exports, second_run.exports),
        (first_run.logs, second_run.logs),
        (first_run.temp, second_run.temp),
        (first_paths.viewer, second_paths.viewer),
    )
    for left, right in surfaces:
        assert left != right
        assert first_paths.contains(left)
        assert second_paths.contains(right)
        assert not first_paths.contains(right)
        assert not second_paths.contains(left)


def test_project_switch_transaction_clears_viewer_timeline_and_camera() -> None:
    session = ProjectSession()
    session.switch("project-a")
    session.viewer_project_id = "project-a"
    session.viewer_run_id = "run-a"
    session.timeline = [{"index": 1}]
    session.active_camera = 42
    session.viewer_selection = "scene-a"

    generation = session.switch("project-b")

    assert generation == 2
    assert session.project_id == "project-b"
    assert session.viewer_project_id is None
    assert session.viewer_run_id is None
    assert session.timeline == []
    assert session.active_camera is None
    assert session.viewer_selection is None


def test_late_viewer_pipeline_and_timeline_results_cannot_cross_projects() -> None:
    session = ProjectSession()
    generation_a = session.switch("project-a")
    session.begin_run("project-a", "run-a")
    identities = [
        AsyncIdentity("project-a", "run-a", generation_a, stage).payload()
        for stage in ("viewer", "train", "timeline")
    ]

    session.switch("project-b")

    assert all(not session.accepts(identity) for identity in identities)


def test_fast_a_b_a_switch_accepts_only_the_final_a_generation() -> None:
    session = ProjectSession()
    old_generation = session.switch("project-a")
    old_result = AsyncIdentity("project-a", "run-a", old_generation, "viewer").payload()
    session.switch("project-b")
    final_generation = session.switch("project-a")
    final_result = AsyncIdentity(
        "project-a", "run-a", final_generation, "viewer"
    ).payload()

    assert not session.accepts(old_result)
    assert session.accepts(final_result)


def test_cancelled_run_cannot_reactivate_from_a_late_result() -> None:
    session = ProjectSession()
    generation = session.switch("project-a")
    session.begin_run("project-a", "run-a")
    late = AsyncIdentity("project-a", "run-a", generation, "viewer").payload()

    session.cancel_run("project-a")
    session.finish_run("project-a", "run-a")

    assert not session.accepts(late)


def test_stale_pipeline_snapshot_cannot_replace_a_new_run(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "metadata")
    project = store.create("project", tmp_path / "library")
    controller = PipelineController(store, tmp_path / "legacy-artifacts")
    project.run_id = "run-old"
    project.status = "running"
    store.save(project)
    stale = store.load(project.project_id)
    store.update_project(
        project.project_id,
        lambda current: setattr(current, "run_id", "run-new"),
    )

    with pytest.raises(RuntimeError, match="stale run"):
        controller._persist(stale)

    assert store.load(project.project_id).run_id == "run-new"


def test_delete_non_current_project_only_moves_the_target(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "metadata")
    first = store.create("first", tmp_path / "library")
    second = store.create("second", tmp_path / "library")
    first_root, second_root = Path(first.root), Path(second.root)
    (second_root / "inputs" / "sentinel.txt").write_text("second", encoding="utf-8")

    deleted = store.delete(second.project_id)

    assert first_root.is_dir()
    assert store.load(first.project_id).project_id == first.project_id
    assert not second_root.exists()
    assert deleted.workspace_path is not None
    assert (deleted.workspace_path / "inputs" / "sentinel.txt").read_text(
        encoding="utf-8"
    ) == "second"
    assert [item.project_id for item in store.all()] == [first.project_id]


def test_delete_current_project_clears_active_presentation(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "metadata")
    project = store.create("current", tmp_path / "library")
    session = ProjectSession()
    session.switch(project.project_id)
    session.viewer_project_id = project.project_id
    session.viewer_run_id = "run-current"
    session.timeline = [{"index": 3}]
    session.active_camera = 7

    store.delete(project.project_id)
    assert session.remove_project(project.project_id)

    assert session.project_id == ""
    assert session.viewer_project_id is None
    assert session.viewer_run_id is None
    assert session.timeline == []
    assert session.active_camera is None


def test_running_project_cannot_be_deleted(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "metadata")
    project = store.create("running", tmp_path / "library")
    store.update_project(
        project.project_id, lambda current: setattr(current, "status", "running")
    )

    with pytest.raises(ProjectDeleteError, match="Running projects"):
        store.delete(project.project_id)

    assert Path(project.root).is_dir()
    assert store.load(project.project_id).status == "running"


def test_legacy_shared_delete_preserves_the_shared_workspace(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "metadata")
    shared = tmp_path / "legacy-shared"
    shared.mkdir()
    sentinel = shared / "do-not-delete.txt"
    sentinel.write_text("owned by multiple projects", encoding="utf-8")
    first = Project("legacy-a", "legacy a", str(shared))
    second = Project("legacy-b", "legacy b", str(shared))
    store.save(first)
    store.save(second)

    assert store.load(first.project_id).workspace_kind == "legacy_shared"
    with pytest.raises(UnsafeProjectWorkspaceError, match="read-only"):
        store.ensure_writable(first.project_id)

    deleted = store.delete(first.project_id)

    assert deleted.legacy_workspace_preserved
    assert deleted.workspace_path is None
    assert sentinel.read_text(encoding="utf-8") == "owned by multiple projects"
    remaining = store.load(second.project_id)
    assert remaining.workspace_kind == "legacy_shared"
    with pytest.raises(UnsafeProjectWorkspaceError, match="read-only"):
        store.ensure_writable(remaining)


def test_delete_metadata_failure_rolls_back_isolated_workspace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ProjectStore(tmp_path / "metadata")
    project = store.create("rollback", tmp_path / "library")
    metadata = store.root / f"{project.project_id}.json"
    workspace = Path(project.root)
    original_replace = project_store_module.os.replace

    def fail_metadata(source: str | Path, destination: str | Path) -> None:
        if Path(source) == metadata:
            raise PermissionError("simulated metadata move failure")
        original_replace(source, destination)

    monkeypatch.setattr(project_store_module.os, "replace", fail_metadata)
    with pytest.raises(ProjectDeleteError, match="delete failed"):
        store.delete(project.project_id)

    assert metadata.is_file()
    assert workspace.is_dir()
    assert store.load(project.project_id).project_id == project.project_id


def test_cross_process_run_lock_rejects_second_writer_and_recovers(
    tmp_path: Path,
) -> None:
    store = ProjectStore(tmp_path / "metadata")
    project = store.create("locked", tmp_path / "library")
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    release = context.Event()
    process = context.Process(
        target=_hold_run_lock,
        args=(str(store.root), project.project_id, ready, release),
    )
    process.start()
    try:
        assert ready.wait(10)
        with pytest.raises(ProjectLockError):
            with store.run_lock(project.project_id):
                pass
        controller = PipelineController(store, tmp_path / "legacy-artifacts")
        with pytest.raises(ProjectLockError):
            controller.set_profile(project.project_id, "quality")
    finally:
        release.set()
        process.join(15)
        if process.is_alive():
            process.terminate()
            process.join(5)

    assert process.exitcode == 0
    lock_path = store.root / ".locks" / f"{project.project_id}.run.lock"
    assert lock_path.is_file()
    with store.run_lock(project.project_id):
        pass


def test_restart_preserves_project_and_artifact_ownership(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "metadata")
    first = store.create("first", tmp_path / "library")
    second = store.create("second", tmp_path / "library")
    for project, run_id in ((first, "run-first"), (second, "run-second")):
        paths = store.paths(project).run(run_id)
        paths.ensure()
        artifact = paths.artifacts / "artifacts" / f"artifact-{project.project_id}"
        artifact.mkdir(parents=True)
        store.update_project(
            project.project_id,
            lambda current, rid=run_id, value=artifact: (
                setattr(current, "run_id", rid),
                current.stages.setdefault("train", project_store_module.StageState(
                    status="succeeded", artifact_paths=[str(value)]
                )),
            ),
        )

    restarted = ProjectStore(store.root)
    restored_first = restarted.load(first.project_id)
    restored_second = restarted.load(second.project_id)

    first_artifact = restored_first.stages["train"].artifact_paths[0]
    second_artifact = restored_second.stages["train"].artifact_paths[0]
    assert restarted.paths(restored_first).contains(first_artifact)
    assert restarted.paths(restored_second).contains(second_artifact)
    assert not restarted.paths(restored_first).contains(second_artifact)
    assert not restarted.paths(restored_second).contains(first_artifact)


def test_sampling_analysis_is_staged_then_atomically_published(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = ProjectStore(tmp_path / "metadata")
    project = store.create("video", tmp_path / "library")
    source = tmp_path / "source.mp4"
    source.write_bytes(b"test-only-video-placeholder")

    def prepare(current: Project) -> None:
        current.input_path = str(source)
        current.input_kind = "video"
        current.sampling = {
            "source_total_frames": 30,
            "duration_seconds": 3.0,
            "fps": 10.0,
            "width": 640,
            "height": 480,
        }

    store.update_project(project.project_id, prepare)
    controller = PipelineController(store, tmp_path / "legacy-artifacts")
    controller.set_sampling_config(
        project.project_id, "target_count", 10, 1.0, "seconds"
    )
    paths = store.paths(project.project_id)
    old = paths.analysis / "old-valid.txt"
    old.write_text("old", encoding="utf-8")

    def fake_analyze(
        _source: str,
        _probe: object,
        _config: object,
        _ffmpeg: str,
        output: Path,
    ) -> dict[str, object]:
        output.mkdir(parents=True)
        thumbnail = output / "thumb-0001.jpg"
        thumbnail.write_bytes(b"new")
        return {
            "analysis_status": "complete",
            "timeline": [{"thumbnail_path": str(thumbnail)}],
            "warnings": [],
        }

    monkeypatch.setattr(pipeline_module, "analyze_video", fake_analyze)
    analyzed = controller.analyze_sampling(project.project_id)

    thumbnail = Path(analyzed.sampling["timeline"][0]["thumbnail_path"])
    assert thumbnail == paths.analysis / "thumb-0001.jpg"
    assert thumbnail.read_bytes() == b"new"
    assert not old.exists()
    assert not list(paths.inputs.glob(".analysis.*.staging"))
    assert not list(paths.inputs.glob(".analysis.*.backup"))


def test_legacy_json_without_p3_fields_remains_readable(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "metadata")
    legacy_root = tmp_path / "legacy"
    legacy_root.mkdir()
    payload = {
        "project_id": "legacy-project",
        "name": "legacy",
        "root": str(legacy_root),
        "input_path": None,
        "input_kind": None,
        "profile": "balanced",
        "run_id": None,
        "status": "idle",
        "current_stage": None,
        "sampling": {},
        "stages": {},
        "warnings": [],
        "created_at": "2026-01-01T00:00:00+00:00",
        "updated_at": "2026-01-01T00:00:00+00:00",
    }
    (store.root / "legacy-project.json").write_text(
        json.dumps(payload), encoding="utf-8"
    )

    restored = store.load("legacy-project")

    assert restored.workspace_kind == "legacy"
    assert restored.library_root is None
    assert restored.root == str(legacy_root)
    assert any("compatibility mode" in warning for warning in restored.warnings)
