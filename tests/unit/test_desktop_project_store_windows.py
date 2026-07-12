from __future__ import annotations

import threading
from pathlib import Path

import pytest

from apps.desktop.pipeline import PipelineController
from apps.desktop.project_store import Project, ProjectStore, StageState
import apps.desktop.project_store as project_store_module


def _project(store: ProjectStore, root: Path) -> Project:
    return store.create("concurrency", root / "project")


def test_update_project_serializes_two_concurrent_writers(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "projects")
    second_store = ProjectStore(tmp_path / "projects")
    project = _project(store, tmp_path)
    barrier = threading.Barrier(3)

    def writer(label: str, writer_store: ProjectStore) -> None:
        barrier.wait()
        for index in range(100):
            def apply(current: Project) -> None:
                state = current.stages.setdefault(label, StageState())
                state.metrics["counter"] = index
            writer_store.update_project(project.project_id, apply)

    threads = [
        threading.Thread(target=writer, args=("one", store)),
        threading.Thread(target=writer, args=("two", second_store)),
    ]
    for thread in threads: thread.start()
    barrier.wait()
    for thread in threads: thread.join()

    loaded = store.load(project.project_id)
    assert loaded.stages["one"].metrics["counter"] == 99
    assert loaded.stages["two"].metrics["counter"] == 99


def test_save_serializes_two_concurrent_snapshots_without_tmp_leaks(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "projects")
    project = _project(store, tmp_path)
    barrier = threading.Barrier(3)

    def writer(status: str) -> None:
        barrier.wait()
        for _ in range(30):
            snapshot = store.load(project.project_id)
            snapshot.status = status
            store.save(snapshot)

    threads = [threading.Thread(target=writer, args=(status,)) for status in ("ready", "idle")]
    for thread in threads: thread.start()
    barrier.wait()
    for thread in threads: thread.join()
    assert store.load(project.project_id).status in {"ready", "idle"}
    assert not list((tmp_path / "projects").glob(".*.tmp"))


def test_gui_poll_reads_while_background_writes_one_thousand_times(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "projects")
    project = _project(store, tmp_path)
    failures: list[BaseException] = []
    done = threading.Event()

    def writer() -> None:
        try:
            for index in range(1000):
                def apply(current: Project) -> None:
                    current.stages.setdefault("ingest", StageState()).metrics["counter"] = index
                store.update_project(project.project_id, apply)
        except BaseException as exc: failures.append(exc)
        finally: done.set()

    def reader() -> None:
        try:
            while not done.is_set():
                assert store.load(project.project_id).project_id == project.project_id
        except BaseException as exc: failures.append(exc)

    writer_thread, reader_thread = threading.Thread(target=writer), threading.Thread(target=reader)
    writer_thread.start(); reader_thread.start()
    writer_thread.join(); reader_thread.join()
    assert not failures
    assert store.load(project.project_id).stages["ingest"].metrics["counter"] == 999
    assert not list((tmp_path / "projects").glob(".*.tmp"))


def test_replace_permission_error_retries_then_cleans_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = ProjectStore(tmp_path / "projects")
    project = _project(store, tmp_path)
    original = project_store_module.os.replace
    attempts = 0

    def flaky_replace(source: str | Path, destination: str | Path) -> None:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise PermissionError(5, "Access is denied", str(destination))
        original(source, destination)

    monkeypatch.setattr(project_store_module.os, "replace", flaky_replace)
    store.update_project(project.project_id, lambda current: setattr(current, "status", "ready"))
    assert attempts == 3
    assert store.load(project.project_id).status == "ready"
    assert not list((tmp_path / "projects").glob(".*.tmp"))


def test_exhausted_replace_failure_leaves_no_tmp_and_pipeline_reports_failed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = ProjectStore(tmp_path / "projects")
    project = _project(store, tmp_path)
    images = tmp_path / "images"; images.mkdir()
    for index in range(3): (images / f"{index}.png").write_bytes(b"not decoded")
    controller = PipelineController(store, tmp_path / "artifacts")
    controller.import_input(project.project_id, images)
    events: list[tuple[str, str]] = []

    def always_locked(_source: str | Path, destination: str | Path) -> None:
        raise PermissionError(5, "simulated permanent sharing violation", str(destination))

    monkeypatch.setattr(project_store_module.os, "replace", always_locked)
    result = controller.run(project.project_id, lambda kind, message, _payload: events.append((kind, message)))
    assert result.status == "failed"
    assert any(kind == "persistence_failed" for kind, _ in events)
    assert not list((tmp_path / "projects").glob(".*.tmp"))


def test_restart_recovers_stale_running_task_as_interrupted(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "projects")
    project = _project(store, tmp_path)
    store.update_project(project.project_id, lambda current: setattr(current, "status", "running"))

    controller = PipelineController(store, tmp_path / "artifacts")
    recovered = controller.recover_interrupted_projects()

    assert [item.project_id for item in recovered] == [project.project_id]
    persisted = store.load(project.project_id)
    assert persisted.status == "interrupted"
    assert any("Desktop restarted" in warning for warning in persisted.warnings)
