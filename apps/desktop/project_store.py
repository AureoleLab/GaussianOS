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


class ProjectLifecycleError(ProjectStoreError):
    """Raised when a lifecycle transaction cannot complete safely."""


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
    archived: bool = False
    archived_at: str | None = None

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


@dataclass(frozen=True, slots=True)
class TrashEntry:
    project_id: str
    name: str
    metadata_path: Path
    workspace_path: Path | None
    deleted_at: str
    estimated_bytes: int
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

    def lifecycle_lock(self, project_id: str, *, timeout: float = 0.0) -> FileLock:
        self._path(project_id)
        return self._operation_lock(project_id, "lifecycle", timeout=timeout)

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
        if project.workspace_kind != "isolated":
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

    @staticmethod
    def _assert_idle(project: Project, operation: str) -> None:
        if project.status == "running":
            raise ProjectLifecycleError(
                f"Running projects cannot be {operation}; cancel and wait for the run to stop."
            )

    def rename(self, project_id: str, name: str) -> Project:
        """Change only the user-facing name, preserving identity and paths."""

        display_name = name.strip()
        if not display_name:
            raise ValueError("project name is required")
        with self.lifecycle_lock(project_id), self.run_lock(project_id):
            def apply(project: Project) -> None:
                self._assert_idle(project, "renamed")
                project.name = display_name

            project, _ = self.update_project(project_id, apply)
            return project

    def set_archived(self, project_id: str, archived: bool) -> Project:
        """Archive or unarchive a project without moving its workspace."""

        with self.lifecycle_lock(project_id), self.run_lock(project_id):
            def apply(project: Project) -> None:
                self._assert_idle(project, "archived")
                project.archived = bool(archived)
                project.archived_at = _now() if archived else None

            project, _ = self.update_project(project_id, apply)
            return project

    @staticmethod
    def _rebase_value(value: Any, old_root: Path, new_root: Path) -> Any:
        if isinstance(value, dict):
            return {
                key: ProjectStore._rebase_value(item, old_root, new_root)
                for key, item in value.items()
            }
        if isinstance(value, list):
            return [
                ProjectStore._rebase_value(item, old_root, new_root)
                for item in value
            ]
        if isinstance(value, str):
            old = str(old_root)
            normalized_value = os.path.normcase(value)
            normalized_old = os.path.normcase(old)
            if (
                normalized_value == normalized_old
                or (
                    normalized_value.startswith(normalized_old)
                    and len(value) > len(old)
                    and value[len(old)] in {"/", "\\"}
                )
            ):
                return str(new_root) + value[len(old):]
        return value

    @staticmethod
    def _copy_ignore(_directory: str, names: list[str]) -> set[str]:
        ignored = {".locks", ".transactions", "__pycache__"}
        ignored.update(
            name
            for name in names
            if name == "attempts"
            or name == "temp"
            or name.endswith((".staging", ".backup", ".failed", ".tmp"))
        )
        return ignored

    def duplicate(
        self,
        project_id: str,
        name: str,
        *,
        mode: str = "inputs",
    ) -> Project:
        """Atomically duplicate an isolated project into a new identity."""

        if mode not in {"inputs", "complete"}:
            raise ValueError("duplicate mode must be 'inputs' or 'complete'")
        display_name = name.strip()
        if not display_name:
            raise ValueError("project name is required")
        with self.lifecycle_lock(project_id), self.run_lock(project_id):
            source = self.load(project_id)
            self._assert_idle(source, "duplicated")
            if source.workspace_kind != "isolated":
                raise UnsafeProjectWorkspaceError(
                    "Legacy/shared projects cannot be duplicated until explicitly migrated."
                )
            source_paths = self.paths(source)
            if mode == "complete":
                if (
                    source.status != "succeeded"
                    or not source.run_id
                    or source.stages.get("validate", StageState()).status
                    != "succeeded"
                    or source.stages.get("export", StageState()).status
                    != "succeeded"
                ):
                    raise ProjectLifecycleError(
                        "A complete copy requires a successfully committed project run."
                    )
                try:
                    receipt = json.loads(
                        source_paths.viewer_manifest.read_text(encoding="utf-8")
                    )
                except (OSError, ValueError, TypeError) as exc:
                    raise ProjectLifecycleError(
                        "A complete copy requires a valid Viewer receipt."
                    ) from exc
                if (
                    receipt.get("project_id") != project_id
                    or receipt.get("run_id") != source.run_id
                    or receipt.get("committed") is not True
                ):
                    raise ProjectLifecycleError(
                        "Viewer receipt does not belong to the current valid run."
                    )
                for key in ("bundle", "gaussian"):
                    artifact = Path(str(receipt.get(key, ""))).resolve()
                    if not source_paths.contains(artifact) or not artifact.exists():
                        raise ProjectLifecycleError(
                            f"Viewer receipt references a missing or unowned {key} artifact."
                        )
                try:
                    timeline_receipt = json.loads(
                        source_paths.run(source.run_id).timeline_manifest.read_text(
                            encoding="utf-8"
                        )
                    )
                except (OSError, ValueError, TypeError) as exc:
                    raise ProjectLifecycleError(
                        "A complete copy requires a valid Timeline receipt."
                    ) from exc
                if (
                    timeline_receipt.get("project_id") != project_id
                    or timeline_receipt.get("run_id") != source.run_id
                    or timeline_receipt.get("stage") != "timeline"
                ):
                    raise ProjectLifecycleError(
                        "Timeline receipt does not belong to the current valid run."
                    )

            duplicate_id = uuid4().hex
            library_root = source_paths.library_root
            destination = isolated_workspace(library_root, duplicate_id)
            staging = destination.parent / f".copy-{duplicate_id}-{uuid4().hex}"
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists() or staging.exists():
                raise ProjectLifecycleError("duplicate workspace destination already exists")

            clone_payload = self._rebase_value(
                source.to_dict(), source_paths.workspace, destination
            )
            clone_payload.update(
                {
                    "project_id": duplicate_id,
                    "name": display_name,
                    "root": str(destination),
                    "library_root": str(library_root),
                    "workspace_kind": "isolated",
                    "archived": False,
                    "archived_at": None,
                    "created_at": _now(),
                    "updated_at": _now(),
                }
            )
            if mode == "inputs":
                clone_payload.update(
                    {
                        "run_id": None,
                        "status": "ready" if source.input_path else "idle",
                        "current_stage": None,
                        "stages": {},
                    }
                )
                sampling = dict(clone_payload.get("sampling", {}))
                sampling.pop("camera_timeline", None)
                sampling["camera_mapping_stale"] = True
                clone_payload["sampling"] = sampling
            clone = Project.from_dict(clone_payload)

            published = False
            target_lock = self.lifecycle_lock(duplicate_id)
            target_lock.acquire()
            try:
                staging.mkdir()
                _write_json(
                    staging / ".gaussianos-transaction.json",
                    {
                        "schema_version": "gaussianos-lifecycle-transaction/v1",
                        "operation": "duplicate",
                        "source_project_id": project_id,
                        "project_id": duplicate_id,
                    },
                )
                if source_paths.inputs.exists():
                    shutil.copytree(
                        source_paths.inputs,
                        staging / "inputs",
                        ignore=self._copy_ignore,
                    )
                if mode == "complete":
                    for child in source_paths.workspace.iterdir():
                        if child.name in {
                            PROJECT_MARKER,
                            ".locks",
                            ".transactions",
                            "inputs",
                        }:
                            continue
                        target = staging / child.name
                        if child.is_dir():
                            shutil.copytree(child, target, ignore=self._copy_ignore)
                        else:
                            shutil.copy2(child, target)
                _write_json(
                    staging / PROJECT_MARKER,
                    {
                        "schema_version": "gaussianos-project-workspace/v1",
                        "project_id": duplicate_id,
                        "created_at": clone.created_at,
                    },
                )
                for manifest in (
                    staging / "viewer" / "scene.json",
                    *staging.glob("runs/*/timeline/camera-timeline.json"),
                ):
                    if not manifest.is_file():
                        continue
                    payload = json.loads(manifest.read_text(encoding="utf-8"))
                    payload = self._rebase_value(
                        payload, source_paths.workspace, destination
                    )
                    payload["project_id"] = duplicate_id
                    _write_json(manifest, payload)

                os.replace(staging, destination)
                published = True
                self.save(clone)
                (destination / ".gaussianos-transaction.json").unlink(
                    missing_ok=True
                )
                ProjectPaths.from_project(clone).ensure()
                return self.load(duplicate_id)
            except Exception as exc:
                if published:
                    shutil.rmtree(destination, ignore_errors=True)
                shutil.rmtree(staging, ignore_errors=True)
                self._path(duplicate_id).unlink(missing_ok=True)
                if isinstance(exc, ProjectStoreError):
                    raise
                raise ProjectLifecycleError(f"project duplicate failed: {exc}") from exc
            finally:
                target_lock.release()

    @staticmethod
    def _directory_size(path: Path | None) -> int:
        if path is None or not path.exists():
            return 0
        if path.is_file():
            try:
                return path.stat().st_size
            except OSError:
                return 0
        total = 0
        for item in path.rglob("*"):
            if item.is_file():
                try:
                    total += item.stat().st_size
                except OSError:
                    pass
        return total

    def trash_entries(self) -> list[TrashEntry]:
        """List only trash entries whose metadata GaussianOS owns."""

        entries: list[TrashEntry] = []
        for directory in sorted(self.root.glob(".trash/*")):
            metadata = directory / "project.json"
            if not metadata.is_file():
                continue
            try:
                project = self._raw_project(metadata)
                manifest_path = directory / "trash.json"
                manifest = (
                    json.loads(manifest_path.read_text(encoding="utf-8"))
                    if manifest_path.is_file()
                    else {}
                )
                workspace_value = manifest.get("workspace_path")
                if not workspace_value and project.workspace_kind == "isolated":
                    workspace_value = str(
                        ProjectPaths.from_project(project).trash_root / directory.name
                    )
                workspace = Path(workspace_value).resolve() if workspace_value else None
                deleted_at = str(manifest.get("deleted_at") or directory.name)
                preserved = bool(
                    manifest.get(
                        "legacy_workspace_preserved",
                        project.workspace_kind != "isolated",
                    )
                )
                entries.append(
                    TrashEntry(
                        project.project_id,
                        project.name,
                        metadata,
                        workspace,
                        deleted_at,
                        self._directory_size(workspace)
                        + self._directory_size(directory),
                        preserved,
                    )
                )
            except (OSError, ValueError, TypeError, ProjectStoreError):
                continue
        return entries

    def _trash_entry(self, project_id: str) -> TrashEntry:
        matches = [
            entry for entry in self.trash_entries()
            if entry.project_id == project_id
        ]
        if not matches:
            raise ProjectLifecycleError("project is not present in GaussianOS trash")
        return sorted(matches, key=lambda item: item.deleted_at, reverse=True)[0]

    def restore(self, project_id: str) -> Project:
        """Restore soft-deleted metadata and its isolated workspace atomically."""

        with self.delete_lock(project_id), self.run_lock(project_id):
            entry = self._trash_entry(project_id)
            if self._path(project_id).exists():
                raise ProjectLifecycleError("a live project already uses this project_id")
            project = self._raw_project(entry.metadata_path)
            original = Path(project.root).resolve()
            workspace_moved = False
            try:
                if project.workspace_kind == "isolated":
                    if entry.workspace_path is None or not entry.workspace_path.is_dir():
                        raise ProjectLifecycleError("trashed project workspace is missing")
                    trash_paths = ProjectPaths(
                        project.project_id,
                        Path(project.library_root or original.parent).resolve(),
                        entry.workspace_path,
                        "legacy",
                    )
                    try:
                        marker = json.loads(
                            (entry.workspace_path / PROJECT_MARKER).read_text(
                                encoding="utf-8"
                            )
                        )
                    except (OSError, ValueError, TypeError) as exc:
                        raise ProjectLifecycleError(
                            "trashed workspace ownership marker is invalid"
                        ) from exc
                    if marker.get("project_id") != project_id:
                        raise ProjectLifecycleError(
                            "trashed workspace belongs to another project"
                        )
                    if original.exists():
                        raise ProjectLifecycleError(
                            "original project workspace is occupied; restore was not attempted"
                        )
                    original.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(trash_paths.workspace, original)
                    workspace_moved = True
                os.replace(entry.metadata_path, self._path(project_id))
            except Exception as exc:
                if workspace_moved and entry.workspace_path is not None:
                    try:
                        os.replace(original, entry.workspace_path)
                    except OSError as rollback_exc:
                        raise ProjectLifecycleError(
                            f"restore failed and workspace rollback failed: {rollback_exc}"
                        ) from exc
                if isinstance(exc, ProjectLifecycleError):
                    raise
                raise ProjectLifecycleError(f"project restore failed: {exc}") from exc
            trash_directory = entry.metadata_path.parent
            for extra in ("trash.json",):
                (trash_directory / extra).unlink(missing_ok=True)
            try:
                trash_directory.rmdir()
            except OSError:
                pass
            return self.load(project_id)

    def purge(self, project_id: str) -> int:
        """Permanently remove one owned trash entry after ownership validation."""

        with self.delete_lock(project_id), self.run_lock(project_id):
            entry = self._trash_entry(project_id)
            project = self._raw_project(entry.metadata_path)
            released = entry.estimated_bytes
            workspace_quarantine: Path | None = None
            metadata_directory = entry.metadata_path.parent
            metadata_quarantine = metadata_directory.with_name(
                f".purging-{metadata_directory.name}-{uuid4().hex}"
            )
            try:
                if project.workspace_kind == "isolated":
                    workspace = entry.workspace_path
                    if workspace is None or not workspace.is_dir():
                        raise ProjectLifecycleError("trashed project workspace is missing")
                    try:
                        marker = json.loads(
                            (workspace / PROJECT_MARKER).read_text(encoding="utf-8")
                        )
                    except (OSError, ValueError, TypeError) as exc:
                        raise ProjectLifecycleError(
                            "refusing to purge a workspace without a valid ownership marker"
                        ) from exc
                    if marker.get("project_id") != project_id:
                        raise ProjectLifecycleError(
                            "refusing to purge a workspace owned by another project"
                        )
                    expected_parent = ProjectPaths.from_project(project).trash_root.resolve()
                    if workspace.resolve().parent != expected_parent:
                        raise ProjectLifecycleError(
                            "refusing to purge a workspace outside GaussianOS trash"
                        )
                    workspace_quarantine = workspace.with_name(
                        f".purging-{workspace.name}-{uuid4().hex}"
                    )
                    os.replace(workspace, workspace_quarantine)
                os.replace(metadata_directory, metadata_quarantine)
            except Exception as exc:
                if workspace_quarantine is not None and workspace_quarantine.exists():
                    os.replace(workspace_quarantine, entry.workspace_path)
                if isinstance(exc, ProjectLifecycleError):
                    raise
                raise ProjectLifecycleError(
                    f"permanent delete transaction could not start: {exc}"
                ) from exc

            try:
                if workspace_quarantine is not None:
                    shutil.rmtree(workspace_quarantine)
                shutil.rmtree(metadata_quarantine)
            except Exception as exc:
                raise ProjectLifecycleError(
                    "permanent delete was quarantined but cleanup did not finish; "
                    f"GaussianOS will retry safely on startup: {exc}"
                ) from exc
            return released

    def recover_lifecycle_residuals(self) -> list[str]:
        """Finish only lifecycle residuals carrying GaussianOS ownership data."""

        actions: list[str] = []
        library_roots = {
            Path(project.library_root).resolve()
            for project in self.all()
            if project.workspace_kind == "isolated" and project.library_root
        }
        for entry in self.trash_entries():
            try:
                deleted = self._raw_project(entry.metadata_path)
            except ProjectStoreError:
                continue
            if deleted.workspace_kind == "isolated" and deleted.library_root:
                library_roots.add(Path(deleted.library_root).resolve())

        for library in library_roots:
            projects_root = library / ".gaussianos" / "projects"
            for staging in (
                projects_root.iterdir() if projects_root.is_dir() else ()
            ):
                marker = staging / ".gaussianos-transaction.json"
                try:
                    payload = json.loads(marker.read_text(encoding="utf-8"))
                except (OSError, ValueError, TypeError):
                    continue
                project_id = str(payload.get("project_id", ""))
                if (
                    payload.get("schema_version")
                    == "gaussianos-lifecycle-transaction/v1"
                    and payload.get("operation") == "duplicate"
                    and project_id
                    and (
                        project_id in staging.name
                        or staging.name == project_id
                    )
                ):
                    try:
                        operation_lock = self.lifecycle_lock(project_id)
                        operation_lock.acquire()
                    except ProjectLockError:
                        continue
                    try:
                        if self._path(project_id).is_file():
                            marker.unlink()
                            actions.append("finished a published project copy")
                        else:
                            shutil.rmtree(staging)
                            actions.append("removed an interrupted project copy")
                    finally:
                        operation_lock.release()

            for entry in self.trash_entries():
                if entry.workspace_path is None or entry.workspace_path.exists():
                    continue
                try:
                    deleted = self._raw_project(entry.metadata_path)
                except ProjectStoreError:
                    continue
                original = Path(deleted.root).resolve()
                if (
                    deleted.workspace_kind == "isolated"
                    and Path(deleted.library_root or "").resolve() == library
                    and original.is_dir()
                ):
                    try:
                        marker = json.loads(
                            (original / PROJECT_MARKER).read_text(encoding="utf-8")
                        )
                    except (OSError, ValueError, TypeError):
                        continue
                    if marker.get("project_id") == deleted.project_id:
                        try:
                            operation_lock = self.delete_lock(deleted.project_id)
                            operation_lock.acquire()
                        except ProjectLockError:
                            continue
                        try:
                            entry.workspace_path.parent.mkdir(
                                parents=True, exist_ok=True
                            )
                            os.replace(original, entry.workspace_path)
                            actions.append("finished an interrupted soft delete")
                        finally:
                            operation_lock.release()

            trash_root = library / ".gaussianos" / ".trash"
            for quarantine in trash_root.glob(".purging-*"):
                try:
                    marker = json.loads(
                        (quarantine / PROJECT_MARKER).read_text(encoding="utf-8")
                    )
                except (OSError, ValueError, TypeError):
                    continue
                project_id = str(marker.get("project_id", ""))
                if project_id and project_id in quarantine.name:
                    try:
                        operation_lock = self.delete_lock(project_id)
                        operation_lock.acquire()
                    except ProjectLockError:
                        continue
                    try:
                        shutil.rmtree(quarantine)
                        actions.append("finished a quarantined workspace purge")
                    finally:
                        operation_lock.release()

        for quarantine in (self.root / ".trash").glob(".purging-*"):
            metadata = quarantine / "project.json"
            try:
                project = self._raw_project(metadata)
            except ProjectStoreError:
                continue
            if project.project_id and project.project_id in quarantine.name:
                try:
                    operation_lock = self.delete_lock(project.project_id)
                    operation_lock.acquire()
                except ProjectLockError:
                    continue
                try:
                    shutil.rmtree(quarantine)
                    actions.append("finished a quarantined metadata purge")
                finally:
                    operation_lock.release()
        return actions

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
                                _write_json(
                                    metadata_trash / "trash.json",
                                    {
                                        "schema_version": "gaussianos-project-trash/v1",
                                        "project_id": project_id,
                                        "deleted_at": _now(),
                                        "workspace_path": None,
                                        "legacy_workspace_preserved": True,
                                    },
                                )
                                os.replace(metadata, metadata_destination)
                            except Exception as exc:
                                shutil.rmtree(metadata_trash, ignore_errors=True)
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
                        metadata_moved = False
                        try:
                            _write_json(
                                metadata_trash / "trash.json",
                                {
                                    "schema_version": "gaussianos-project-trash/v1",
                                    "project_id": project_id,
                                    "deleted_at": _now(),
                                    "workspace_path": str(workspace_destination),
                                    "legacy_workspace_preserved": False,
                                },
                            )
                            os.replace(metadata, metadata_destination)
                            metadata_moved = True
                            os.replace(paths.workspace, workspace_destination)
                            workspace_moved = True
                        except Exception as exc:
                            if workspace_moved and not paths.workspace.exists():
                                try:
                                    os.replace(workspace_destination, paths.workspace)
                                except OSError as rollback_exc:
                                    raise ProjectDeleteError(
                                        f"delete failed and workspace rollback failed: {rollback_exc}"
                                    ) from exc
                            if metadata_moved and not metadata.exists():
                                try:
                                    os.replace(metadata_destination, metadata)
                                except OSError as rollback_exc:
                                    raise ProjectDeleteError(
                                        f"delete failed and metadata rollback failed: {rollback_exc}"
                                    ) from exc
                            shutil.rmtree(metadata_trash, ignore_errors=True)
                            raise ProjectDeleteError(f"project delete failed: {exc}") from exc
                        return DeletedProject(
                            project_id,
                            metadata_destination,
                            workspace_destination,
                            legacy_workspace_preserved=False,
                        )
            finally:
                run_lock.release()
