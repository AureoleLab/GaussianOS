"""Run the production desktop pipeline against an extracted portable package.

The control plane is imported from the checkout so this script can be audited,
while every native tool and worker interpreter is discovered from the supplied
distribution root.  It is intended for release-candidate evidence, not as an
alternate application launcher.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def _write_report(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--distribution-root", type=Path, required=True)
    parser.add_argument("--video", type=Path, required=True)
    parser.add_argument("--frames", type=int, default=12)
    parser.add_argument("--profile", choices=("preview", "balanced", "quality"), default="preview")
    args = parser.parse_args()

    distribution = args.distribution_root.resolve()
    video = args.video.resolve()
    stamp = _utc_stamp()
    report_path = distribution / "Logs" / f"portable-e2e-{stamp}.json"
    report: dict[str, Any] = {
        "schema_version": "gaussianos-portable-e2e/v1",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "running",
        "distribution_root": str(distribution),
        "video": str(video),
        "profile": args.profile,
        "requested_frames": args.frames,
        "events": [],
    }

    os.environ["GAUSSIANOS_DISTRIBUTION_ROOT"] = str(distribution)
    for name in (
        "PYTHONHOME",
        "PYTHONPATH",
        "PYTHONSTARTUP",
        "PYTHONUSERBASE",
        "VIRTUAL_ENV",
        "CONDA_PREFIX",
        "CONDA_DEFAULT_ENV",
    ):
        os.environ.pop(name, None)
    system_root = os.environ.get("SystemRoot", r"C:\Windows")
    os.environ["PATH"] = os.pathsep.join(
        (str(Path(system_root) / "System32"), system_root)
    )

    session = None
    try:
        from apps.desktop.pipeline import PipelineController, RuntimePaths
        from apps.desktop.project_store import ProjectStore
        from apps.desktop.sampling import discover_ffprobe
        from apps.desktop.scene_export import SceneBundleExporter
        from apps.desktop.video_import import VideoImportSession
        from apps.desktop.viewer import load_viewer_scene

        runtime = RuntimePaths.discover()
        report["runtime"] = {
            "colmap": str(runtime.colmap),
            "ffmpeg": runtime.ffmpeg,
            "map_python": str(runtime.map_python),
            "gsplat_python": str(runtime.gsplat_python),
            "worker_cwd": str(runtime.worker_cwd),
        }
        session = VideoImportSession(
            video,
            runtime.ffmpeg,
            discover_ffprobe(runtime.ffmpeg),
            profile=args.profile,
        )
        requested = min(max(2, args.frames), session.probe.total_frames)
        session.configure(
            "target_count",
            requested,
            1.0,
            "seconds",
            0,
            session.probe.total_frames - 1,
            args.profile,
        )
        analyzed = session.analyze()
        report["analysis"] = {
            "source_total_frames": analyzed["source_total_frames"],
            "selected_frame_count": analyzed["selected_frame_count"],
            "selected_frame_indices": analyzed["selected_frame_indices"],
            "analysis_status": analyzed["analysis_status"],
        }

        acceptance = distribution / "Projects" / "portable-e2e"
        store = ProjectStore(acceptance / "metadata")
        controller = PipelineController(
            store,
            acceptance / "legacy-artifacts-unused",
            runtime=runtime,
            enforce_preflight=True,
        )
        project = controller.create_project(
            f"Portable RC1 E2E {stamp}", acceptance / "library"
        )
        project = controller.commit_video_import(
            project.project_id, video, args.profile, session.snapshot()
        )

        def on_event(kind: str, message: str, payload: dict[str, Any]) -> None:
            event = {"kind": kind, "message": message, "payload": payload}
            report["events"].append(event)
            print(json.dumps(event, ensure_ascii=False), flush=True)

        run_id = controller.new_run_id(project.project_id)
        project = controller.run(project.project_id, on_event, run_id=run_id)
        report["project_id"] = project.project_id
        report["run_id"] = project.run_id
        report["pipeline_status"] = project.status
        report["stages"] = {
            name: asdict(state) for name, state in project.stages.items()
        }
        if project.status != "succeeded":
            raise RuntimeError(
                "pipeline ended without success: "
                + "; ".join(project.warnings[-5:])
            )

        validate_state = project.stages["validate"]
        export_state = project.stages["export"]
        bundle, gaussian = validate_state.artifact_paths[:2]
        pointcloud = next(
            path for path in export_state.artifact_paths if path.endswith(".pointcloud.ply")
        )
        run_paths = store.paths(project).run(project.run_id or run_id)
        timeline_receipt = json.loads(
            run_paths.timeline_manifest.read_text(encoding="utf-8")
        )
        viewer = load_viewer_scene(
            bundle,
            gaussian,
            pointcloud,
            timeline_receipt["records"],
            project_id=project.project_id,
            run_id=project.run_id,
        )
        report["viewer"] = {
            "gaussian_count": viewer.gaussian_count,
            "camera_count": viewer.camera_count,
            "sh_degree": viewer.sh_degree,
            "bundle_path": str(viewer.bundle_path),
            "gaussian_path": str(viewer.gaussian_path),
        }

        export_result = SceneBundleExporter(store).export(
            project.project_id,
            project.run_id or run_id,
            distribution / "Exports",
        )
        report["user_export"] = export_result.payload()
        report["worker_execution_records"] = [
            str(path)
            for path in sorted(run_paths.root.rglob("execution.json"))
        ]
        report["status"] = "succeeded"
        report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        _write_report(report_path, report)
        print(f"E2E_REPORT={report_path}", flush=True)
        return 0
    except Exception as exc:
        report["status"] = "failed"
        report["error"] = f"{type(exc).__name__}: {exc}"
        report["traceback"] = traceback.format_exc()
        report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        _write_report(report_path, report)
        print(f"E2E_REPORT={report_path}", file=sys.stderr, flush=True)
        traceback.print_exc()
        return 1
    finally:
        if session is not None:
            session.cancel()


if __name__ == "__main__":
    raise SystemExit(main())
