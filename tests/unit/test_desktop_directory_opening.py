from __future__ import annotations

from pathlib import Path

import pytest

from apps.desktop.directory_opening import ProjectDirectoryService
from apps.desktop.main import project_view
from apps.desktop.project_store import (
    Project,
    ProjectStore,
    UnsafeProjectWorkspaceError,
)


def _set_active_run(store: ProjectStore, project_id: str, run_id: str) -> None:
    def update(project: Project) -> None:
        project.run_id = run_id

    store.update_project(project_id, update)


def test_new_project_library_workspace_and_library_display_are_consistent(
    tmp_path: Path,
) -> None:
    store = ProjectStore(tmp_path / "state" / "projects")
    library = tmp_path / "chosen-library"
    library.mkdir()

    project = store.create("New project", library)
    restored = store.load(project.project_id)
    view = project_view(restored)
    expected_workspace = (
        library / ".gaussianos" / "projects" / project.project_id
    ).resolve()

    assert Path(restored.root) == expected_workspace
    assert Path(restored.library_root or "") == library.resolve()
    assert Path(view["workspace_path"]) == expected_workspace
    assert Path(view["library_path"]) == library.resolve()
    assert (expected_workspace / ".gaussianos-project.json").is_file()
    assert (expected_workspace / "inputs" / "analysis").is_dir()
    assert (expected_workspace / "runs").is_dir()
    assert (expected_workspace / "viewer").is_dir()
    assert view["active_run_status"] == "none"


def test_directory_service_opens_only_existing_owned_project_paths(
    tmp_path: Path,
) -> None:
    store = ProjectStore(tmp_path / "state" / "projects")
    library = tmp_path / "library"
    library.mkdir()
    project = store.create("Owned", library)
    opened: list[Path] = []
    service = ProjectDirectoryService(
        store,
        lambda path: opened.append(path) is None,
        cooldown_seconds=0,
    )

    workspace_result = service.open(project.project_id, "workspace")
    library_result = service.open(project.project_id, "library")

    assert workspace_result.opened
    assert library_result.opened
    assert opened == [
        Path(project.root).resolve(),
        library.resolve(),
    ]


def test_missing_exports_and_stale_active_run_never_call_shell(
    tmp_path: Path,
) -> None:
    store = ProjectStore(tmp_path / "state" / "projects")
    library = tmp_path / "library"
    library.mkdir()
    project = store.create("Runs", library)
    opened: list[Path] = []
    service = ProjectDirectoryService(
        store,
        lambda path: opened.append(path) is None,
        cooldown_seconds=0,
    )
    run_id = "run-test-stale"
    _set_active_run(store, project.project_id, run_id)

    stale = service.open(project.project_id, "exports", run_id)
    assert stale.status == "stale"
    assert "stale" in stale.message.lower()
    assert opened == []
    assert project_view(store.load(project.project_id))["active_run_status"] == "stale"

    run_paths = store.paths(project.project_id).run(run_id)
    run_paths.ensure()
    empty = service.open(project.project_id, "exports", run_id)
    assert empty.status == "unavailable"
    assert empty.message == "尚无导出结果"
    assert opened == []

    export = run_paths.exports / "scene.ply"
    export.write_bytes(b"ply")
    available = service.open(project.project_id, "exports", run_id)
    assert available.opened
    assert opened == [run_paths.exports.resolve()]


def test_run_inputs_artifacts_and_duplicate_request_handling(
    tmp_path: Path,
) -> None:
    store = ProjectStore(tmp_path / "state" / "projects")
    library = tmp_path / "library"
    library.mkdir()
    project = store.create("Run paths", library)
    run_id = "run-owned"
    _set_active_run(store, project.project_id, run_id)
    run_paths = store.paths(project.project_id).run(run_id)
    run_paths.ensure()
    run_paths.frames.mkdir()
    opened: list[Path] = []
    now = [1.0]
    service = ProjectDirectoryService(
        store,
        lambda path: opened.append(path) is None,
        cooldown_seconds=1.0,
        clock=lambda: now[0],
    )

    assert service.open(project.project_id, "run", run_id).opened
    assert service.open(project.project_id, "inputs", run_id).opened
    assert service.open(project.project_id, "artifacts", run_id).opened
    duplicate = service.open(project.project_id, "artifacts", run_id)

    assert duplicate.status == "duplicate"
    assert opened == [
        run_paths.root.resolve(),
        run_paths.frames.resolve(),
        run_paths.artifacts.resolve(),
    ]


def test_legacy_shared_opening_is_read_only_and_has_no_synthetic_library(
    tmp_path: Path,
) -> None:
    store = ProjectStore(tmp_path / "state" / "projects")
    shared = tmp_path / "legacy-shared"
    shared.mkdir()
    sentinel = shared / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    store.save(Project("legacy-a", "Legacy A", str(shared)))
    store.save(Project("legacy-b", "Legacy B", str(shared)))
    opened: list[Path] = []
    service = ProjectDirectoryService(
        store,
        lambda path: opened.append(path) is None,
        cooldown_seconds=0,
    )
    before = sorted(path.relative_to(shared) for path in shared.rglob("*"))

    workspace = service.open("legacy-a", "workspace")
    library = service.open("legacy-a", "library")
    after = sorted(path.relative_to(shared) for path in shared.rglob("*"))

    assert store.load("legacy-a").workspace_kind == "legacy_shared"
    assert workspace.opened
    assert library.status == "unavailable"
    assert "legacy/shared" in library.message
    assert opened == [shared.resolve()]
    assert before == after == [Path("keep.txt")]
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_single_legacy_project_is_read_only_without_creating_directories(
    tmp_path: Path,
) -> None:
    store = ProjectStore(tmp_path / "state" / "projects")
    legacy = tmp_path / "legacy"
    legacy.mkdir()
    sentinel = legacy / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")
    store.save(Project("legacy-one", "Legacy", str(legacy)))
    before = sorted(path.relative_to(legacy) for path in legacy.rglob("*"))

    with pytest.raises(UnsafeProjectWorkspaceError, match="read-only"):
        store.ensure_writable("legacy-one")

    after = sorted(path.relative_to(legacy) for path in legacy.rglob("*"))
    assert store.load("legacy-one").workspace_kind == "legacy"
    assert before == after == [Path("keep.txt")]
