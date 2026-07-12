from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from apps.desktop.main import project_view
from apps.desktop.pipeline import PipelineController, RuntimePaths, STAGES
from apps.desktop.project_store import Project, ProjectStore, StageState
from packages.plugin_sdk import StageStatus


def _runtime(tmp_path: Path) -> RuntimePaths:
    colmap = tmp_path / "colmap.exe"; colmap.write_bytes(b"test")
    return RuntimePaths(colmap, "ffmpeg", tmp_path / "map-python", tmp_path / "gs-python", tmp_path, tmp_path, tmp_path, tmp_path, tmp_path, tmp_path)


def _controller(tmp_path: Path):
    store = ProjectStore(tmp_path / "projects")
    project = store.create("status", tmp_path / "work")
    project.run_id = "test"
    store.save(project)
    return PipelineController(store, tmp_path / "artifacts", _runtime(tmp_path)), store, project


def test_colmap_success_persists_fallback_skipped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    controller, store, project = _controller(tmp_path)
    images = tmp_path / "images"; images.mkdir(); (images / "1.png").write_bytes(b"x")
    artifact = tmp_path / "reconstruction"; artifact.mkdir()
    monkeypatch.setattr(controller, "_manifest", lambda _: SimpleNamespace(plugin_id="recon_colmap", plugin_version="1"))
    monkeypatch.setattr(controller, "_run_worker", lambda *args: SimpleNamespace(
        result=SimpleNamespace(status=StageStatus.SUCCEEDED, quality_report=SimpleNamespace(metrics={}), error=None),
        committed_artifacts=[SimpleNamespace(path=artifact)],
    ))
    assert controller._reconstruct(project, images, SimpleNamespace(is_cancelled=False), None) == artifact
    restored = store.load(project.project_id)
    assert restored.stages["colmap"].status == "succeeded"
    assert restored.stages["fallback"].status == "skipped"


def test_colmap_failure_enters_fallback_required_before_fallback(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    controller, store, project = _controller(tmp_path)
    images = tmp_path / "images"; images.mkdir(); (images / "1.png").write_bytes(b"x")
    artifact = tmp_path / "fallback"; artifact.mkdir()
    monkeypatch.setattr(controller, "_manifest", lambda _: SimpleNamespace(plugin_id="recon_colmap", plugin_version="1"))
    monkeypatch.setattr(controller, "_run_worker", lambda *args: SimpleNamespace(result=SimpleNamespace(status=StageStatus.FAILED, quality_report=None, error=SimpleNamespace(message="quality gate")), committed_artifacts=[]))
    def fallback(current, *_):
        assert current.stages["colmap"].status == "fallback_required"
        return artifact
    monkeypatch.setattr(controller, "_fallback", fallback)
    assert controller._reconstruct(project, images, SimpleNamespace(is_cancelled=False), None) == artifact
    assert store.load(project.project_id).stages["colmap"].status == "fallback_required"


def test_success_invariant_rejects_pending_or_running_stage():
    project = Project("id", "name", ".", status="running")
    project.stages = {name: StageState(status="succeeded") for name in STAGES}
    project.stages["fallback"].status = "pending"
    with pytest.raises(RuntimeError, match="non-terminal"):
        PipelineController._normalize_success(project)


def test_success_invariant_accepts_completed_fallback_path():
    project = Project("id", "name", ".", status="running")
    project.stages = {name: StageState(status="succeeded") for name in STAGES}
    project.stages["colmap"].status = "fallback_required"
    PipelineController._normalize_success(project)
    project.stages["fallback"].status = "running"
    with pytest.raises(RuntimeError, match="non-terminal"):
        PipelineController._normalize_success(project)


def test_succeeded_project_is_always_presented_at_one_hundred_percent():
    project = Project("id", "name", ".", status="succeeded")
    project.stages = {name: StageState(status="succeeded") for name in STAGES}
    project.stages["fallback"].status = "skipped"
    assert project_view(project)["progress"] == 1.0
