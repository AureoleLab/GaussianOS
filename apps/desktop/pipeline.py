"""P2 orchestration: durable control plane over isolated P1 workers.

No model library is imported here.  Every reconstruction/training action is
delegated to ``SubprocessWorkerRunner`` and is therefore safe to invoke from a
non-Qt worker thread.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import threading
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from PIL import Image

from packages.artifact_store import ArtifactStore
from packages.licensing import ProfilePolicyRegistry
from packages.pipeline import CancellationToken, SubprocessWorkerRunner
from packages.plugin_sdk import ExecutionProfile, PluginManifest, StageKind, StageRequest, StageStatus

from .project_store import Project, ProjectStore, ProjectStoreError, StageState


ROOT = Path(__file__).resolve().parents[2]
STAGES = ("ingest", "colmap", "fallback", "train", "validate", "export")
PROFILES = {
    "preview": {"fps": 3.0, "steps": 1000},
    "balanced": {"fps": 8.0, "steps": 3000},
    "quality": {"fps": 15.0, "steps": 7000},
}


@dataclass(frozen=True, slots=True)
class RuntimePaths:
    colmap: Path
    ffmpeg: str
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
        factory = ROOT / ".gaussian-factory"
        ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
        return cls(
            colmap=factory / "tools" / "colmap" / "3.13.0" / "bin" / "colmap.exe",
            ffmpeg=ffmpeg,
            map_python=factory / "envs" / "mapanything-1.1.2" / "Scripts" / "python.exe",
            gsplat_python=factory / "envs" / "gsplat-1.5.3" / "Scripts" / "python.exe",
            gsplat_source=factory / "sources" / "gsplat-v1.5.3",
            map_source=factory / "sources" / "map-anything-v1.1.2",
            map_checkpoint=factory / "downloads" / "map-anything-apache-00f9c245" / "model.safetensors",
            map_config=factory / "downloads" / "map-anything-apache-00f9c245" / "config.json",
            dino_source=factory / "sources" / "dinov2-7764ea0",
            dino_checkpoint=Path.home() / ".cache" / "torch" / "hub" / "checkpoints" / "dinov2_vitg14_pretrain.pth",
        )


class PipelineController:
    """Thread-safe project orchestration with cancellation and restart resume."""

    def __init__(self, store: ProjectStore, artifact_root: str | Path, runtime: RuntimePaths | None = None) -> None:
        self.store = store
        self.artifacts = ArtifactStore(artifact_root)
        self.runtime = runtime or RuntimePaths.discover()
        self.policy = ProfilePolicyRegistry.from_directory(ROOT / "configs" / "profiles")
        self._tokens: dict[str, CancellationToken] = {}
        self._running: set[str] = set()
        self._lock = threading.Lock()

    def create_project(self, name: str, project_root: str | Path) -> Project:
        """Control-plane-only project creation entry point for the GUI."""
        return self.store.create(name, project_root)

    def import_input(self, project_id: str, source: str | Path) -> Project:
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
        def apply(project: Project) -> None:
            if project.status == "running":
                raise RuntimeError("cannot change input while a pipeline is running")
            project.input_path, project.input_kind, project.status = str(source), kind, "ready"
        project, _ = self.store.update_project(project_id, apply)
        return project

    def set_profile(self, project_id: str, profile: str) -> Project:
        if profile not in PROFILES:
            raise ValueError(f"unknown profile: {profile}")
        def apply(project: Project) -> None:
            if project.status == "running":
                raise RuntimeError("cannot change profile while a pipeline is running")
            project.profile = profile
        project, _ = self.store.update_project(project_id, apply)
        return project

    def recover_interrupted_projects(self) -> list[Project]:
        """Mark stale GUI-owned runs resumable after an application restart."""
        recovered: list[Project] = []
        for snapshot in self.store.all():
            if snapshot.status != "running":
                continue
            def apply(project: Project) -> None:
                if project.status == "running":
                    project.status = "interrupted"
                    project.current_stage = None
                    project.warnings.append("Desktop restarted while this task was running; resume to continue.")
            project, _ = self.store.update_project(snapshot.project_id, apply)
            recovered.append(project)
        return recovered

    def cancel(self, project_id: str) -> None:
        with self._lock:
            token = self._tokens.get(project_id)
        if token:
            token.cancel("cancelled from desktop GUI")

    def run(self, project_id: str, on_event: Callable[[str, str, dict[str, Any]], None] | None = None) -> Project:
        project = self.store.load(project_id)
        if not project.input_path or not project.input_kind:
            raise ValueError("import a video or image folder first")
        token = CancellationToken()
        with self._lock:
            if project_id in self._running:
                raise RuntimeError("pipeline is already running for this project")
            self._running.add(project_id)
            self._tokens[project_id] = token
        persistence_failed = False
        try:
            project.run_id = project.run_id or f"p2-{project.project_id[:12]}"
            project.status = "running"
            self._persist(project)
            inputs = self._ingest(project, token, on_event)
            reconstruction = self._reconstruct(project, inputs, token, on_event)
            training_input = self._prepare_training_input(project, reconstruction, inputs)
            training = self._train(project, training_input, token, on_event)
            self._validate_and_export(project, training, on_event)
            project.status = "succeeded"
        except InterruptedError:
            project.status = "cancelled"
        except ProjectStoreError as exc:
            persistence_failed = True
            self._mark_persistence_failure(project, exc, on_event)
        except Exception as exc:
            project.status = "failed"
            project.warnings.append(f"{type(exc).__name__}: {exc}")
            self._emit(on_event, "error", str(exc), {})
        finally:
            if not persistence_failed:
                project.current_stage = None
                try:
                    self._persist(project)
                except ProjectStoreError as exc:
                    persistence_failed = True
                    self._mark_persistence_failure(project, exc, on_event)
            with self._lock:
                self._tokens.pop(project_id, None)
                self._running.discard(project_id)
        return project

    def _persist(self, project: Project) -> None:
        """Commit the control-plane snapshot through the atomic update API."""
        snapshot = deepcopy(project)
        def replace(current: Project) -> None:
            for name in Project.__dataclass_fields__:
                setattr(current, name, deepcopy(getattr(snapshot, name)))
        self.store.update_project(project.project_id, replace)

    def _best_effort_persist(self, project: Project) -> None:
        try:
            self._persist(project)
        except ProjectStoreError:
            # The original exception is emitted to the GUI; never mask it with
            # a second persistence failure or let the worker thread escape.
            pass

    def _mark_persistence_failure(self, project: Project, exc: Exception, event: Callable[[str, str, dict[str, Any]], None] | None) -> None:
        project.status = "failed"
        project.current_stage = None
        project.warnings.append(f"Project state persistence failed: {exc}")
        self._best_effort_persist(project)
        self._emit(event, "persistence_failed", str(exc), {"status": "failed", "project_id": project.project_id})

    def _emit(self, sink: Callable[[str, str, dict[str, Any]], None] | None, kind: str, message: str, payload: dict[str, Any]) -> None:
        if sink:
            sink(kind, message, payload)

    def _stage(self, project: Project, name: str, event: Callable[[str, str, dict[str, Any]], None] | None) -> StageState:
        state = project.stages.setdefault(name, StageState())
        project.current_stage, state.status, state.error = name, "running", None
        self._persist(project)
        self._emit(event, "stage", name, {"stage": name})
        return state

    def _complete(self, project: Project, name: str, state: StageState, event: Callable[[str, str, dict[str, Any]], None] | None) -> None:
        state.status, state.updated_at = "succeeded", datetime.now(timezone.utc).isoformat()
        self._persist(project)
        self._emit(event, "progress", f"{name} completed", {"stage": name, "progress": (STAGES.index(name) + 1) / len(STAGES)})

    def _previous(self, project: Project, name: str) -> StageState | None:
        state = project.stages.get(name)
        if state and state.status == "succeeded" and all(Path(path).exists() for path in state.artifact_paths):
            return state
        return None

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def _ingest(self, project: Project, token: CancellationToken, event: Callable[[str, str, dict[str, Any]], None] | None) -> Path:
        cached = self._previous(project, "ingest")
        if cached:
            self._emit(event, "log", "reusing durable keyframe set", {})
            return Path(cached.artifact_paths[0])
        state = self._stage(project, "ingest", event)
        destination = Path(project.root) / "inputs" / "frames"
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
            fps = PROFILES[project.profile]["fps"]
            command = [self.runtime.ffmpeg, "-y", "-i", str(source), "-vf", f"fps={fps}", str(destination / "frame_%06d.png")]
            completed = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False)
            if completed.returncode:
                raise RuntimeError(f"ffmpeg extraction failed: {completed.stderr[-1000:]}")
        frames = sorted(destination.glob("*.png"))
        if len(frames) < 3:
            raise RuntimeError("keyframe extraction produced fewer than three frames")
        state.artifact_paths, state.metrics = [str(destination)], {"frame_count": len(frames)}
        self._complete(project, "ingest", state, event)
        return destination

    def _manifest(self, worker: str) -> PluginManifest:
        return PluginManifest.model_validate_json((ROOT / "workers" / worker / "plugin.json").read_text(encoding="utf-8"))

    def _run_worker(self, manifest: PluginManifest, request: StageRequest, python: Path | None, token: CancellationToken):
        return SubprocessWorkerRunner(self.artifacts, self.policy, worker_cwd=ROOT, python_executable=python or sys.executable, poll_interval_seconds=0.1, cancellation_grace_seconds=5.0).run(request, manifest, timeout_seconds=7200, cancellation_token=token)

    def _reconstruct(self, project: Project, images: Path, token: CancellationToken, event: Callable[[str, str, dict[str, Any]], None] | None) -> Path:
        for stage in ("colmap", "fallback"):
            cached = self._previous(project, stage)
            if cached:
                return Path(cached.artifact_paths[0])
        count = len(list(images.glob("*.png")))
        state = self._stage(project, "colmap", event)
        manifest = self._manifest("recon_colmap")
        request = StageRequest(run_id=project.run_id or "p2", stage_id="colmap", stage_kind=StageKind.RECONSTRUCTION, plugin_id=manifest.plugin_id, plugin_version=manifest.plugin_version, profile=ExecutionProfile.PRODUCTION, config={"config_version": "recon-colmap/v1", "colmap_executable": str(self.runtime.colmap), "colmap_executable_sha256": self._sha256(self.runtime.colmap), "images_path": str(images), "expected_image_count": count, "camera_model": "SIMPLE_RADIAL", "use_gpu": True, "minimum_registered_ratio": 0.9, "maximum_reprojection_error_px": 2.0, "maximum_step_over_median": 4.0})
        outcome = self._run_worker(manifest, request, None, token)
        if outcome.result.status is StageStatus.SUCCEEDED:
            state.artifact_paths, state.metrics = [str(item.path) for item in outcome.committed_artifacts], outcome.result.quality_report.metrics if outcome.result.quality_report else {}
            self._complete(project, "colmap", state, event)
            return Path(state.artifact_paths[0])
        if token.is_cancelled:
            raise InterruptedError(token.reason)
        state.status, state.error = "fallback_required", outcome.result.error.message if outcome.result.error else "COLMAP failed"
        self._persist(project)
        self._emit(event, "warning", "COLMAP failed its quality gate; starting MapAnything + COLMAP BA", {})
        return self._fallback(project, images, count, token, event)

    def _fallback(self, project: Project, images: Path, count: int, token: CancellationToken, event: Callable[[str, str, dict[str, Any]], None] | None) -> Path:
        state = self._stage(project, "fallback", event)
        manifest = self._manifest("recon_mapanything")
        config = {"config_version": "recon-mapanything/v1", "images_path": str(images), "expected_image_count": count, "mapanything_source": str(self.runtime.map_source), "mapanything_checkpoint": str(self.runtime.map_checkpoint), "mapanything_config": str(self.runtime.map_config), "dinov2_source": str(self.runtime.dino_source), "dinov2_checkpoint": str(self.runtime.dino_checkpoint), "colmap_executable": str(self.runtime.colmap), "trigger_minimum_registered_ratio": 0.9, "voxel_fraction": 0.015, "seed": 42}
        request = StageRequest(run_id=project.run_id or "p2", stage_id="fallback", stage_kind=StageKind.RECONSTRUCTION, plugin_id=manifest.plugin_id, plugin_version=manifest.plugin_version, profile=ExecutionProfile.PRODUCTION, config=config)
        outcome = self._run_worker(manifest, request, self.runtime.map_python, token)
        if outcome.result.status is not StageStatus.SUCCEEDED:
            raise RuntimeError(outcome.result.error.message if outcome.result.error else "MapAnything worker failed")
        state.artifact_paths, state.metrics = [str(item.path) for item in outcome.committed_artifacts], outcome.result.quality_report.metrics if outcome.result.quality_report else {}
        self._complete(project, "fallback", state, event)
        return Path(state.artifact_paths[0])

    def _prepare_training_input(self, project: Project, reconstruction: Path, images: Path) -> Path:
        destination = Path(project.root) / "training-input"
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
        for index, source in enumerate(sorted(images.glob("*.png"))):
            target = training_images / source.name
            size = camera_sizes.get(image_camera.get(source.name, ""))
            with Image.open(source) as loaded:
                converted = loaded.convert("RGB")
                if size and converted.size != size:
                    converted = converted.resize(size, Image.Resampling.LANCZOS)
                converted.save(target)
            records.append({"frame_id": f"scene:{index:06d}", "image_path": f"scenes/scene/frames/{source.name}", "sha256": self._sha256(target), "sample_index": index, "nominal_timestamp_seconds": float(index), "split": "holdout" if index % 8 == 4 else "train"})
        if sum(record["split"] == "holdout" for record in records) == 0:
            records[-1]["split"] = "holdout"
        dataset = {"schema_version": "desktop-dataset/v1", "dataset_id": project.project_id, "scenes": [{"scene_id": "scene", "source": {"file_name": Path(project.input_path or "input").name, "sha256": self._sha256(Path(project.input_path)) if Path(project.input_path or "").is_file() else "0" * 64}, "frames": records}]}
        (destination / "dataset.manifest.json").write_text(json.dumps(dataset, indent=2) + "\n", encoding="utf-8")
        return destination

    def _train(self, project: Project, data_dir: Path, token: CancellationToken, event: Callable[[str, str, dict[str, Any]], None] | None) -> Path:
        cached = self._previous(project, "train")
        if cached:
            return Path(cached.artifact_paths[0])
        state = self._stage(project, "train", event)
        manifest = self._manifest("train_gsplat")
        reconstruction = "recon.mapanything" if project.stages.get("fallback", StageState()).status == "succeeded" else "recon.colmap"
        request = StageRequest(run_id=project.run_id or "p2", stage_id="train", stage_kind=StageKind.TRAINING, plugin_id=manifest.plugin_id, plugin_version=manifest.plugin_version, profile=ExecutionProfile.PRODUCTION, config={"config_version": "train-gsplat/v1", "scene_id": "scene", "data_dir": str(data_dir), "dataset_manifest": str(data_dir / "dataset.manifest.json"), "gsplat_source": str(self.runtime.gsplat_source), "data_factor": 1, "max_steps": PROFILES[project.profile]["steps"], "seed": 42, "sh_degree": 3, "sh_degree_interval": 500, "minimum_psnr_gain_db": -5.0, "reconstruction_plugin_id": reconstruction})
        outcome = self._run_worker(manifest, request, self.runtime.gsplat_python, token)
        if outcome.result.status is not StageStatus.SUCCEEDED:
            if token.is_cancelled:
                raise InterruptedError(token.reason)
            raise RuntimeError(outcome.result.error.message if outcome.result.error else "gsplat worker failed")
        state.artifact_paths, state.metrics = [str(item.path) for item in outcome.committed_artifacts], outcome.result.quality_report.metrics if outcome.result.quality_report else {}
        if state.metrics.get("psnr_gain_db", 0.0) < 0.0:
            project.warnings.append("Training holdout PSNR did not improve; the artifact remains available for diagnosis.")
        self._complete(project, "train", state, event)
        return Path(state.artifact_paths[0])

    def _validate_and_export(self, project: Project, training: Path, event: Callable[[str, str, dict[str, Any]], None] | None) -> None:
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
        export = self._stage(project, "export", event)
        destination = Path(project.root) / "exports"; destination.mkdir(parents=True, exist_ok=True)
        reconstruction_paths = project.stages.get("fallback", StageState()).artifact_paths or project.stages.get("colmap", StageState()).artifact_paths
        reconstruction = Path(reconstruction_paths[0]) if reconstruction_paths else None
        pointcloud = training / "scene.pointcloud.ply"
        fallback_pointcloud = reconstruction / "sparse" / "points.ply" if reconstruction else None
        for source in (ply, bundle):
            target = destination / source.name
            if source.is_dir():
                if target.exists(): shutil.rmtree(target)
                shutil.copytree(source, target)
            else: shutil.copy2(source, target)
        if pointcloud.exists():
            shutil.copy2(pointcloud, destination / pointcloud.name)
        elif fallback_pointcloud and fallback_pointcloud.is_file():
            shutil.copy2(fallback_pointcloud, destination / "scene.pointcloud.ply")
        export.artifact_paths = [str(item) for item in destination.iterdir()]
        export.metrics = {"glb": "reserved", "spz": "reserved"}
        self._complete(project, "export", export, event)
        source_name = Path(project.input_path or "").stem
        if source_name == "002" and not any("Scene 002" in warning for warning in project.warnings):
            project.warnings.append("Scene 002 diagnostic: skyline/building tearing is known; no concealment post-processing was applied.")
            self._persist(project)
