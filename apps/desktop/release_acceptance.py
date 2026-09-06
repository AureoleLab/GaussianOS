"""Exercise the production pipeline from the shipped executable itself.

This is an explicit release diagnostic, never a different implementation of
the pipeline. It writes only beneath a fresh acceptance directory, and records
the executable/control-plane origin so source tests cannot pass a frozen gate.
"""
from __future__ import annotations

import json
import os
import sys
import traceback
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .pipeline import PipelineController, RuntimePaths
from .portable import doctor_report, layout_paths
from .project_store import ProjectStore
from .sampling import discover_ffprobe
from .scene_export import SceneBundleExporter
from .video_import import VideoImportSession
from .viewer import load_viewer_scene


def run_pipeline_acceptance(video: Path, *, frames: int = 12, profile: str = "preview",
                            output: Path | None = None) -> int:
    layout = layout_paths(create=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    acceptance = (output or layout.cache / "ReleaseAcceptance" / f"{stamp}-{uuid4().hex[:8]}").resolve()
    if acceptance.exists() and any(acceptance.iterdir()):
        raise ValueError(f"Acceptance requires an empty output directory: {acceptance}")
    acceptance.mkdir(parents=True, exist_ok=True)
    report_path = acceptance / "report.json"
    report = {
        "schema_version": "gaussianos-executable-e2e/v1", "status": "running",
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "frozen": bool(getattr(sys, "frozen", False)), "executable": sys.executable,
        "control_plane": __file__, "sys_path": sys.path,
        "distribution_root": str(layout.distribution_root),
        "video": str(video.resolve()), "profile": profile, "requested_frames": frames,
        "metadata_directory": str(acceptance / "metadata"), "events": [],
        "environment": {key: os.environ.get(key) for key in
                        ("PATH", "PYTHONHOME", "PYTHONPATH", "CONDA_PREFIX", "TEMP", "HF_HOME")},
    }

    def save():
        temporary = report_path.with_suffix(".tmp")
        temporary.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, report_path)

    session = None
    save()
    try:
        runtime = RuntimePaths.discover()
        report["runtime"] = {key: str(value) for key, value in asdict(runtime).items()}
        before = doctor_report(full=True)
        report["doctor_before"] = before.payload()
        if before.exit_code:
            raise RuntimeError(f"Packaged doctor failed: {before.payload()}")
        session = VideoImportSession(video.resolve(), runtime.ffmpeg,
                                     discover_ffprobe(runtime.ffmpeg), profile=profile)
        requested = min(max(3, frames), session.probe.total_frames)
        session.configure("target_count", requested, 1.0, "seconds", 0,
                          session.probe.total_frames - 1, profile)
        analyzed = session.analyze()
        report["analysis"] = {key: analyzed[key] for key in
                              ("source_total_frames", "selected_frame_count",
                               "selected_frame_indices", "analysis_status")}
        store = ProjectStore(acceptance / "metadata")
        controller = PipelineController(store, acceptance / "unused-legacy-artifacts",
                                        runtime=runtime, enforce_preflight=True)
        project = controller.create_project(f"Beta acceptance {stamp}", acceptance / "library")
        project = controller.commit_video_import(project.project_id, video.resolve(), profile, session.snapshot())
        run_id = controller.new_run_id(project.project_id)
        report.update(project_id=project.project_id, run_id=run_id)

        def event(kind, message, payload):
            report["events"].append({"kind": kind, "message": message, "payload": payload})
            save()

        project = controller.run(project.project_id, event, run_id=run_id)
        report["pipeline_status"] = project.status
        report["stages"] = {name: asdict(state) for name, state in project.stages.items()}
        if project.status != "succeeded":
            raise RuntimeError("Pipeline did not succeed: " + "; ".join(project.warnings[-5:]))
        bundle, gaussian = project.stages["validate"].artifact_paths[:2]
        pointcloud = next(path for path in project.stages["export"].artifact_paths
                          if path.endswith(".pointcloud.ply"))
        run_paths = store.paths(project).run(project.run_id or run_id)
        timeline = json.loads(run_paths.timeline_manifest.read_text(encoding="utf-8"))
        scene = load_viewer_scene(bundle, gaussian, pointcloud, timeline["records"],
                                  project_id=project.project_id, run_id=project.run_id)
        if scene.gaussian_count <= 0 or scene.camera_count < 3 or not timeline["records"]:
            raise RuntimeError("Viewer or camera timeline is empty")
        report["viewer"] = {"gaussian_count": scene.gaussian_count, "camera_count": scene.camera_count,
                            "sh_degree": scene.sh_degree, "gaussian_path": str(scene.gaussian_path)}
        report["camera_timeline"] = {"record_count": len(timeline["records"]), "manifest": str(run_paths.timeline_manifest)}
        export_directory = acceptance / "exports"
        export_directory.mkdir()
        exported = SceneBundleExporter(store).export(project.project_id, project.run_id or run_id,
                                                     export_directory)
        report["scene_bundle_export"] = exported.payload()
        # A fresh store must recover exactly the same successful project/run.
        recovered = ProjectStore(acceptance / "metadata").load(project.project_id)
        if recovered.status != "succeeded" or recovered.run_id != project.run_id:
            raise RuntimeError("Project reopen lost completed pipeline state")
        report["reopen"] = {"status": recovered.status, "run_id": recovered.run_id}
        executions = []
        for path in sorted(run_paths.root.rglob("execution.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            executions.append({"path": str(path), "record": record})
            if report["frozen"]:
                for entry in (record.get("executable"), record.get("cwd")):
                    if entry and not Path(entry).resolve().is_relative_to(layout.distribution_root.resolve()):
                        raise RuntimeError(f"Worker escaped package: {entry}")
        if not executions:
            raise RuntimeError("No actual worker execution records found")
        report["worker_executions"] = executions
        after = doctor_report(full=True)
        report["doctor_after"] = after.payload()
        if after.exit_code:
            raise RuntimeError("Runtime integrity changed during pipeline execution")
        report["status"] = "succeeded"
        return 0
    except Exception as exc:
        report.update(status="failed", error=f"{type(exc).__name__}: {exc}", traceback=traceback.format_exc())
        return 1
    finally:
        if session is not None:
            session.cancel()
        report["completed_at_utc"] = datetime.now(timezone.utc).isoformat()
        save()
