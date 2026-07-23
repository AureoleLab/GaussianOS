"""Canonical project and run paths owned by the desktop control plane."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PROJECT_MARKER = ".gaussianos-project.json"


def _safe_identity(value: str, label: str) -> str:
    if not value or any(part in value for part in ("/", "\\", "..")):
        raise ValueError(f"unsafe {label}")
    return value


def isolated_workspace(library_root: str | Path, project_id: str) -> Path:
    _safe_identity(project_id, "project_id")
    return Path(library_root).resolve() / ".gaussianos" / "projects" / project_id


@dataclass(frozen=True, slots=True)
class RunPaths:
    project_id: str
    run_id: str
    root: Path

    @property
    def inputs(self) -> Path:
        return self.root / "inputs"

    @property
    def frames(self) -> Path:
        return self.inputs / "frames"

    @property
    def training(self) -> Path:
        return self.root / "training"

    @property
    def artifacts(self) -> Path:
        return self.root / "artifacts"

    @property
    def staging(self) -> Path:
        return self.artifacts / "attempts"

    @property
    def timeline(self) -> Path:
        return self.root / "timeline"

    @property
    def timeline_manifest(self) -> Path:
        return self.timeline / "camera-timeline.json"

    @property
    def exports(self) -> Path:
        return self.root / "exports"

    @property
    def logs(self) -> Path:
        return self.artifacts

    @property
    def temp(self) -> Path:
        return self.root / "temp"

    def ensure(self) -> None:
        for directory in (
            self.root,
            self.inputs,
            self.training,
            self.artifacts,
            self.timeline,
            self.exports,
            self.temp,
        ):
            directory.mkdir(parents=True, exist_ok=True)


@dataclass(frozen=True, slots=True)
class ProjectPaths:
    project_id: str
    library_root: Path
    workspace: Path
    workspace_kind: str

    @classmethod
    def from_project(cls, project: Any) -> "ProjectPaths":
        project_id = _safe_identity(str(project.project_id), "project_id")
        workspace = Path(project.root).resolve()
        library_value = getattr(project, "library_root", None)
        library_root = Path(library_value).resolve() if library_value else workspace.parent
        return cls(
            project_id=project_id,
            library_root=library_root,
            workspace=workspace,
            workspace_kind=str(getattr(project, "workspace_kind", "legacy")),
        )

    @property
    def marker(self) -> Path:
        return self.workspace / PROJECT_MARKER

    @property
    def inputs(self) -> Path:
        return self.workspace / "inputs"

    @property
    def analysis(self) -> Path:
        return self.inputs / "analysis"

    @property
    def runs(self) -> Path:
        return self.workspace / "runs"

    @property
    def viewer(self) -> Path:
        return self.workspace / "viewer"

    @property
    def viewer_manifest(self) -> Path:
        return self.viewer / "scene.json"

    @property
    def locks(self) -> Path:
        return self.workspace / ".locks"

    @property
    def trash_root(self) -> Path:
        if self.workspace_kind == "isolated":
            return self.library_root / ".gaussianos" / ".trash"
        return self.workspace.parent / ".gaussianos-trash"

    def run(self, run_id: str) -> RunPaths:
        _safe_identity(run_id, "run_id")
        return RunPaths(self.project_id, run_id, self.runs / run_id)

    def contains(self, candidate: str | Path) -> bool:
        try:
            Path(candidate).resolve().relative_to(self.workspace)
            return True
        except ValueError:
            return False

    def validate_isolated_identity(self) -> None:
        if self.workspace_kind != "isolated":
            return
        expected = isolated_workspace(self.library_root, self.project_id)
        if os.path.normcase(str(expected)) != os.path.normcase(str(self.workspace)):
            raise ValueError("isolated project workspace does not match project_id")
        try:
            import json

            marker = json.loads(self.marker.read_text(encoding="utf-8"))
        except (OSError, ValueError, TypeError) as exc:
            raise ValueError("isolated project ownership marker is missing or invalid") from exc
        if marker.get("project_id") != self.project_id:
            raise ValueError("isolated project ownership marker belongs to another project")

    def ensure(self) -> None:
        if self.workspace_kind == "isolated":
            self.validate_isolated_identity()
        for directory in (self.workspace, self.inputs, self.analysis, self.runs, self.viewer, self.locks):
            directory.mkdir(parents=True, exist_ok=True)
