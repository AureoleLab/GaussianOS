"""Project-switch transaction and asynchronous result identity."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class AsyncIdentity:
    project_id: str
    run_id: str | None
    generation: int
    stage: str

    def payload(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "run_id": self.run_id,
            "generation": self.generation,
            "stage": self.stage,
        }


@dataclass(slots=True)
class ProjectSession:
    """UI-owned identity; switching clears every project presentation field."""

    project_id: str = ""
    generation: int = 0
    viewer_project_id: str | None = None
    viewer_run_id: str | None = None
    timeline: list[dict[str, Any]] = field(default_factory=list)
    active_camera: int | None = None
    viewer_selection: str | None = None
    active_runs: dict[str, str] = field(default_factory=dict)
    cancelled_runs: set[tuple[str, str]] = field(default_factory=set)

    def switch(self, project_id: str) -> int:
        self.generation += 1
        self.project_id = project_id
        self.viewer_project_id = None
        self.viewer_run_id = None
        self.timeline.clear()
        self.active_camera = None
        self.viewer_selection = None
        return self.generation

    def begin_run(self, project_id: str, run_id: str) -> None:
        self.active_runs[project_id] = run_id
        self.cancelled_runs.discard((project_id, run_id))

    def cancel_run(self, project_id: str) -> None:
        run_id = self.active_runs.get(project_id)
        if run_id:
            self.cancelled_runs.add((project_id, run_id))

    def finish_run(self, project_id: str, run_id: str) -> None:
        if self.active_runs.get(project_id) == run_id:
            self.active_runs.pop(project_id, None)

    def remove_project(self, project_id: str) -> bool:
        self.active_runs.pop(project_id, None)
        self.cancelled_runs = {
            identity for identity in self.cancelled_runs if identity[0] != project_id
        }
        if self.project_id != project_id:
            return False
        self.switch("")
        return True

    def accepts(self, payload: dict[str, Any], *, require_run: bool = False) -> bool:
        project_id = payload.get("project_id")
        generation = payload.get("generation")
        run_id = payload.get("run_id")
        stage = payload.get("stage")
        if (
            project_id != self.project_id
            or generation != self.generation
            or not isinstance(stage, str)
            or not stage
        ):
            return False
        if isinstance(run_id, str) and (project_id, run_id) in self.cancelled_runs:
            return False
        if require_run:
            return (
                isinstance(run_id, str)
                and self.active_runs.get(str(project_id)) == run_id
            )
        return run_id is None or isinstance(run_id, str)
