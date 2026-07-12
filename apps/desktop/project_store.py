"""Durable, Windows-safe project/task state owned by the desktop control plane."""

from __future__ import annotations

import errno
import json
import os
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, TypeVar
from uuid import uuid4


REPLACE_BACKOFF_SECONDS = (0.05, 0.1, 0.2, 0.4, 0.8)
_LOCKS_GUARD = threading.Lock()
_PROJECT_LOCKS: dict[tuple[str, str], threading.RLock] = {}


class ProjectStoreError(RuntimeError):
    """Raised when a durable project-state operation cannot complete."""


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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Project":
        stages = {name: StageState(**state) for name, state in value.get("stages", {}).items()}
        return cls(**{**value, "stages": stages})


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

    def create(self, name: str, project_root: str | Path) -> Project:
        project = Project(project_id=uuid4().hex, name=name, root=str(Path(project_root).resolve()))
        # A freshly allocated id is not observable yet, but use the same path
        # as all subsequent operations to keep the contract simple.
        self.save(project)
        return project

    def save(self, project: Project) -> Project:
        """Persist a fully prepared project under the project's shared lock.

        Existing callers should prefer ``update_project``.  ``save`` remains
        for initial creation and compatibility, but still cannot race another
        save/load for this project in this process.
        """
        with self._lock(project.project_id):
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
            return Project.from_dict(payload)

    def update_project(self, project_id: str, update: Callable[[Project], T]) -> tuple[Project, T]:
        """Atomically load, mutate and persist one project.

        ``update`` runs while the project's lock is held and must mutate only
        the supplied current snapshot.  Its return value is passed through for
        callers that need to report a transition result.
        """
        with self._lock(project_id):
            path = self._path(project_id)
            try:
                project = Project.from_dict(json.loads(path.read_text(encoding="utf-8")))
            except OSError as exc:
                raise ProjectStoreError(f"could not read project state {project_id}: {exc}") from exc
            result = update(project)
            project.updated_at = _now()
            _write_json(path, project.to_dict())
            return Project.from_dict(project.to_dict()), result

    def all(self) -> list[Project]:
        # Each document is loaded under its own shared project lock.  A writer
        # can therefore never replace a document while this method reads it.
        return [self.load(path.stem) for path in sorted(self.root.glob("*.json"))]
