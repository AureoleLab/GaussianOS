"""Prepare the frozen P1 inputs and run the real gsplat worker for all scenes."""

from __future__ import annotations

import argparse
import json
import os
import shutil
from pathlib import Path

from PIL import Image

from packages.artifact_store import ArtifactStore
from packages.licensing import ProfilePolicyRegistry
from packages.pipeline import SubprocessWorkerRunner
from packages.plugin_sdk import ExecutionProfile, PluginManifest, StageKind, StageRequest


ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "benchmark_runs" / "p1_dataset_v1" / "dataset.manifest.json"
RUN_ROOT = ROOT / "benchmark_runs" / "gsplat-1.5.3"
TRAIN_PYTHON = ROOT / ".gaussian-factory" / "envs" / "gsplat-1.5.3" / "Scripts" / "python.exe"
SOURCE = ROOT / ".gaussian-factory" / "sources" / "gsplat-v1.5.3"


def _prepare_scene(scene_id: str, factor: int) -> Path:
    destination = RUN_ROOT / "inputs" / scene_id
    images = destination / "images"
    resized = destination / f"images_{factor}"
    sparse = destination / "sparse" / "0"
    images.mkdir(parents=True, exist_ok=True)
    resized.mkdir(parents=True, exist_ok=True)
    sparse.mkdir(parents=True, exist_ok=True)
    source_images = ROOT / "benchmark_runs" / "p1_dataset_v1" / "scenes" / scene_id / "frames"
    source_model = ROOT / "benchmark_runs" / "colmap_3.13.0" / scene_id / "attempt-001" / "sparse_txt"
    for source in sorted(source_images.glob("*.png")):
        full = images / source.name
        if not full.exists():
            try:
                os.link(source, full)
            except OSError:
                shutil.copy2(source, full)
        downsampled = resized / source.name
        if not downsampled.exists():
            with Image.open(source) as image:
                size = (round(image.width / factor), round(image.height / factor))
                image.resize(size, Image.Resampling.LANCZOS).save(downsampled, format="PNG")
    # The gsplat 1.5.3 example pins the legacy pure-Python pycolmap reader.
    # Feed it COLMAP text so COLMAP 3.13's rigs/frames binary additions cannot
    # be misinterpreted as the legacy images.bin layout.
    for stale in sparse.iterdir():
        if stale.is_file():
            stale.unlink()
    for source in (source_model / "cameras.txt", source_model / "images.txt", source_model / "points3D.txt"):
        target = sparse / source.name
        shutil.copy2(source, target)
    return destination


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scenes", nargs="+", default=["001", "002", "003"])
    parser.add_argument("--steps", type=int, default=7000)
    parser.add_argument("--factor", type=int, default=4)
    parser.add_argument("--timeout-seconds", type=float, default=7200)
    args = parser.parse_args()
    manifest = PluginManifest.model_validate_json(
        (ROOT / "workers" / "train_gsplat" / "plugin.json").read_text(encoding="utf-8")
    )
    registry = ProfilePolicyRegistry.from_directory(ROOT / "configs" / "profiles")
    store = ArtifactStore(ROOT / ".gaussian-factory" / "artifact-store")
    runner = SubprocessWorkerRunner(
        store,
        registry,
        worker_cwd=ROOT,
        python_executable=TRAIN_PYTHON,
        poll_interval_seconds=0.1,
        cancellation_grace_seconds=5.0,
    )
    summary: dict[str, object] = {
        "protocol": "p1-gsplat-real-training/v1",
        "gsplat_version": "1.5.3",
        "gsplat_commit": "937e29912570c372bed6747a5c9bf85fed877bae",
        "steps": args.steps,
        "data_factor": args.factor,
        "scenes": {},
    }
    for scene_id in args.scenes:
        data_dir = _prepare_scene(scene_id, args.factor)
        request = StageRequest(
            run_id="p1-gsplat-1.5.3",
            stage_id=f"train-{scene_id}",
            stage_kind=StageKind.TRAINING,
            plugin_id=manifest.plugin_id,
            plugin_version=manifest.plugin_version,
            profile=ExecutionProfile.PRODUCTION,
            config={
                "config_version": "train-gsplat/v1",
                "scene_id": scene_id,
                "data_dir": str(data_dir),
                "dataset_manifest": str(DATASET),
                "gsplat_source": str(SOURCE),
                "data_factor": args.factor,
                "max_steps": args.steps,
                "seed": 42,
                "sh_degree": 3,
                "sh_degree_interval": 500,
                "minimum_psnr_gain_db": 0.25,
            },
        )
        outcome = runner.run(request, manifest, timeout_seconds=args.timeout_seconds)
        item: dict[str, object] = {
            "status": outcome.result.status.value,
            "return_code": outcome.return_code,
            "attempt_archive": str(outcome.attempt_archive) if outcome.attempt_archive else None,
            "artifacts": [str(record.path) for record in outcome.committed_artifacts],
        }
        if outcome.result.quality_report is not None:
            item["metrics"] = outcome.result.quality_report.metrics
        if outcome.result.error is not None:
            item["error"] = outcome.result.error.model_dump(mode="json")
        summary["scenes"][scene_id] = item
        RUN_ROOT.mkdir(parents=True, exist_ok=True)
        (RUN_ROOT / "run-summary.json").write_text(
            json.dumps(summary, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(json.dumps({scene_id: item}, indent=2, ensure_ascii=False), flush=True)
        if outcome.result.status.value != "succeeded":
            return 10
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
