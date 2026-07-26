from __future__ import annotations

import os
from pathlib import Path

from apps.desktop.project_entries import (
    ENTRY_DIRECTORY_NAME,
    ProjectEntryService,
    safe_project_entry_name,
)
from apps.desktop.project_store import ProjectStore


def test_readable_entries_preserve_uuid_workspaces_and_resolve_collisions(
    tmp_path: Path,
) -> None:
    store = ProjectStore(tmp_path / "state" / "projects")
    library = tmp_path / "library"
    library.mkdir()
    first = store.create("Courtyard Scan", library)
    second = store.create("Courtyard Scan", library)
    entries = ProjectEntryService(store)

    first_entry = entries.ensure(first)
    second_entry = entries.ensure(second)

    assert first_entry.name == "Courtyard Scan"
    assert second_entry.name == "Courtyard Scan (2)"
    assert first_entry.parent == second_entry.parent == (
        library / ENTRY_DIRECTORY_NAME
    ).resolve()
    assert first_entry.resolve() == Path(first.root).resolve()
    assert second_entry.resolve() == Path(second.root).resolve()
    assert Path(first.root).name == first.project_id
    assert Path(second.root).name == second.project_id


def test_rename_replaces_only_the_owned_entry(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "state" / "projects")
    library = tmp_path / "library"
    library.mkdir()
    project = store.create("Before", library)
    entries = ProjectEntryService(store)
    old_entry = entries.ensure(project)
    collision = old_entry.parent / "After"
    collision.mkdir()
    sentinel = collision / "keep.txt"
    sentinel.write_text("keep", encoding="utf-8")

    renamed = store.rename(project.project_id, "After")
    new_entry = entries.ensure(renamed)

    assert new_entry.name == "After (2)"
    assert new_entry.resolve() == Path(project.root).resolve()
    assert not os.path.lexists(old_entry)
    assert collision.is_dir()
    assert sentinel.read_text(encoding="utf-8") == "keep"


def test_soft_delete_removes_only_a_captured_name_entry(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "state" / "projects")
    library = tmp_path / "library"
    library.mkdir()
    project = store.create("Trash me", library)
    entries = ProjectEntryService(store)
    entry = entries.ensure(project)
    captured = entries.entries_for(project)

    entries.remove_captured(project, captured)
    deleted = store.delete(project.project_id)

    assert deleted.workspace_path is not None
    assert deleted.workspace_path.is_dir()
    assert not os.path.lexists(entry)

    restored = store.restore(project.project_id)
    restored_entry = entries.ensure(restored)
    assert restored_entry.name == "Trash me"
    assert restored_entry.resolve() == Path(restored.root).resolve()


def test_reconcile_creates_readable_entries_for_existing_projects(
    tmp_path: Path,
) -> None:
    store = ProjectStore(tmp_path / "state" / "projects")
    library = tmp_path / "library"
    library.mkdir()
    first = store.create("既有项目", library)
    second = store.create("Existing project", library)

    warnings = ProjectEntryService(store).reconcile()

    assert warnings == []
    entry_root = library / ENTRY_DIRECTORY_NAME
    assert (entry_root / "既有项目").resolve() == Path(first.root).resolve()
    assert (entry_root / "Existing project").resolve() == Path(second.root).resolve()


def test_project_entry_names_are_unicode_readable_and_windows_safe() -> None:
    assert safe_project_entry_name("  庭院 / 扫描  ") == "庭院 - 扫描"
    assert safe_project_entry_name("CON") == "CON Project"
    assert safe_project_entry_name("...") == "Untitled Project"
