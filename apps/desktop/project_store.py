"""Durable, Windows-safe project/task state owned by the desktop control plane."""

from __future__ import annotations

import errno
import json
import os
import shutil
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar
from uuid import uuid4

from packages.file_lock import FileLock, ProjectLockError

from .project_paths import PROJECT_MARKER, ProjectPaths, isolated_workspace


REPLACE_BACKOFF_SECONDS = (0.05, 0.1, 0.2, 0.4, 0.8)
_LOCKS_GUARD = threading.Lock()
_PROJECT_LOCKS: dict[tuple[str, str], threading.RLock] = {}


class ProjectStoreError(RuntimeError):
    """Raised when a durable project-state operation cannot complete."""


class UnsafeProjectWorkspaceError(ProjectStoreError):
    """Raised when legacy/shared ownership cannot be established safely."""


class ProjectDeleteError(ProjectStoreError):
    """Raised when a project cannot be moved to the private trash."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_sharing_violation(exc: OSError) -> bool:
    """Return true for Windows access/sharing errors worth a bounded retry."""
    return (
        isinstance(exc, PermissionError)
        or getattr(exc, "winerror", None) in {5, 32, 33}
        or getattr(exc, "errno", None) in {errno.EACCES, errno.EPERM}
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    """Durably replace ``path`` without retaining an open source handle.

    The temporary file is deliberately a sibling of its destination: Windows
    only guarantees an atomic replacement on the same volume.  Its handle is
    closed before every ``os.replace`` attempt.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    data = (json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n").encode("utf-8")
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())

        for attempt, delay in enumerate((*REPLACE_BACKOFF_SECONDS, None), start=1):
            try:
                # No file object is live here.  This matters for Windows where
                # an otherwise harmless read handle prevents replacement.
                os.replace(temporary, path)
                return
            except OSError as exc:
                if not _is_sharing_violation(exc) or delay is None:
                    raise ProjectStoreError(
                        f"could not atomically save project state after {attempt} replace attempts: {exc}"
                    ) from exc
                time.sleep(delay)
    finally:
        # Includes exhausted retries and failures while writing the temporary.
        temporary.unlink(missing_ok=True)


@dataclass(slots=True)
class StageState:
    status: str = "pending"
    artifact_paths: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    updated_at: str = field(default_factory=_now)


@dataclass(slots=True)
class Project:
    project_id: str
    name: str
    root: str
    input_path: str | None = None
    input_kind: str | None = None
    profile: str = "balanced"
    run_id: str | None = None
    status: str = "idle"
    current_stage: str | None = None
    sampling: dict[str, Any] = field(default_factory=dict)
    stages: dict[str, StageState] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)
    library_root: str | None = None
    workspace_kind: str = "legacy"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Project":
        stages = {name: StageState(**state) for name, state in value.get("stages", {}).items()}
        return cls(**{**value, "stages": stages})


@dataclass(frozen=True, slots=True)
class DeletedProject:
    project_id: str
    metadata_path: Path
    workspace_path: Path | None
    legacy_workspace_preserved: bool


T = TypeVar("T")


class ProjectStore:
    """One atomically replaced JSON document per project.

    Every operation for the same root/project id shares one process-local
    ``RLock``, including operations through separately constructed stores.  New
    state transitions must use ``update_project`` so loading, modifying and
    writing are one critical section.
    """

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._root_key = os.path.normcase(str(self.root))

    def _path(self, project_id: str) -> Path:
        if not project_id or any(part in project_id for part in ("/", "\\", "..")):
            raise ValueError("unsafe project_id")
        return self.root / f"{project_id}.json"

    def _lock(self, project_id: str) -> threading.RLock:
        key = (self._root_key, project_id)
        with _LOCKS_GUARD:
            return _PROJECT_LOCKS.setdefault(key, threading.RLock())

    def _operation_lock(
        self, project_id: str, operation: str, *, timeout: float = 0.0
    ) -> FileLock:
        return FileLock(
            self.root / ".locks" / f"{project_id}.{operation}.lock",
            operation=operation,
            project_id=project_id,
            timeout=timeout,
        )

    def run_lock(self, project_id: str, *, timeout: float = 0.0) -> FileLock:
        self._path(project_id)
        return self._operation_lock(project_id, "run", timeout=timeout)

    def delete_lock(self, project_id: str, *, timeout: float = 0.0) -> FileLock:
        self._path(project_id)
        return self._operation_lock(project_id, "delete", timeout=timeout)

    def migration_lock(self, project_id: str, *, timeout: float = 0.0) -> FileLock:
        self._path(project_id)
        return self._operation_lock(project_id, "migration", timeout=timeout)

    def _state_lock(self, project_id: str, *, timeout: float = 5.0) -> FileLock:
        return self._operation_lock(project_id, "state", timeout=timeout)

    @staticmethod
    def _root_key_for(project: Project) -> str:
        return os.path.normcase(str(Path(project.root).resolve()))

    def _raw_project(self, path: Path) -> Project:
        try:
            return Project.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, ValueError, TypeError) as exc:
            raise ProjectStoreError(f"could not read project state {path.stem}: {exc}") from exc

    def _classify(self, projects: list[Project]) -> list[Project]:
        roots: dict[str, list[Project]] = {}
        trashed_legacy_roots: set[str] = set()
        for path in self.root.glob(".trash/*/project.json"):
            try:
                deleted = self._raw_project(path)
            except ProjectStoreError:
                continue
            if deleted.workspace_kind != "isolated":
                trashed_legacy_roots.add(self._root_key_for(deleted))
        for project in projects:
            if project.workspace_kind != "isolated":
                roots.setdefault(self._root_key_for(project), []).append(project)
                if project.workspace_kind == "legacy":
                    warning = (
                        "Legacy workspace compatibility mode; its existing files "
                        "are not moved automatically."
                    )
                    if warning not in project.warnings:
                        project.warnings.append(warning)
        for root_key, shared in roots.items():
            if len(shared) < 2 and root_key not in trashed_legacy_roots:
                continue
            for project in shared:
                project.workspace_kind = "legacy_shared"
                warning = (
                    "Legacy/shared workspace detected; writes and recursive deletion "
                    "are blocked until the project is migrated explicitly."
                )
                if warning not in project.warnings:
                    project.warnings.append(warning)
        return projects

    def _assert_unique_workspace(self, project: Project) -> None:
        if project.workspace_kind != "isolated":
            return
        ProjectPaths.from_project(project).validate_isolated_identity()
        target = self._root_key_for(project)
        for path in self.root.glob("*.json"):
            if path.stem == project.project_id:
                continue
            other = self._raw_project(path)
            if self._root_key_for(other) == target:
                raise UnsafeProjectWorkspaceError(
                    f"workspace is already bound to project {other.project_id}"
                )

    def create(self, name: str, project_root: str | Path) -> Project:
        """Create an isolated project below a user-selected project library."""

        if not name.strip():
            raise ValueError("project name is required")
        project_id = uuid4().hex
        library_root = Path(project_root).resolve()
        workspace = isolated_workspace(library_root, project_id)
        workspace.parent.mkdir(parents=True, exist_ok=True)
        try:
            workspace.mkdir(exist_ok=False)
        except FileExistsError as exc:
            raise UnsafeProjectWorkspaceError(
                f"new project workspace already exists: {workspace}"
            ) from exc
        project = Project(
            project_id=project_id,
            name=name.strip(),
            root=str(workspace),
            library_root=str(library_root),
            workspace_kind="isolated",
        )
        metadata_created = False
        try:
            _write_json(
                workspace / PROJECT_MARKER,
                {
                    "schema_version": "gaussianos-project-workspace/v1",
                    "project_id": project_id,
                    "created_at": project.created_at,
                },
            )
            self.save(project)
            metadata_created = True
            ProjectPaths.from_project(project).ensure()
            return self.load(project_id)
        except Exception:
            if metadata_created:
                self._path(project_id).unlink(missing_ok=True)
            # This directory was allocated by this call for an unobservable UUID,
            # so rollback cannot remove pre-existing user data.
            shutil.rmtree(workspace, ignore_errors=True)
            raise

    def save(self, project: Project) -> Project:
        """Persist a fully prepared project under the project's shared lock.

        Existing callers should prefer ``update_project``.  ``save`` remains
        for initial creation and compatibility, but still cannot race another
        save/load for this project in this process.
        """
        with self._lock(project.project_id):
            with self._state_lock(project.project_id):
                self._assert_unique_workspace(project)
                project.updated_at = _now()
                _write_json(self._path(project.project_id), project.to_dict())
                return Project.from_dict(project.to_dict())

    def load(self, project_id: str) -> Project:
        with self._lock(project_id):
            path = self._path(project_id)
            try:
                # ``Path.read_text`` closes the handle before returning, so GUI
                # polling never keeps a Windows handle across a replacement.
                payload = json.loads(path.read_text(encoding="utf-8"))
            except OSError as exc:
                raise ProjectStoreError(f"could not read project state {project_id}: {exc}") from exc
            project = Project.from_dict(payload)
        others = [
            self._raw_project(candidate)
            for candidate in sorted(self.root.glob("*.json"))
            if candidate.stem != project_id
        ]
        return self._classify([project, *others])[0]

    def paths(self, project_or_id: Project | str) -> ProjectPaths:
        project = self.load(project_or_id) if isinstance(project_or_id, str) else project_or_id
        paths = ProjectPaths.from_project(project)
        if project.workspace_kind == "isolated":
            paths.validate_isolated_identity()
        return paths

    def ensure_writable(self, project_or_id: Project | str) -> ProjectPaths:
        project = self.load(project_or_id) if isinstance(project_or_id, str) else project_or_id
        if project.workspace_kind == "legacy_shared":
            raise UnsafeProjectWorkspaceError(
                "Legacy/shared workspace is read-only; migrate it before importing or running."
            )
        paths = self.paths(project)
        paths.ensure()
        return paths

    def update_project(self, project_id: str, update: Callable[[Project], T]) -> tuple[Project, T]:
        """Atomically load, mutate and persist one project.

        ``update`` runs while the project's lock is held and must mutate only
        the supplied current snapshot.  Its return value is passed through for
        callers that need to report a transition result.
        """
        with self._lock(project_id):
            with self._state_lock(project_id):
                path = self._path(project_id)
                try:
                    project = Project.from_dict(json.loads(path.read_text(encoding="utf-8")))
                except OSError as exc:
                    raise ProjectStoreError(f"could not read project state {project_id}: {exc}") from exc
                project = self._classify(
                    [
                        project,
                        *[
                            self._raw_project(candidate)
                            for candidate in sorted(self.root.glob("*.json"))
                            if candidate.stem != project_id
                        ],
                    ]
                )[0]
                result = update(project)
                self._assert_unique_workspace(project)
                project.updated_at = _now()
                _write_json(path, project.to_dict())
                return Project.from_dict(project.to_dict()), result

    def all(self) -> list[Project]:
        # Each document is loaded under its own shared project lock.  A writer
        # can therefore never replace a document while this method reads it.
        projects: list[Project] = []
        for path in sorted(self.root.glob("*.json")):
            with self._lock(path.stem):
                projects.append(self._raw_project(path))
        return self._classify(projects)

    def delete(self, project_id: str) -> DeletedProject:
        """Soft-delete metadata and, for isolated projects, its owned workspace."""

        metadata = self._path(project_id)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        with self.delete_lock(project_id):
            try:
                run_lock = self.run_lock(project_id)
                run_lock.acquire()
            except ProjectLockError as exc:
                raise ProjectDeleteError(
                    "Project is running in another GaussianOS instance and cannot be deleted."
                ) from exc
            try:
                with self._lock(project_id):
                    with self._state_lock(project_id):
                        project = self.load(project_id)
                        if project.status == "running":
                            raise ProjectDeleteError(
                                "Running projects cannot be deleted; cancel and wait for the run to stop."
                            )
                        paths = self.paths(project)
                        metadata_trash = self.root / ".trash" / f"{project_id}-{timestamp}"
                        metadata_trash.mkdir(parents=True, exist_ok=False)
                        metadata_destination = metadata_trash / "project.json"
                        if project.workspace_kind != "isolated":
                            try:
                                os.replace(metadata, metadata_destination)
                            except Exception as exc:
                                metadata_trash.rmdir()
                                raise ProjectDeleteError(
                                    f"legacy project metadata could not be moved to trash: {exc}"
                                ) from exc
                            return DeletedProject(
                                project_id,
                                metadata_destination,
                                None,
                                legacy_workspace_preserved=True,
                            )

                        paths.validate_isolated_identity()
                        workspace_destination = paths.trash_root / f"{project_id}-{timestamp}"
                        workspace_destination.parent.mkdir(parents=True, exist_ok=True)
                        if workspace_destination.exists():
                            raise ProjectDeleteError(
                                f"project trash destination already exists: {workspace_destination}"
                            )
                        workspace_moved = False
                        try:
                            os.replace(paths.workspace, workspace_destination)
                            workspace_moved = True
                            os.replace(metadata, metadata_destination)
                        except Exception as exc:
                            if workspace_moved and not paths.workspace.exists():
                                try:
                                    os.replace(workspace_destination, paths.workspace)
                                except OSError as rollback_exc:
                                    raise ProjectDeleteError(
                                        f"delete failed and workspace rollback failed: {rollback_exc}"
                                    ) from exc
                            try:
                                metadata_trash.rmdir()
                            except OSError:
                                pass
                            raise ProjectDeleteError(f"project delete failed: {exc}") from exc
                        return DeletedProject(
                            project_id,
                            metadata_destination,
                            workspace_destination,
                            legacy_workspace_preserved=False,
                        )
            finally:
                run_lock.release()
