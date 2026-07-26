"""Validated project-directory resolution for desktop UI actions."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Literal

from .project_store import Project, ProjectStore


DirectoryKind = Literal[
    "workspace",
    "library",
    "run",
    "inputs",
    "artifacts",
    "exports",
]


class DirectoryResolutionError(RuntimeError):
    """A requested project directory cannot be opened safely."""

    status = "unavailable"


class StaleActiveRunError(DirectoryResolutionError):
    """The durable active run no longer has an owned run directory."""

    status = "stale"


@dataclass(frozen=True, slots=True)
class DirectoryTarget:
    project_id: str
    run_id: str | None
    kind: DirectoryKind
    path: Path


@dataclass(frozen=True, slots=True)
class DirectoryOpenResult:
    status: Literal["opened", "unavailable", "stale", "failed", "duplicate"]
    message: str
    path: Path | None = None

    @property
    def opened(self) -> bool:
        return self.status == "opened"


class ProjectDirectoryService:
    """Resolve IDs through ProjectStore and open only validated local paths."""

    def __init__(
        self,
        store: ProjectStore,
        open_local_path: Callable[[Path], bool],
        *,
        cooldown_seconds: float = 0.75,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.store = store
        self._open_local_path = open_local_path
        self._cooldown_seconds = max(0.0, cooldown_seconds)
        self._clock = clock
        self._recent: dict[tuple[str, str, str], float] = {}
        self._guard = threading.Lock()

    @staticmethod
    def _active_run(project: Project, requested_run_id: str | None) -> str:
        active_run_id = str(project.run_id or "")
        requested = str(requested_run_id or "")
        if requested and requested != active_run_id:
            raise StaleActiveRunError(
                f"Requested run {requested} is no longer the active run for this project."
            )
        if not active_run_id:
            raise DirectoryResolutionError("This project has no active run.")
        return active_run_id

    @staticmethod
    def _require_directory(path: Path, message: str) -> Path:
        if not path.is_dir():
            raise DirectoryResolutionError(message)
        return path.resolve()

    def resolve(
        self,
        project_id: str,
        kind: DirectoryKind,
        run_id: str | None = None,
    ) -> DirectoryTarget:
        project = self.store.load(project_id)
        paths = self.store.paths(project)

        if kind == "workspace":
            destination = self._require_directory(
                paths.workspace, "The project workspace is missing."
            )
            if not paths.contains(destination):
                raise DirectoryResolutionError(
                    "The project workspace failed its ownership check."
                )
            return DirectoryTarget(project.project_id, None, kind, destination)

        if kind == "library":
            if not project.library_root:
                raise DirectoryResolutionError(
                    "This legacy/shared project has no managed library directory; "
                    "open its project workspace instead."
                )
            destination = self._require_directory(
                paths.library_root, "The project library directory is missing."
            )
            # store.paths() validated the isolated project marker and the exact
            # library/.gaussianos/projects/project_id ownership relationship.
            return DirectoryTarget(project.project_id, None, kind, destination)

        active_run_id = self._active_run(project, run_id)
        run_paths = paths.run(active_run_id)
        if not run_paths.root.is_dir():
            raise StaleActiveRunError(
                f"Active run {active_run_id} is stale: its run directory is missing."
            )

        if kind == "run":
            destination = run_paths.root
            unavailable = "The active run directory is missing."
        elif kind == "inputs":
            destination = run_paths.frames
            unavailable = "The active run has no input frames."
        elif kind == "artifacts":
            destination = run_paths.artifacts
            unavailable = "The active run has no artifacts."
        elif kind == "exports":
            destination = run_paths.exports
            unavailable = "尚无导出结果"
        else:
            raise DirectoryResolutionError(f"Unknown directory target: {kind}")

        destination = self._require_directory(destination, unavailable)
        if not paths.contains(destination):
            raise DirectoryResolutionError(
                "The requested directory is outside the owning project workspace."
            )
        if kind == "exports":
            try:
                has_export = next(destination.iterdir(), None) is not None
            except OSError as exc:
                raise DirectoryResolutionError(
                    f"Could not inspect the export directory: {exc}"
                ) from exc
            if not has_export:
                raise DirectoryResolutionError("尚无导出结果")
        return DirectoryTarget(project.project_id, active_run_id, kind, destination)

    def open(
        self,
        project_id: str,
        kind: DirectoryKind,
        run_id: str | None = None,
    ) -> DirectoryOpenResult:
        key = (str(project_id), str(run_id or ""), str(kind))
        now = self._clock()
        with self._guard:
            previous = self._recent.get(key)
            if previous is not None and now - previous < self._cooldown_seconds:
                return DirectoryOpenResult(
                    "duplicate", "Duplicate directory request ignored."
                )
            self._recent[key] = now

        try:
            target = self.resolve(project_id, kind, run_id)
        except StaleActiveRunError as exc:
            return DirectoryOpenResult("stale", str(exc))
        except Exception as exc:
            return DirectoryOpenResult("unavailable", str(exc))

        try:
            opened = bool(self._open_local_path(target.path))
        except Exception as exc:
            return DirectoryOpenResult(
                "failed",
                f"Could not open {kind} directory: {exc}",
                target.path,
            )
        if not opened:
            return DirectoryOpenResult(
                "failed",
                f"Windows could not open the {kind} directory.",
                target.path,
            )
        return DirectoryOpenResult(
            "opened",
            f"Opened {kind} directory: {target.path}",
            target.path,
        )
