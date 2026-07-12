"""Run the P2 proof chain: failed COLMAP -> MapAnything+BA -> gsplat -> consumers."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from apps.desktop.pipeline import PipelineController
from apps.desktop.project_store import ProjectStore


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=ROOT / "benchmark_runs" / "p2-mapanything-gsplat")
    parser.add_argument("--profile", choices=("preview", "balanced", "quality"), default="preview")
    parser.add_argument("--resume", action="store_true", help="resume the durable project in --workspace")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    projects = ProjectStore(workspace / "projects")
    existing = projects.all()
    if args.resume:
        if not existing:
            raise SystemExit("--resume requested but no durable project exists")
        project = existing[-1]
    else:
        project = projects.create("MapAnything fallback integration", workspace / "project")
        project.profile = args.profile
        projects.save(project)
    controller = PipelineController(projects, ROOT / ".gaussian-factory" / "artifact-store")
    if not project.input_path:
        controller.import_input(project.project_id, ROOT / "benchmark_runs" / "mapanything-fallback" / "hard-case-001" / "images")
    events: list[dict[str, object]] = []
    result = controller.run(project.project_id, lambda kind, message, payload: events.append({"kind": kind, "message": message, **payload}))
    payload = result.to_dict() | {"events": events}
    (workspace / "summary.json").parent.mkdir(parents=True, exist_ok=True)
    (workspace / "summary.json").write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    required = ("colmap", "fallback", "train", "validate", "export")
    return 0 if result.status == "succeeded" and result.stages.get("fallback").status == "succeeded" and all(result.stages.get(name) and result.stages[name].status == "succeeded" for name in required if name != "colmap") else 10


if __name__ == "__main__":
    raise SystemExit(main())
