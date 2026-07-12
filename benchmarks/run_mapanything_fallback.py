"""Run the production-gated MapAnything fallback on the frozen hard case."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from packages.artifact_store import ArtifactStore
from packages.licensing import ProfilePolicyRegistry
from packages.pipeline import SubprocessWorkerRunner
from packages.plugin_sdk import ExecutionProfile, PluginManifest, StageKind, StageRequest


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--normal-gate", action="store_true")
    args = parser.parse_args()
    manifest = PluginManifest.model_validate_json(
        (ROOT / "workers" / "recon_mapanything" / "plugin.json").read_text(encoding="utf-8")
    )
    runner = SubprocessWorkerRunner(
        ArtifactStore(ROOT / ".gaussian-factory" / "artifact-store"),
        ProfilePolicyRegistry.from_directory(ROOT / "configs" / "profiles"),
        worker_cwd=ROOT,
        python_executable=ROOT / ".gaussian-factory" / "envs" / "mapanything-1.1.2" / "Scripts" / "python.exe",
        poll_interval_seconds=0.1,
        cancellation_grace_seconds=5.0,
    )
    if args.normal_gate:
        images_path = ROOT / "benchmark_runs" / "p1_dataset_v1" / "scenes" / "001" / "frames"
        expected_count = 39
        stage_id = "normal-gate-001"
    else:
        images_path = ROOT / "benchmark_runs" / "mapanything-fallback" / "hard-case-001" / "images"
        expected_count = 12
        stage_id = "hard-case-001"
    request = StageRequest(
        run_id="p1-mapanything-fallback",
        stage_id=stage_id,
        stage_kind=StageKind.RECONSTRUCTION,
        plugin_id=manifest.plugin_id,
        plugin_version=manifest.plugin_version,
        profile=ExecutionProfile.PRODUCTION,
        config={
            "config_version": "recon-mapanything/v1",
            "images_path": str(images_path.resolve()),
            "expected_image_count": expected_count,
            "mapanything_source": str((ROOT / ".gaussian-factory" / "sources" / "map-anything-v1.1.2").resolve()),
            "mapanything_checkpoint": str((ROOT / ".gaussian-factory" / "downloads" / "map-anything-apache-00f9c245" / "model.safetensors").resolve()),
            "mapanything_config": str((ROOT / ".gaussian-factory" / "downloads" / "map-anything-apache-00f9c245" / "config.json").resolve()),
            "dinov2_source": str((ROOT / ".gaussian-factory" / "sources" / "dinov2-7764ea0").resolve()),
            "dinov2_checkpoint": str(Path.home() / ".cache" / "torch" / "hub" / "checkpoints" / "dinov2_vitg14_pretrain.pth"),
            "colmap_executable": str((ROOT / ".gaussian-factory" / "tools" / "colmap" / "3.13.0" / "bin" / "colmap.exe").resolve()),
            "trigger_minimum_registered_ratio": 0.9,
            "voxel_fraction": 0.015,
            "seed": 42,
        },
    )
    outcome = runner.run(request, manifest, timeout_seconds=3600)
    result = {
        "status": outcome.result.status.value,
        "return_code": outcome.return_code,
        "artifacts": [str(item.path) for item in outcome.committed_artifacts],
        "attempt_archive": str(outcome.attempt_archive) if outcome.attempt_archive else None,
        "quality_report": outcome.result.quality_report.model_dump(mode="json") if outcome.result.quality_report else None,
        "error": outcome.result.error.model_dump(mode="json") if outcome.result.error else None,
    }
    destination = ROOT / "benchmark_runs" / "mapanything-fallback" / ("normal-gate-summary.json" if args.normal_gate else "run-summary.json")
    destination.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))
    if args.normal_gate:
        correctly_denied = outcome.result.error is not None and outcome.result.error.code.value == "policy_denied"
        return 0 if correctly_denied else 10
    return 0 if outcome.result.status.value == "succeeded" else 10


if __name__ == "__main__":
    raise SystemExit(main())
