from pathlib import Path

from apps.desktop.project_store import ProjectStore, StageState


def test_project_state_is_durable_and_atomic(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "projects")
    created = store.create("demo", tmp_path / "demo")
    created.profile = "quality"
    created.stages["train"] = StageState(status="succeeded", artifact_paths=[str(tmp_path)])
    store.save(created)

    restored = ProjectStore(tmp_path / "projects").load(created.project_id)
    assert restored.name == "demo"
    assert restored.profile == "quality"
    assert restored.stages["train"].status == "succeeded"
    assert not list((tmp_path / "projects").glob(".*.tmp"))
