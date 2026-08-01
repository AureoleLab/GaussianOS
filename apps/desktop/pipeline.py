"""P2 orchestration: durable control plane over isolated P1 workers.

No model library is imported here.  Every reconstruction/training action is
delegated to ``SubprocessWorkerRunner`` and is therefore safe to invoke from a
non-Qt worker thread.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sys
import threading
import traceback
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import wraps
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from PIL import Image

from packages.artifact_store import ArtifactStore
from packages.artifact_store.store import atomic_write_json
from packages.file_lock import ProjectLockError
from packages.licensing import ProfilePolicyRegistry
from packages.pipeline import CancellationToken, ExecutionOutcome, SubprocessWorkerRunner
from packages.plugin_sdk import (
    ErrorCode,
    ExecutionProfile,
    PluginManifest,
    StageKind,
    StageRequest,
    StageStatus,
)

from .camera_timeline import build_camera_timeline
from .project_paths import ProjectPaths
from .project_store import Project, ProjectStore, ProjectStoreError, StageState
from .sampling import (
    SamplingConfig,
    VideoProbe,
    analyze_video,
    discover_ffprobe,
    estimate_sampling,
    extract_selected_frames,
    probe_video,
    requested_count,
    selection_config_hash,
    validate_config,
)


ROOT = Path(__file__).resolve().parents[2]
STAGES = ("ingest", "colmap", "fallback", "train", "validate", "export")
TERMINAL_STAGE_STATES = frozenset({"succeeded", "skipped", "fallback_required"})
PROFILES = {
    "preview": {"fps": 3.0, "steps": 1000},
    "balanced": {"fps": 8.0, "steps": 3000},
    "quality": {"fps": 15.0, "steps": 7000},
}


class WorkerStageError(RuntimeError):
    """Pipeline exception retaining the worker audit fields for the GUI/log."""

    def __init__(self, message: str, diagnostics: dict[str, Any]) -> None:
        super().__init__(message)
        self.diagnostics = diagnostics


def _idle_project_write(method: Callable[..., Project]) -> Callable[..., Project]:
    """Reject desktop metadata/input writes while any process owns the run."""

    @wraps(method)
    def locked(
        self: "PipelineController", project_id: str, *args: Any, **kwargs: Any
    ) -> Project:
        with self.store.run_lock(project_id):
            if self.store.load(project_id).status == "running":
                raise ProjectLockError(
                    "project is running and cannot be changed by another operation"
                )
            return method(self, project_id, *args, **kwargs)

    return locked


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    colmap: Path
    ffmpeg: str
    worker_python: Path
    worker_cwd: Path
    map_python: Path
    gsplat_python: Path
    gsplat_source: Path
    map_source: Path
    map_checkpoint: Path
    map_config: Path
    dino_source: Path
    dino_checkpoint: Path

    @classmethod
    def discover(cls) -> "RuntimePaths":
        # A frozen portable build keeps every mutable dependency beside the
        # executable.  Source/developer runs preserve the historic local
        # location.  This must not fall back to user-profile caches.
        if getattr(sys, "frozen", False):
            from .portable import layout_paths

            layout = layout_paths()
            factory = layout.runtime
            worker_cwd = layout.application / "worker_host"
        else:
            factory = ROOT / ".gaussian-factory"
            worker_cwd = ROOT
        bundled_ffmpeg = factory / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
        ffmpeg = str(bundled_ffmpeg) if bundled_ffmpeg.is_file() else (shutil.which("ffmpeg") or "ffmpeg")
        map_env = factory / "envs" / "mapanything-1.1.2"
        gsplat_env = factory / "envs" / "gsplat-1.5.3"
        map_python = (map_env / "python.exe") if (map_env / "python.exe").is_file() else (map_env / "Scripts" / "python.exe")
        return cls(
            colmap=factory / "tools" / "colmap" / "3.13.0" / "bin" / "colmap.exe",
            ffmpeg=ffmpeg,
            worker_python=map_python if getattr(sys, "frozen", False) else Path(sys.executable),
            worker_cwd=worker_cwd,
            map_python=map_python,
            gsplat_python=(gsplat_env / "python.exe") if (gsplat_env / "python.exe").is_file() else (gsplat_env / "Scripts" / "python.exe"),
            gsplat_source=factory / "sources" / "gsplat-v1.5.3",
            map_source=factory / "sources" / "map-anything-v1.1.2",
            map_checkpoint=factory / "downloads" / "map-anything-apache-00f9c245" / "model.safetensors",
            map_config=factory / "downloads" / "map-anything-apache-00f9c245" / "config.json",
            dino_source=factory / "sources" / "dinov2-7764ea0",
            dino_checkpoint=factory / "downloads" / "dinov2-7764ea0" / "dinov2_vitg14_pretrain.pth",
        )


class PipelineController:
    """Thread-safe project orchestration with cancellation and restart resume."""

    def __init__(self, store: ProjectStore, artifact_root: str | Path, runtime: RuntimePaths | None = None) -> None:
        self.store = store
        # Kept only as a compatibility hint for callers that still pass the P2
        # global location.  P3 workers always receive a per-project/per-run
        # ArtifactStore rooted by ProjectPaths.
        self.legacy_artifact_root = Path(artifact_root).resolve()
        self.runtime = runtime or RuntimePaths.discover()
        self.policy = ProfilePolicyRegistry.from_directory(ROOT / "configs" / "profiles")
        self._tokens: dict[str, CancellationToken] = {}
        self._running: set[str] = set()
        self._lock = threading.Lock()

    def create_project(self, name: str, project_root: str | Path) -> Project:
        """Control-plane-only project creation entry point for the GUI."""
        return self.store.create(name, project_root)

    @staticmethod
    def new_run_id(project_id: str) -> str:
        return f"run-{project_id[:12]}-{uuid4().hex[:12]}"

    def project_paths(self, project_or_id: Project | str) -> ProjectPaths:
        return self.store.paths(project_or_id)

    @staticmethod
    def _raise_if_cancelled(token: CancellationToken | None) -> None:
        if token is not None and token.is_cancelled:
            raise InterruptedError(token.reason)

    @staticmethod
    def _mark_outputs_stale(project: Project, reason: str) -> None:
        for state in project.stages.values():
            if state.status not in {"pending", "running"}:
                state.status = "stale"
                state.error = reason
        project.sampling["camera_mapping_stale"] = True
        project.sampling.pop("camera_timeline", None)
        project.run_id = None
        project.current_stage = None

    def cleanup_project(self, project_id: str, target: str) -> Project:
        """Remove selected owned outputs through a rollback-capable transaction."""

        stage_groups = {
            "reconstruction": ("colmap", "fallback", "train", "validate", "export"),
            "training": ("train", "validate", "export"),
            "viewer": ("export",),
            "exports": ("export",),
        }
        artifact_stage_groups = {
            **stage_groups,
            "viewer": (),
        }
        if target not in stage_groups:
            raise ValueError(
                "cleanup target must be reconstruction, training, viewer, or exports"
            )
        with self.store.lifecycle_lock(project_id), self.store.run_lock(project_id):
            project = self.store.load(project_id)
            if project.status == "running":
                raise ProjectLockError(
                    "project is running and cannot be cleaned"
                )
            if project.workspace_kind != "isolated":
                raise ProjectStoreError(
                    "Legacy/shared project cleanup is blocked until explicit migration."
                )
            paths = self.store.ensure_writable(project)
            targets: list[Path] = []
            for stage in artifact_stage_groups[target]:
                state = project.stages.get(stage)
                if state is None:
                    continue
                for value in state.artifact_paths:
                    path = Path(value).resolve()
                    if paths.contains(path):
                        targets.append(path)
            if project.run_id:
                run_paths = paths.run(project.run_id)
                if target in {"reconstruction", "training"}:
                    targets.append(run_paths.training)
                if target in {"reconstruction", "training", "exports"}:
                    targets.append(run_paths.exports)
                if target in {"reconstruction", "training", "viewer"}:
                    targets.append(run_paths.timeline_manifest)
            if target in {"reconstruction", "training", "viewer", "exports"}:
                targets.append(paths.viewer_manifest)

            unique: list[Path] = []
            for candidate in sorted(
                {item.resolve() for item in targets if item.exists()},
                key=lambda item: len(item.parts),
            ):
                if not paths.contains(candidate):
                    raise ProjectStoreError(
                        f"cleanup target is outside the owning project: {candidate}"
                    )
                if any(parent == candidate or parent in candidate.parents for parent in unique):
                    continue
                unique.append(candidate)

            transaction = paths.transactions / f"cleanup-{uuid4().hex}"
            transaction.mkdir(parents=True, exist_ok=False)
            moves = [
                {
                    "source": str(source),
                    "quarantine": str(transaction / f"{index:03d}-{source.name}"),
                }
                for index, source in enumerate(unique)
            ]
            manifest = transaction / "transaction.json"
            atomic_write_json(
                manifest,
                {
                    "schema_version": "gaussianos-cleanup-transaction/v1",
                    "project_id": project_id,
                    "target": target,
                    "phase": "moving",
                    "moves": moves,
                },
            )
            moved: list[tuple[Path, Path]] = []
            metadata_committed = False
            try:
                for item in moves:
                    source = Path(item["source"])
                    quarantine = Path(item["quarantine"])
                    if source.exists():
                        quarantine.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(source, quarantine)
                        moved.append((source, quarantine))
                atomic_write_json(
                    manifest,
                    {
                        "schema_version": "gaussianos-cleanup-transaction/v1",
                        "project_id": project_id,
                        "target": target,
                        "phase": "moved",
                        "moves": moves,
                    },
                )

                def apply(current: Project) -> None:
                    if current.status == "running":
                        raise ProjectLockError(
                            "project started running while cleanup was pending"
                        )
                    for stage_name in stage_groups[target]:
                        current.stages[stage_name] = StageState()
                    current.sampling.pop("camera_timeline", None)
                    current.sampling["camera_mapping_stale"] = True
                    current.run_id = None
                    current.current_stage = None
                    current.status = "ready" if current.input_path else "idle"
                    current.warnings.append(
                        f"Cleared {target} outputs; downstream artifacts must be rebuilt."
                    )

                cleaned, _ = self.store.update_project(project_id, apply)
                metadata_committed = True
                atomic_write_json(
                    manifest,
                    {
                        "schema_version": "gaussianos-cleanup-transaction/v1",
                        "project_id": project_id,
                        "target": target,
                        "phase": "committed",
                        "moves": moves,
                    },
                )
            except Exception:
                if metadata_committed:
                    # The durable project snapshot is authoritative.  Keep the
                    # owned transaction for startup to finish instead of
                    # restoring artifacts that metadata has invalidated.
                    return cleaned
                for source, quarantine in reversed(moved):
                    if quarantine.exists() and not source.exists():
                        source.parent.mkdir(parents=True, exist_ok=True)
                        os.replace(quarantine, source)
                shutil.rmtree(transaction, ignore_errors=True)
                raise
            shutil.rmtree(transaction, ignore_errors=True)
            return cleaned

    def recover_lifecycle_residuals(self) -> list[str]:
        """Recover only transactions and temp paths with provable project ownership."""

        actions = self.store.recover_lifecycle_residuals()
        for snapshot in self.store.all():
            if snapshot.workspace_kind != "isolated":
                continue
            try:
                run_lock = self.store.run_lock(snapshot.project_id)
                run_lock.acquire()
            except ProjectLockError:
                continue
            try:
                current = self.store.load(snapshot.project_id)
                if current.status == "running":
                    continue
                paths = self.store.paths(current)
                for transaction in sorted(paths.transactions.glob("cleanup-*")):
                    manifest = transaction / "transaction.json"
                    try:
                        payload = json.loads(manifest.read_text(encoding="utf-8"))
                    except (OSError, ValueError, TypeError):
                        # Unknown directories are deliberately preserved.
                        continue
                    if (
                        payload.get("schema_version")
                        != "gaussianos-cleanup-transaction/v1"
                        or payload.get("project_id") != current.project_id
                    ):
                        continue
                    stage_groups = {
                        "reconstruction": (
                            "colmap", "fallback", "train", "validate", "export"
                        ),
                        "training": ("train", "validate", "export"),
                        "viewer": ("export",),
                        "exports": ("export",),
                    }
                    target = str(payload.get("target", ""))
                    metadata_committed = (
                        target in stage_groups
                        and current.run_id is None
                        and any(
                            warning.startswith(f"Cleared {target} outputs;")
                            for warning in current.warnings
                        )
                        and all(
                            current.stages.get(name, StageState()).status
                            == "pending"
                            for name in stage_groups[target]
                        )
                    )
                    if payload.get("phase") == "committed" or metadata_committed:
                        shutil.rmtree(transaction)
                        actions.append(f"finished cleanup transaction for {current.name}")
                        continue
                    for move in reversed(payload.get("moves", [])):
                        source = Path(str(move.get("source", ""))).resolve()
                        quarantine = Path(str(move.get("quarantine", ""))).resolve()
                        if (
                            paths.contains(source)
                            and paths.contains(quarantine)
                            and quarantine.exists()
                            and not source.exists()
                        ):
                            source.parent.mkdir(parents=True, exist_ok=True)
                            os.replace(quarantine, source)
                    shutil.rmtree(transaction)
                    actions.append(f"rolled back cleanup transaction for {current.name}")

                if not paths.analysis.exists():
                    backups = sorted(
                        paths.inputs.glob(".analysis.*.backup"),
                        key=lambda item: item.stat().st_mtime,
                        reverse=True,
                    )
                    if backups:
                        os.replace(backups[0], paths.analysis)
                        actions.append(f"restored sampling analysis for {current.name}")
                for residual in paths.inputs.glob(".analysis.*"):
                    if residual.name.endswith((".staging", ".backup", ".failed")):
                        shutil.rmtree(residual)
                        actions.append(f"removed sampling residual for {current.name}")
                for run in paths.runs.iterdir() if paths.runs.is_dir() else ():
                    temp = run / "temp"
                    if temp.is_dir():
                        shutil.rmtree(temp)
                        temp.mkdir()
                        actions.append(f"cleared run temp for {current.name}")
                    exports = run / "exports"
                    if exports.is_dir():
                        for staging in exports.glob(".*.staging"):
                            if staging.is_dir():
                                shutil.rmtree(staging)
                            else:
                                staging.unlink()
                            actions.append(f"removed export staging for {current.name}")
            finally:
                run_lock.release()
        return actions

    @_idle_project_write
    def import_input(self, project_id: str, source: str | Path) -> Project:
        self.store.ensure_writable(project_id)
        source = Path(source).resolve()
        if not source.exists():
            raise FileNotFoundError(source)
        if source.is_dir():
            images = [item for item in source.iterdir() if item.suffix.lower() in {".png", ".jpg", ".jpeg"}]
            if not images:
                raise ValueError("image folder contains no PNG/JPEG files")
            kind = "images"
        elif source.suffix.lower() in {".mp4", ".mov", ".mkv", ".avi", ".webm"}:
            kind = "video"
        else:
            raise ValueError("input must be a video or image folder")
        sampling: dict[str, Any]
        if kind == "video":
            probe = probe_video(source, discover_ffprobe(self.runtime.ffmpeg))
            config = SamplingConfig(profile=self.store.load(project_id).profile)
            estimate = estimate_sampling(probe, config)
            sampling = {
                **probe.to_dict(),
                "source_total_frames": probe.total_frames,
                "sampling_mode": "auto",
                "requested_frame_count": requested_count(probe, config),
                "candidate_frame_count": estimate["estimated_candidate_count"],
                "selected_frame_count": 0,
                "selected_frame_indices": [],
                "rejected_frame_indices": [],
                "selection_config_hash": selection_config_hash(probe, config),
                "interval_value": config.interval_value,
                "interval_unit": config.interval_unit,
                "manual_override": False,
                "profile_label": config.profile.title(),
                "timeline": [],
                "warnings": [],
                "analysis_status": "pending",
                **estimate,
            }
        else:
            total = len(images)
            sampling = {
                "source_total_frames": total,
                "sampling_mode": "all_frames",
                "requested_frame_count": total,
                "candidate_frame_count": total,
                "selected_frame_count": total,
                "selected_frame_indices": list(range(total)),
                "rejected_frame_indices": [],
                "selection_config_hash": hashlib.sha256(f"images:{total}".encode()).hexdigest(),
                "manual_override": False,
                "profile_label": "Images",
                "timeline": [],
                "warnings": [],
                "analysis_status": "complete",
            }
        def apply(project: Project) -> None:
            if project.status == "running":
                raise RuntimeError("cannot change input while a pipeline is running")
            project.input_path, project.input_kind, project.status = str(source), kind, "ready"
            project.sampling = sampling
            self._mark_outputs_stale(project, "Input or sampling configuration changed")
        project, _ = self.store.update_project(project_id, apply)
        return project

    @_idle_project_write
    def set_profile(self, project_id: str, profile: str) -> Project:
        self.store.ensure_writable(project_id)
        if profile not in PROFILES:
            raise ValueError(f"unknown profile: {profile}")
        def apply(project: Project) -> None:
            if project.status == "running":
                raise RuntimeError("cannot change profile while a pipeline is running")
            profile_changed = project.profile != profile
            project.profile = profile
            if project.input_kind == "video" and project.sampling and not project.sampling.get("manual_override", False):
                probe = self._probe_from_project(project)
                config = SamplingConfig(
                    profile=profile,
                    in_frame=int(project.sampling.get("in_frame", 0)),
                    out_frame=int(project.sampling["out_frame"]) if project.sampling.get("out_frame") is not None else None,
                )
                estimate = estimate_sampling(probe, config)
                project.sampling.update({
                    "sampling_mode": "auto",
                    "requested_frame_count": requested_count(probe, config),
                    "candidate_frame_count": estimate["estimated_candidate_count"],
                    "selected_frame_count": 0,
                    "selected_frame_indices": [],
                    "rejected_frame_indices": [],
                    "selection_config_hash": selection_config_hash(probe, config),
                    "profile_label": profile.title(),
                    "analysis_status": "pending",
                    "timeline": [],
                    **estimate,
                })
                self._mark_outputs_stale(project, "Profile changed automatic frame selection")
            elif project.input_kind == "video" and project.sampling:
                probe = self._probe_from_project(project)
                config = SamplingConfig(
                    mode=str(project.sampling.get("sampling_mode", "target_count")),
                    requested_frame_count=int(project.sampling.get("requested_frame_count", 1)),
                    interval_value=float(project.sampling.get("interval_value", 1.0)),
                    interval_unit=str(project.sampling.get("interval_unit", "seconds")),
                    profile=profile,
                    manual_override=True,
                    in_frame=int(project.sampling.get("in_frame", 0)),
                    out_frame=int(project.sampling["out_frame"]) if project.sampling.get("out_frame") is not None else None,
                )
                estimate = estimate_sampling(probe, config)
                project.sampling.update({
                    "selection_config_hash": selection_config_hash(probe, config),
                    "selected_frame_count": 0,
                    "selected_frame_indices": [],
                    "rejected_frame_indices": [],
                    "analysis_status": "pending",
                    "timeline": [],
                    **estimate,
                })
                self._mark_outputs_stale(project, "Profile changed reconstruction outputs")
            elif profile_changed:
                self._mark_outputs_stale(
                    project, "Profile changed reconstruction outputs"
                )
            if profile_changed:
                project.status = "ready" if project.input_path else "idle"
        project, _ = self.store.update_project(project_id, apply)
        return project

    @staticmethod
    def _probe_from_project(project: Project) -> VideoProbe:
        sampling = project.sampling
        try:
            return VideoProbe(
                total_frames=int(sampling["source_total_frames"]),
                duration_seconds=float(sampling["duration_seconds"]),
                fps=float(sampling["fps"]),
                width=int(sampling["width"]),
                height=int(sampling["height"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("video must be probed before configuring sampling") from exc

    @staticmethod
    def _sampling_config(project: Project) -> SamplingConfig:
        sampling = project.sampling
        return SamplingConfig(
            mode=str(sampling.get("sampling_mode", "auto")),
            requested_frame_count=int(sampling["requested_frame_count"]) if sampling.get("requested_frame_count") is not None else None,
            interval_value=float(sampling.get("interval_value", 1.0)),
            interval_unit=str(sampling.get("interval_unit", "seconds")),
            profile=project.profile,
            manual_override=bool(sampling.get("manual_override", False)),
            in_frame=int(sampling.get("in_frame", 0)),
            out_frame=int(sampling["out_frame"]) if sampling.get("out_frame") is not None else None,
        )

    @_idle_project_write
    def set_sampling_config(
        self,
        project_id: str,
        mode: str,
        requested_frame_count: int,
        interval_value: float,
        interval_unit: str,
        in_frame: int = 0,
        out_frame: int | None = None,
    ) -> Project:
        self.store.ensure_writable(project_id)
        snapshot = self.store.load(project_id)
        if snapshot.input_kind != "video":
            raise ValueError("frame sampling is available only for video inputs")
        probe = self._probe_from_project(snapshot)
        config = SamplingConfig(
            mode=mode,
            requested_frame_count=requested_frame_count,
            interval_value=interval_value,
            interval_unit=interval_unit,
            profile=snapshot.profile,
            manual_override=True,
            in_frame=in_frame,
            out_frame=out_frame,
        )
        validate_config(probe, config)
        estimate = estimate_sampling(probe, config)
        effective = requested_count(probe, config)
        def apply(project: Project) -> None:
            if project.status == "running":
                raise RuntimeError("cannot change sampling while a pipeline is running")
            project.sampling.update({
                "sampling_mode": mode,
                "requested_frame_count": effective,
                "interval_value": interval_value,
                "interval_unit": interval_unit,
                "manual_override": True,
                "profile_label": "Custom",
                "candidate_frame_count": estimate["estimated_candidate_count"],
                "selected_frame_count": 0,
                "selected_frame_indices": [],
                "rejected_frame_indices": [],
                "selection_config_hash": selection_config_hash(probe, config),
                "analysis_status": "pending",
                "timeline": [],
                "warnings": [],
                "in_frame": estimate["in_frame"],
                "out_frame": estimate["out_frame"],
                "trimmed_frame_count": estimate["trimmed_frame_count"],
                **estimate,
            })
            self._mark_outputs_stale(project, "Trim or sampling configuration changed")
            project.status = "ready"
        project, _ = self.store.update_project(project_id, apply)
        return project

    def commit_video_import(
        self,
        project_id: str,
        source: str | Path,
        profile: str,
        sampling: dict[str, Any],
    ) -> Project:
        with self.store.run_lock(project_id):
            return self._commit_video_import_locked(
                project_id, source, profile, sampling
            )

    def _commit_video_import_locked(
        self,
        project_id: str,
        source: str | Path,
        profile: str,
        sampling: dict[str, Any],
    ) -> Project:
        """Atomically make an analyzed transient import a durable project input."""
        paths = self.store.ensure_writable(project_id)
        source_path = Path(source).resolve()
        if not source_path.is_file():
            raise FileNotFoundError(source_path)
        if sampling.get("analysis_status") != "complete":
            raise ValueError("Generate requires completed video analysis")
        analysis_dir = paths.analysis
        analysis_dir.mkdir(parents=True, exist_ok=True)
        durable = deepcopy(sampling)
        for record in durable.get("timeline", []):
            thumbnail = Path(str(record.get("thumbnail_path", "")))
            if thumbnail.is_file():
                destination = analysis_dir / thumbnail.name
                shutil.copy2(thumbnail, destination)
                record["thumbnail_path"] = str(destination)

        def apply(project: Project) -> None:
            if project.status == "running":
                raise RuntimeError("cannot replace input while a pipeline is running")
            project.input_path = str(source_path)
            project.input_kind = "video"
            project.profile = profile
            project.sampling = durable
            self._mark_outputs_stale(project, "Video import configuration changed")
            project.status = "ready"
            project.current_stage = None

        project, _ = self.store.update_project(project_id, apply)
        return project

    def analyze_sampling(
        self, project_id: str, *, active_run_id: str | None = None
    ) -> Project:
        if active_run_id is not None:
            current = self.store.load(project_id)
            if current.run_id != active_run_id or current.status != "running":
                raise RuntimeError("sampling analysis no longer belongs to the active run")
            return self._analyze_sampling_locked(project_id)
        with self.store.run_lock(project_id):
            current = self.store.load(project_id)
            if current.status == "running":
                raise RuntimeError("cannot analyze sampling while a pipeline is running")
            return self._analyze_sampling_locked(project_id)

    def _analyze_sampling_locked(self, project_id: str) -> Project:
        paths = self.store.ensure_writable(project_id)
        project = self.store.load(project_id)
        if project.input_kind != "video" or not project.input_path:
            raise ValueError("import a video before analyzing keyframes")
        probe, config = self._probe_from_project(project), self._sampling_config(project)
        expected_hash = str(
            project.sampling.get("selection_config_hash")
            or selection_config_hash(probe, config)
        )
        self.store.update_project(project_id, lambda current: current.sampling.update({"analysis_status": "analyzing", "warnings": []}))
        analysis_staging = paths.inputs / f".analysis.{uuid4().hex}.staging"
        analysis_backup = paths.inputs / f".analysis.{uuid4().hex}.backup"
        published = False
        old_analysis_saved = False
        committed = False
        try:
            result = analyze_video(
                project.input_path,
                probe,
                config,
                self.runtime.ffmpeg,
                analysis_staging,
            )
            for record in result.get("timeline", []):
                thumbnail = record.get("thumbnail_path")
                if thumbnail:
                    relative = Path(thumbnail).resolve().relative_to(
                        analysis_staging.resolve()
                    )
                    record["thumbnail_path"] = str(paths.analysis / relative)
            if paths.analysis.exists():
                os.replace(paths.analysis, analysis_backup)
                old_analysis_saved = True
            try:
                os.replace(analysis_staging, paths.analysis)
                published = True
            except Exception:
                if old_analysis_saved:
                    os.replace(analysis_backup, paths.analysis)
                    old_analysis_saved = False
                raise

            def apply(current: Project) -> None:
                if current.sampling.get("selection_config_hash") != expected_hash:
                    raise RuntimeError("sampling configuration changed while analysis was running")
                current.sampling.update(result)
                current.sampling.pop("analysis_error", None)
                current.warnings = [item for item in current.warnings if not item.startswith("Frame sampling:")]
                current.warnings.extend(f"Frame sampling: {item}" for item in result.get("warnings", []))

            analyzed, _ = self.store.update_project(project_id, apply)
            committed = True
        except Exception as exc:
            if published and paths.analysis.exists():
                failed = paths.inputs / f".analysis.{uuid4().hex}.failed"
                try:
                    os.replace(paths.analysis, failed)
                    if old_analysis_saved:
                        os.replace(analysis_backup, paths.analysis)
                        old_analysis_saved = False
                finally:
                    shutil.rmtree(failed, ignore_errors=True)
            try:
                self.store.update_project(project_id, lambda current: current.sampling.update({"analysis_status": "failed", "analysis_error": str(exc)}))
            except ProjectStoreError:
                pass
            raise
        finally:
            shutil.rmtree(analysis_staging, ignore_errors=True)
            if committed:
                shutil.rmtree(analysis_backup, ignore_errors=True)
        return analyzed

    def recover_interrupted_projects(self) -> list[Project]:
        """Mark stale GUI-owned runs resumable after an application restart."""
        recovered: list[Project] = []
        for snapshot in self.store.all():
            if snapshot.status != "running":
                continue
            try:
                run_lock = self.store.run_lock(snapshot.project_id)
                run_lock.acquire()
            except Exception:
                # A live second instance still owns this run.  File existence is
                # not considered ownership; only the OS advisory lock is.
                continue
            def apply(project: Project) -> None:
                if project.status == "running":
                    project.status = "interrupted"
                    for state in project.stages.values():
                        if state.status == "running":
                            state.status = "interrupted"
                            state.error = "Desktop restarted while this stage was running"
                    project.current_stage = None
                    project.warnings.append("Desktop restarted while this task was running; resume to continue.")
            try:
                project, _ = self.store.update_project(snapshot.project_id, apply)
                recovered.append(project)
            finally:
                run_lock.release()
        return recovered

    def cancel(self, project_id: str) -> None:
        with self._lock:
            token = self._tokens.get(project_id)
        if token:
            token.cancel("cancelled from desktop GUI")

    def run(
        self,
        project_id: str,
        on_event: Callable[[str, str, dict[str, Any]], None] | None = None,
        *,
        run_id: str | None = None,
        generation: int = 0,
    ) -> Project:
        self.store.ensure_writable(project_id)
        project = self.store.load(project_id)
        if not project.input_path or not project.input_kind:
            raise ValueError("import a video or image folder first")
        run_id = run_id or self.new_run_id(project_id)
        token = CancellationToken()
        with self._lock:
            if project_id in self._running:
                raise RuntimeError("pipeline is already running for this project")
            self._running.add(project_id)
            self._tokens[project_id] = token
        persistence_failed = False
        started = False
        run_lock = None

        def identified_event(kind: str, message: str, payload: dict[str, Any]) -> None:
            if on_event is None:
                return
            stage = str(payload.get("stage") or project.current_stage or "pipeline")
            on_event(
                kind,
                message,
                {
                    **payload,
                    "project_id": project.project_id,
                    "run_id": run_id,
                    "generation": generation,
                    "stage": stage,
                },
            )

        try:
            run_lock = self.store.run_lock(project_id)
            run_lock.acquire()
            project = self.store.load(project_id)
            if project.status == "running":
                raise ProjectLockError(
                    "project metadata still records a running pipeline; recover or cancel it first"
                )
            project.run_id = run_id
            project.status = "running"
            project.current_stage = None
            self._persist(project, allow_begin=True)
            started = True

            self._raise_if_cancelled(token)
            inputs = self._ingest(project, token, identified_event)
            self._raise_if_cancelled(token)
            reconstruction = self._reconstruct(project, inputs, token, identified_event)
            self._raise_if_cancelled(token)
            training_input = self._prepare_training_input(
                project, reconstruction, inputs, generation
            )
            self._raise_if_cancelled(token)
            training = self._train(project, training_input, token, identified_event)
            self._raise_if_cancelled(token)
            self._validate_and_export(
                project,
                training,
                identified_event,
                generation,
                cancellation_token=token,
            )
            self._raise_if_cancelled(token)
            self._normalize_success(project)
            project.status = "succeeded"
        except ProjectLockError:
            raise
        except InterruptedError:
            self._terminate_active_stage(project, "interrupted", token.reason)
            project.status = "interrupted"
        except ProjectStoreError as exc:
            persistence_failed = True
            self._mark_persistence_failure(project, exc, identified_event)
        except Exception as exc:
            self._terminate_active_stage(project, "failed", str(exc))
            project.status = "failed"
            project.warnings.append(f"{type(exc).__name__}: {exc}")
            error_payload: dict[str, Any] = {
                "exception_type": type(exc).__name__,
                "traceback": traceback.format_exc(),
            }
            if isinstance(exc, WorkerStageError):
                error_payload.update(exc.diagnostics)
            if project.run_id:
                try:
                    atomic_write_json(
                        self.store.paths(project).run(project.run_id).logs
                        / "pipeline-error.json",
                        {
                            "schema_version": "gaussianos-pipeline-error/v1",
                            "project_id": project.project_id,
                            "run_id": project.run_id,
                            "generation": generation,
                            "stage": project.current_stage or error_payload.get(
                                "worker_stage", "pipeline"
                            ),
                            "message": str(exc),
                            **error_payload,
                        },
                    )
                except (OSError, ProjectStoreError, TypeError, ValueError):
                    pass
            self._emit(identified_event, "error", str(exc), error_payload)
        finally:
            if started and not persistence_failed:
                project.current_stage = None
                try:
                    self._persist(project)
                except ProjectStoreError as exc:
                    persistence_failed = True
                    self._mark_persistence_failure(project, exc, identified_event)
            with self._lock:
                self._tokens.pop(project_id, None)
                self._running.discard(project_id)
            if run_lock is not None:
                run_lock.release()
        return project

    def _persist(self, project: Project, *, allow_begin: bool = False) -> None:
        """Commit the control-plane snapshot through the atomic update API."""
        snapshot = deepcopy(project)
        def replace(current: Project) -> None:
            if not allow_begin and current.run_id != snapshot.run_id:
                raise RuntimeError(
                    f"stale run {snapshot.run_id} cannot replace active run {current.run_id}"
                )
            if allow_begin and current.status == "running" and current.run_id != snapshot.run_id:
                raise RuntimeError("another run became active before this run could start")
            if current.project_id != snapshot.project_id or current.root != snapshot.root:
                raise RuntimeError("project identity changed while the pipeline was running")
            for name in Project.__dataclass_fields__:
                setattr(current, name, deepcopy(getattr(snapshot, name)))
        self.store.update_project(project.project_id, replace)

    def _best_effort_persist(self, project: Project) -> None:
        try:
            self._persist(project)
        except (ProjectStoreError, RuntimeError):
            # The original exception is emitted to the GUI; never mask it with
            # a second persistence failure or let the worker thread escape.
            pass

    def _mark_persistence_failure(self, project: Project, exc: Exception, event: Callable[[str, str, dict[str, Any]], None] | None) -> None:
        self._terminate_active_stage(project, "failed", f"Project state persistence failed: {exc}")
        project.status = "failed"
        project.current_stage = None
        project.warnings.append(f"Project state persistence failed: {exc}")
        self._best_effort_persist(project)
        self._emit(event, "persistence_failed", str(exc), {"status": "failed", "project_id": project.project_id})

    def _emit(self, sink: Callable[[str, str, dict[str, Any]], None] | None, kind: str, message: str, payload: dict[str, Any]) -> None:
        if sink:
            sink(kind, message, payload)

    def _stage(self, project: Project, name: str, event: Callable[[str, str, dict[str, Any]], None] | None) -> StageState:
        if project.status != "running" or not project.run_id:
            raise RuntimeError(f"stage {name} cannot start without an active run")
        if project.current_stage:
            active = project.stages.get(project.current_stage)
            if active is not None and active.status == "running" and project.current_stage != name:
                raise RuntimeError(
                    f"stage {name} cannot start while {project.current_stage} is running"
                )
        state = project.stages.setdefault(name, StageState())
        project.current_stage, state.status, state.error = name, "running", None
        self._persist(project)
        self._emit(event, "stage", name, {"stage": name})
        return state

    def _complete(self, project: Project, name: str, state: StageState, event: Callable[[str, str, dict[str, Any]], None] | None) -> None:
        if (
            project.current_stage != name
            or project.stages.get(name) is not state
            or state.status != "running"
        ):
            raise RuntimeError(f"late or invalid completion rejected for stage {name}")
        state.status, state.updated_at = "succeeded", datetime.now(timezone.utc).isoformat()
        self._persist(project)
        self._emit(event, "progress", f"{name} completed", {"stage": name, "progress": (STAGES.index(name) + 1) / len(STAGES)})

    def _skip(self, project: Project, name: str, reason: str, event: Callable[[str, str, dict[str, Any]], None] | None) -> None:
        state = project.stages.setdefault(name, StageState())
        state.status, state.error = "skipped", None
        state.metrics = {"reason": reason}
        state.updated_at = datetime.now(timezone.utc).isoformat()
        self._persist(project)
        self._emit(event, "stage_skipped", f"{name} skipped: {reason}", {"stage": name})

    @staticmethod
    def _terminate_active_stage(project: Project, status: str, error: str) -> None:
        if project.current_stage:
            state = project.stages.get(project.current_stage)
            if state is not None and state.status == "running":
                state.status, state.error = status, error
                state.updated_at = datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _normalize_success(project: Project) -> None:
        """Enforce the persisted success invariant before exposing completion."""
        non_terminal = {
            name: project.stages.get(name, StageState()).status
            for name in STAGES
            if project.stages.get(name, StageState()).status not in TERMINAL_STAGE_STATES
        }
        if non_terminal:
            raise RuntimeError(f"cannot succeed with non-terminal stages: {non_terminal}")

    def _previous(self, project: Project, name: str) -> StageState | None:
        state = project.stages.get(name)
        paths = self.store.paths(project)
        owned = (
            project.workspace_kind != "isolated"
            or all(paths.contains(path) for path in state.artifact_paths)
        ) if state else False
        if (
            state
            and owned
            and state.status == "succeeded"
            and all(Path(path).exists() for path in state.artifact_paths)
        ):
            return state
        return None

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def _atomic_copy(source: Path, target: Path) -> None:
        """Copy beside the destination, then publish with one filesystem rename."""

        if target.exists():
            raise RuntimeError(f"export target already exists: {target}")
        staging = target.parent / f".{target.name}.{uuid4().hex}.staging"
        try:
            if source.is_dir():
                shutil.copytree(source, staging)
            else:
                shutil.copy2(source, staging)
            os.replace(staging, target)
        finally:
            if staging.is_dir():
                shutil.rmtree(staging, ignore_errors=True)
            else:
                staging.unlink(missing_ok=True)

    def _ingest(self, project: Project, token: CancellationToken, event: Callable[[str, str, dict[str, Any]], None] | None) -> Path:
        cached = self._previous(project, "ingest")
        if cached and cached.metrics.get("selection_config_hash") == project.sampling.get("selection_config_hash"):
            self._emit(event, "log", "reusing durable keyframe set", {})
            return Path(cached.artifact_paths[0])
        state = self._stage(project, "ingest", event)
        if not project.run_id:
            raise RuntimeError("ingest requires an active run")
        destination = self.store.paths(project).run(project.run_id).frames
        destination.mkdir(parents=True, exist_ok=True)
        source = Path(project.input_path or "")
        if project.input_kind == "images":
            files = sorted(item for item in source.iterdir() if item.suffix.lower() in {".png", ".jpg", ".jpeg"})
            for index, image in enumerate(files):
                if token.is_cancelled:
                    raise InterruptedError(token.reason)
                target = destination / f"frame_{index:06d}.png"
                if not target.exists():
                    with Image.open(image) as loaded:
                        loaded.convert("RGB").save(target)
        else:
            probe, config = self._probe_from_project(project), self._sampling_config(project)
            expected_hash = selection_config_hash(probe, config)
            if project.sampling.get("analysis_status") != "complete" or project.sampling.get("selection_config_hash") != expected_hash:
                self._emit(event, "sampling", "Analyzing all source frames and building the candidate pool", {})
                analyzed = self.analyze_sampling(
                    project.project_id, active_run_id=project.run_id
                )
                project.sampling = deepcopy(analyzed.sampling)
            selected_indices = [int(value) for value in project.sampling.get("selected_frame_indices", [])]
            extract_selected_frames(source, selected_indices, probe.total_frames, self.runtime.ffmpeg, destination)
        frames = sorted(destination.glob("*.png"))
        if len(frames) < 3:
            raise RuntimeError("keyframe extraction produced fewer than three frames")
        sampling_metrics = {
            key: deepcopy(project.sampling.get(key))
            for key in (
                "source_total_frames",
                "sampling_mode",
                "requested_frame_count",
                "candidate_frame_count",
                "selected_frame_count",
                "selected_frame_indices",
                "rejected_frame_indices",
                "selection_config_hash",
                "in_frame",
                "out_frame",
                "trimmed_frame_count",
            )
            if key in project.sampling
        }
        state.artifact_paths, state.metrics = [str(destination)], {"frame_count": len(frames), **sampling_metrics}
        self._complete(project, "ingest", state, event)
        return destination

    def _manifest(self, worker: str) -> PluginManifest:
        return PluginManifest.model_validate_json((ROOT / "workers" / worker / "plugin.json").read_text(encoding="utf-8"))

    def _run_worker(
        self,
        project: Project,
        manifest: PluginManifest,
        request: StageRequest,
        python: Path | None,
        token: CancellationToken,
    ):
        if not project.run_id or request.run_id != project.run_id:
            raise RuntimeError("worker request does not belong to the active project run")
        run_paths = self.store.paths(project).run(project.run_id)
        run_paths.ensure()
        artifact_store = ArtifactStore(run_paths.artifacts)
        return SubprocessWorkerRunner(
            artifact_store,
            self.policy,
            worker_cwd=self.runtime.worker_cwd,
            python_executable=python or self.runtime.worker_python,
            poll_interval_seconds=0.1,
            cancellation_grace_seconds=5.0,
        ).run(
            request,
            manifest,
            timeout_seconds=7200,
            cancellation_token=token,
        )

    @staticmethod
    def _worker_diagnostics(
        stage: str, outcome: ExecutionOutcome
    ) -> dict[str, Any]:
        error = outcome.result.error
        error_code = getattr(error, "code", None) if error else None
        diagnostics: dict[str, Any] = {
            "worker_stage": stage,
            "worker_plugin_id": getattr(outcome.result, "plugin_id", None),
            "worker_error_code": (
                getattr(error_code, "value", str(error_code))
                if error_code is not None
                else None
            ),
            "worker_error_details": getattr(error, "details", {}) if error else {},
            "worker_return_code": getattr(outcome, "return_code", None),
            "worker_attempt_archive": (
                str(getattr(outcome, "attempt_archive", None))
                if getattr(outcome, "attempt_archive", None)
                else None
            ),
        }
        log_tails: dict[str, str] = {}
        archive = getattr(outcome, "attempt_archive", None)
        if archive and archive.is_dir():
            for log in sorted(archive.rglob("*.log")):
                try:
                    content = log.read_text(encoding="utf-8", errors="replace").strip()
                except OSError:
                    continue
                if content:
                    log_tails[log.relative_to(archive).as_posix()] = content[-2000:]
                if len(log_tails) == 4:
                    break
        diagnostics["worker_log_tails"] = log_tails
        return diagnostics

    def _worker_failure(
        self,
        stage: str,
        outcome: ExecutionOutcome,
        event: Callable[[str, str, dict[str, Any]], None] | None,
    ) -> WorkerStageError:
        message = (
            outcome.result.error.message
            if outcome.result.error
            else f"{stage} worker failed without a structured error"
        )
        diagnostics = self._worker_diagnostics(stage, outcome)
        self._emit(
            event,
            "worker_error",
            message,
            {"stage": stage, **diagnostics},
        )
        return WorkerStageError(message, diagnostics)

    @staticmethod
    def _is_colmap_quality_gate_failure(outcome: ExecutionOutcome) -> bool:
        error = outcome.result.error
        return bool(
            error
            and error.code is ErrorCode.OUTPUT_VALIDATION_FAILED
            and error.details.get("failure_kind") == "quality_gate"
        )

    def _reconstruct(self, project: Project, images: Path, token: CancellationToken, event: Callable[[str, str, dict[str, Any]], None] | None) -> Path:
        for stage in ("colmap", "fallback"):
            cached = self._previous(project, stage)
            if cached:
                if stage == "colmap" and project.stages.get("fallback", StageState()).status != "skipped":
                    self._skip(project, "fallback", "COLMAP passed the production quality gate", event)
                return Path(cached.artifact_paths[0])
        count = len(list(images.glob("*.png")))
        state = self._stage(project, "colmap", event)
        manifest = self._manifest("recon_colmap")
        request = StageRequest(run_id=project.run_id or "p2", stage_id="colmap", stage_kind=StageKind.RECONSTRUCTION, plugin_id=manifest.plugin_id, plugin_version=manifest.plugin_version, profile=ExecutionProfile.PRODUCTION, config={"config_version": "recon-colmap/v1", "colmap_executable": str(self.runtime.colmap), "colmap_executable_sha256": self._sha256(self.runtime.colmap), "images_path": str(images), "expected_image_count": count, "camera_model": "SIMPLE_RADIAL", "use_gpu": True, "minimum_registered_ratio": 0.9, "maximum_reprojection_error_px": 2.0, "maximum_step_over_median": 4.0})
        outcome = self._run_worker(project, manifest, request, None, token)
        self._raise_if_cancelled(token)
        if outcome.result.status is StageStatus.SUCCEEDED:
            state.artifact_paths, state.metrics = [str(item.path) for item in outcome.committed_artifacts], outcome.result.quality_report.metrics if outcome.result.quality_report else {}
            self._complete(project, "colmap", state, event)
            self._skip(project, "fallback", "COLMAP passed the production quality gate", event)
            return Path(state.artifact_paths[0])
        if token.is_cancelled:
            raise InterruptedError(token.reason)
        if not self._is_colmap_quality_gate_failure(outcome):
            state.status = "failed"
            state.error = (
                outcome.result.error.message
                if outcome.result.error
                else "COLMAP worker failed"
            )
            self._persist(project)
            raise self._worker_failure("colmap", outcome, event)
        state.status, state.error = "fallback_required", outcome.result.error.message if outcome.result.error else "COLMAP failed"
        self._persist(project)
        self._emit(event, "warning", "COLMAP failed its quality gate; starting MapAnything + COLMAP BA", {})
        return self._fallback(project, images, count, token, event)

    def _fallback(self, project: Project, images: Path, count: int, token: CancellationToken, event: Callable[[str, str, dict[str, Any]], None] | None) -> Path:
        state = self._stage(project, "fallback", event)
        manifest = self._manifest("recon_mapanything")
        config = {"config_version": "recon-mapanything/v1", "images_path": str(images), "expected_image_count": count, "mapanything_source": str(self.runtime.map_source), "mapanything_checkpoint": str(self.runtime.map_checkpoint), "mapanything_config": str(self.runtime.map_config), "dinov2_source": str(self.runtime.dino_source), "dinov2_checkpoint": str(self.runtime.dino_checkpoint), "colmap_executable": str(self.runtime.colmap), "trigger_minimum_registered_ratio": 0.9, "voxel_fraction": 0.015, "seed": 42}
        request = StageRequest(run_id=project.run_id or "p2", stage_id="fallback", stage_kind=StageKind.RECONSTRUCTION, plugin_id=manifest.plugin_id, plugin_version=manifest.plugin_version, profile=ExecutionProfile.PRODUCTION, config=config)
        outcome = self._run_worker(project, manifest, request, self.runtime.map_python, token)
        self._raise_if_cancelled(token)
        if outcome.result.status is not StageStatus.SUCCEEDED:
            raise self._worker_failure("fallback", outcome, event)
        state.artifact_paths, state.metrics = [str(item.path) for item in outcome.committed_artifacts], outcome.result.quality_report.metrics if outcome.result.quality_report else {}
        self._complete(project, "fallback", state, event)
        return Path(state.artifact_paths[0])

    def _prepare_training_input(
        self,
        project: Project,
        reconstruction: Path,
        images: Path,
        generation: int = 0,
    ) -> Path:
        if not project.run_id:
            raise RuntimeError("training input requires an active run")
        run_paths = self.store.paths(project).run(project.run_id)
        destination = run_paths.training
        sparse = destination / "sparse" / "0"
        training_images = destination / "images"
        sparse.mkdir(parents=True, exist_ok=True)
        training_images.mkdir(parents=True, exist_ok=True)
        source_sparse = reconstruction / ("sparse_ba_txt" if (reconstruction / "sparse_ba_txt").is_dir() else "model_txt")
        for name in ("cameras.txt", "images.txt", "points3D.txt"):
            shutil.copy2(source_sparse / name, sparse / name)
        camera_sizes: dict[str, tuple[int, int]] = {}
        for line in (sparse / "cameras.txt").read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#"):
                values = line.split(); camera_sizes[values[0]] = (int(values[2]), int(values[3]))
        image_camera: dict[str, str] = {}
        for line in (sparse / "images.txt").read_text(encoding="utf-8").splitlines():
            if line and not line.startswith("#"):
                values = line.split()
                if len(values) >= 10:
                    image_camera[values[9]] = values[8]
        records = []
        source_fps = float(project.sampling.get("fps", 1.0))
        for index, source in enumerate(sorted(images.glob("*.png"))):
            target = training_images / source.name
            size = camera_sizes.get(image_camera.get(source.name, ""))
            with Image.open(source) as loaded:
                converted = loaded.convert("RGB")
                if size and converted.size != size:
                    converted = converted.resize(size, Image.Resampling.LANCZOS)
                converted.save(target)
            try:
                source_index = int(source.stem.rsplit("_", 1)[1])
            except (IndexError, ValueError):
                source_index = index
            records.append({"frame_id": f"scene:{source_index:06d}", "image_path": f"scenes/scene/frames/{source.name}", "sha256": self._sha256(target), "sample_index": source_index, "nominal_timestamp_seconds": source_index / max(source_fps, 1e-9), "split": "holdout" if index % 8 == 4 else "train"})
        if sum(record["split"] == "holdout" for record in records) == 0:
            records[-1]["split"] = "holdout"
        provenance_keys = (
            "source_total_frames", "sampling_mode", "requested_frame_count",
            "candidate_frame_count", "selected_frame_count", "selected_frame_indices",
            "rejected_frame_indices", "selection_config_hash",
            "in_frame", "out_frame", "trimmed_frame_count",
        )
        sampling_provenance = {key: deepcopy(project.sampling.get(key)) for key in provenance_keys if key in project.sampling}
        dataset = {"schema_version": "desktop-dataset/v1", "dataset_id": project.project_id, "sampling_provenance": sampling_provenance, "scenes": [{"scene_id": "scene", "source": {"file_name": Path(project.input_path or "input").name, "sha256": self._sha256(Path(project.input_path)) if Path(project.input_path or "").is_file() else "0" * 64}, "frames": records}]}
        atomic_write_json(destination / "dataset.manifest.json", dataset)
        atomic_write_json(destination / "sampling.provenance.json", sampling_provenance)
        project.sampling["camera_timeline"] = build_camera_timeline(project.sampling, images, sparse)
        project.sampling["camera_mapping_stale"] = False
        atomic_write_json(
            run_paths.timeline_manifest,
            {
                "schema_version": "gaussianos-camera-timeline/v1",
                "project_id": project.project_id,
                "run_id": project.run_id,
                "generation": generation,
                "stage": "timeline",
                "records": project.sampling["camera_timeline"],
            },
        )
        self._persist(project)
        return destination

    def _train(self, project: Project, data_dir: Path, token: CancellationToken, event: Callable[[str, str, dict[str, Any]], None] | None) -> Path:
        cached = self._previous(project, "train")
        if cached:
            return Path(cached.artifact_paths[0])
        state = self._stage(project, "train", event)
        manifest = self._manifest("train_gsplat")
        reconstruction = "recon.mapanything" if project.stages.get("fallback", StageState()).status == "succeeded" else "recon.colmap"
        request = StageRequest(run_id=project.run_id or "p2", stage_id="train", stage_kind=StageKind.TRAINING, plugin_id=manifest.plugin_id, plugin_version=manifest.plugin_version, profile=ExecutionProfile.PRODUCTION, config={"config_version": "train-gsplat/v1", "scene_id": "scene", "data_dir": str(data_dir), "dataset_manifest": str(data_dir / "dataset.manifest.json"), "gsplat_source": str(self.runtime.gsplat_source), "data_factor": 1, "max_steps": PROFILES[project.profile]["steps"], "seed": 42, "sh_degree": 3, "sh_degree_interval": 500, "minimum_psnr_gain_db": -5.0, "reconstruction_plugin_id": reconstruction})
        outcome = self._run_worker(project, manifest, request, self.runtime.gsplat_python, token)
        self._raise_if_cancelled(token)
        if outcome.result.status is not StageStatus.SUCCEEDED:
            if token.is_cancelled:
                raise InterruptedError(token.reason)
            raise RuntimeError(outcome.result.error.message if outcome.result.error else "gsplat worker failed")
        state.artifact_paths, state.metrics = [str(item.path) for item in outcome.committed_artifacts], outcome.result.quality_report.metrics if outcome.result.quality_report else {}
        if state.metrics.get("psnr_gain_db", 0.0) < 0.0:
            project.warnings.append("Training holdout PSNR did not improve; the artifact remains available for diagnosis.")
        self._complete(project, "train", state, event)
        return Path(state.artifact_paths[0])

    def _validate_and_export(
        self,
        project: Project,
        training: Path,
        event: Callable[[str, str, dict[str, Any]], None] | None,
        generation: int = 0,
        *,
        cancellation_token: CancellationToken | None = None,
    ) -> None:
        self._raise_if_cancelled(cancellation_token)
        if not project.run_id:
            raise RuntimeError("validation requires an active run")
        paths = self.store.paths(project)
        if project.workspace_kind == "isolated" and not paths.contains(training):
            raise RuntimeError("training artifact is outside the owning project workspace")
        run_paths = paths.run(project.run_id)
        state = self._stage(project, "validate", event)
        from packages.exportkit import read_gaussian_ply
        from packages.scene_bundle import load_scene_bundle
        bundle = next(training.glob("*.scene-bundle")); ply = next(training.glob("*.graphdeco-gs-v1.ply"))
        loaded_bundle, loaded_ply = load_scene_bundle(bundle), read_gaussian_ply(ply)
        if loaded_bundle.gaussians is None or len(loaded_bundle.gaussians.means) != len(loaded_ply.means):
            raise RuntimeError("Gaussian PLY consumer validation count mismatch")
        try:
            import gsply
            gsply_count = int(gsply.plyread(ply).means.shape[0])
        except ImportError as exc:
            raise RuntimeError("desktop consumer validation requires gsply==0.4.6") from exc
        if gsply_count != len(loaded_ply.means):
            raise RuntimeError("gsply consumer validation count mismatch")
        state.artifact_paths, state.metrics = [str(bundle), str(ply)], {"gaussian_count": int(len(loaded_ply.means)), "gsply_gaussian_count": gsply_count}
        self._complete(project, "validate", state, event)
        self._raise_if_cancelled(cancellation_token)
        export = self._stage(project, "export", event)
        destination = run_paths.exports
        destination.mkdir(parents=True, exist_ok=True)
        reconstruction_paths = project.stages.get("fallback", StageState()).artifact_paths or project.stages.get("colmap", StageState()).artifact_paths
        reconstruction = Path(reconstruction_paths[0]) if reconstruction_paths else None
        pointcloud = training / "scene.pointcloud.ply"
        fallback_pointcloud = None
        if reconstruction:
            candidates = (reconstruction / "scene.pointcloud.ply", reconstruction / "sparse" / "points.ply")
            fallback_pointcloud = next((item for item in candidates if item.is_file()), None)
        for source in (ply, bundle):
            self._raise_if_cancelled(cancellation_token)
            target = destination / source.name
            self._atomic_copy(source, target)
        exported_bundle = destination / bundle.name
        if exported_bundle.is_dir() and project.sampling:
            provenance_keys = (
                "source_total_frames", "sampling_mode", "requested_frame_count",
                "candidate_frame_count", "selected_frame_count", "selected_frame_indices",
                "rejected_frame_indices", "selection_config_hash",
                "in_frame", "out_frame", "trimmed_frame_count",
            )
            sampling_provenance = {key: deepcopy(project.sampling.get(key)) for key in provenance_keys if key in project.sampling}
            atomic_write_json(
                exported_bundle / "sampling.provenance.json", sampling_provenance
            )
        if pointcloud.exists():
            self._atomic_copy(pointcloud, destination / pointcloud.name)
        elif fallback_pointcloud and fallback_pointcloud.is_file():
            self._atomic_copy(fallback_pointcloud, destination / "scene.pointcloud.ply")
        self._raise_if_cancelled(cancellation_token)
        export.artifact_paths = [str(item) for item in destination.iterdir()]
        export.metrics = {"glb": "reserved", "spz": "reserved"}
        self._complete(project, "export", export, event)
        viewer_pointcloud = (
            destination / "scene.pointcloud.ply"
            if (destination / "scene.pointcloud.ply").is_file()
            else None
        )
        atomic_write_json(
            paths.viewer_manifest,
            {
                "schema_version": "gaussianos-viewer-scene/v1",
                "project_id": project.project_id,
                "run_id": project.run_id,
                "generation": generation,
                "stage": "viewer",
                "bundle": str(bundle),
                "gaussian": str(ply),
                "pointcloud": str(viewer_pointcloud) if viewer_pointcloud else None,
                "committed": True,
            },
        )
        source_name = Path(project.input_path or "").stem
        if source_name == "002" and not any("Scene 002" in warning for warning in project.warnings):
            project.warnings.append("Scene 002 diagnostic: skyline/building tearing is known; no concealment post-processing was applied.")
            self._persist(project)
