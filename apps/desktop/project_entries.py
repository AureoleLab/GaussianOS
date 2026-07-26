"""User-facing project-name entries backed by isolated UUID workspaces."""

from __future__ import annotations

import os
import re
import subprocess
import threading
import unicodedata
from pathlib import Path

from .project_store import Project, ProjectStore


ENTRY_DIRECTORY_NAME = "GaussianOS Projects"
_INVALID_FILENAME = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


class ProjectEntryError(RuntimeError):
    """A friendly project entry cannot be created or changed safely."""


def safe_project_entry_name(name: str) -> str:
    """Return a readable filename without changing the durable project name."""

    normalized = unicodedata.normalize("NFC", str(name))
    normalized = _INVALID_FILENAME.sub("-", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip(" .")
    if not normalized:
        normalized = "Untitled Project"
    if normalized.upper() in _RESERVED_NAMES:
        normalized += " Project"
    return normalized[:96].rstrip(" .") or "Untitled Project"


def _same_path(first: Path, second: Path) -> bool:
    return os.path.normcase(str(first.resolve())) == os.path.normcase(
        str(second.resolve())
    )


def _is_directory_link(path: Path) -> bool:
    is_junction = getattr(os.path, "isjunction", lambda _path: False)
    return path.is_symlink() or bool(is_junction(path))


def project_display_path(project: Project) -> Path:
    """Return an existing friendly entry, or its non-mutating display hint."""

    if project.workspace_kind != "isolated" or not project.library_root:
        return Path(project.root).resolve()
    root = Path(project.library_root).resolve() / ENTRY_DIRECTORY_NAME
    workspace = Path(project.root).resolve()
    if root.is_dir():
        for candidate in root.iterdir():
            if ProjectEntryService._points_to(candidate, workspace):
                return candidate
    return root / safe_project_entry_name(project.name)


class ProjectEntryService:
    """Maintain readable directory links without renaming owned workspaces."""

    def __init__(self, store: ProjectStore) -> None:
        self.store = store
        self._guard = threading.RLock()

    def reconcile(self) -> list[str]:
        """Ensure readable entries for existing isolated projects.

        One damaged project must not prevent the application from starting or
        hide every other project in the same library.
        """

        warnings: list[str] = []
        for project in self.store.all():
            if project.workspace_kind != "isolated":
                continue
            try:
                self.ensure(project)
            except Exception as exc:
                warnings.append(
                    f"Project folder entry warning ({project.project_id}): {exc}"
                )
        return warnings

    @staticmethod
    def root_for(project: Project) -> Path:
        if not project.library_root:
            raise ProjectEntryError(
                "Legacy/shared projects do not have a managed project-name entry."
            )
        return Path(project.library_root).resolve() / ENTRY_DIRECTORY_NAME

    @staticmethod
    def _points_to(entry: Path, workspace: Path) -> bool:
        if not os.path.lexists(entry) or not _is_directory_link(entry):
            return False
        try:
            return _same_path(entry, workspace)
        except OSError:
            return False

    def entries_for(self, project_or_id: Project | str) -> list[Path]:
        project = (
            self.store.load(project_or_id)
            if isinstance(project_or_id, str)
            else project_or_id
        )
        if project.workspace_kind != "isolated" or not project.library_root:
            return []
        paths = self.store.paths(project)
        root = self.root_for(project)
        if not root.is_dir():
            return []
        return [
            candidate
            for candidate in root.iterdir()
            if self._points_to(candidate, paths.workspace)
        ]

    @staticmethod
    def _create_link(entry: Path, workspace: Path) -> None:
        if os.name == "nt":
            completed = subprocess.run(
                [
                    "cmd.exe",
                    "/d",
                    "/c",
                    "mklink",
                    "/J",
                    str(entry),
                    str(workspace),
                ],
                check=False,
                capture_output=True,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout).strip()
                raise ProjectEntryError(
                    f"Windows could not create the project-name entry: {detail}"
                )
            return
        entry.symlink_to(workspace, target_is_directory=True)

    @staticmethod
    def _remove_link(entry: Path) -> None:
        if not os.path.lexists(entry):
            return
        if not _is_directory_link(entry):
            raise ProjectEntryError(
                f"Refusing to remove a non-link project entry: {entry}"
            )
        if getattr(os.path, "isjunction", lambda _path: False)(entry):
            entry.rmdir()
        else:
            entry.unlink()

    def ensure(self, project_or_id: Project | str) -> Path:
        project = (
            self.store.load(project_or_id)
            if isinstance(project_or_id, str)
            else project_or_id
        )
        if project.workspace_kind != "isolated":
            raise ProjectEntryError(
                "Legacy/shared projects remain read-only and use their existing path."
            )
        paths = self.store.paths(project)
        paths.validate_isolated_identity()
        root = self.root_for(project)
        base_name = safe_project_entry_name(project.name)

        with self._guard:
            root.mkdir(parents=True, exist_ok=True)
            existing = self.entries_for(project)
            for entry in existing:
                if entry.name == base_name:
                    return entry

            candidate = root / base_name
            suffix = 2
            while os.path.lexists(candidate):
                if self._points_to(candidate, paths.workspace):
                    break
                candidate = root / f"{base_name} ({suffix})"
                suffix += 1

            if not os.path.lexists(candidate):
                self._create_link(candidate, paths.workspace)
            if not self._points_to(candidate, paths.workspace):
                raise ProjectEntryError(
                    "The project-name entry does not resolve to its owned workspace."
                )

            for old_entry in existing:
                if old_entry != candidate:
                    self._remove_link(old_entry)
            return candidate

    def remove(self, project_or_id: Project | str) -> list[Path]:
        project = (
            self.store.load(project_or_id)
            if isinstance(project_or_id, str)
            else project_or_id
        )
        with self._guard:
            entries = self.entries_for(project)
            for entry in entries:
                self._remove_link(entry)
            return entries

    def remove_captured(self, project: Project, entries: list[Path]) -> None:
        """Remove links validated before an atomic workspace move."""

        expected_parent = self.root_for(project)
        with self._guard:
            for entry in entries:
                if entry.parent != expected_parent:
                    raise ProjectEntryError(
                        f"Refusing to remove an entry outside the library view: {entry}"
                    )
                self._remove_link(entry)
