"""Durable project/task state owned by the desktop control plane."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
        os.replace(temporary, path)
    finally:
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


class ProjectStore:
    """One JSON document per project, atomically replaced after every transition."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def create(self, name: str, project_root: str | Path) -> Project:
        project = Project(project_id=uuid4().hex, name=name, root=str(Path(project_root).resolve()))
        self.save(project)
        return project

    def save(self, project: Project) -> None:
        project.updated_at = _now()
        _write_json(self.root / f"{project.project_id}.json", project.to_dict())

    def load(self, project_id: str) -> Project:
        return Project.from_dict(json.loads((self.root / f"{project_id}.json").read_text(encoding="utf-8")))

    def all(self) -> list[Project]:
        return [Project.from_dict(json.loads(path.read_text(encoding="utf-8"))) for path in sorted(self.root.glob("*.json"))]
