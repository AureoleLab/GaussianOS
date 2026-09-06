"""Execute the shipped standalone MapAnything worker on packaged test frames.

The parent only prepares the public worker request; inference, source locks,
COLMAP bundle adjustment, quality gates and artifact writing are production code.
This is a local packaged-worker check, not independent-machine acceptance.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from packages.external_process import external_environment


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", type=Path, required=True)
    parser.add_argument("--images", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    stage, output, images = args.stage.resolve(), args.output.resolve(), args.images.resolve()
    if output.exists():
        raise RuntimeError(f"Refusing to replace prior evidence: {output}")
    output.mkdir(parents=True)
    runtime = stage / "Runtime"
    request = {
        "schema_version": "1.0.0", "request_id": str(uuid4()), "run_id": "public-beta-fallback",
        "stage_id": "fallback", "stage_kind": "reconstruction", "plugin_id": "recon.mapanything",
        "plugin_version": "v1.1.2", "profile": "production", "attempt_id": "attempt-" + uuid4().hex,
        "attempt_dir": str(output / "attempt"), "cancellation_file": str(output / "cancel.json"),
        "deadline_utc": None, "inputs": [], "config": {
            "config_version": "recon-mapanything/v1", "images_path": str(images),
            "expected_image_count": sum(p.is_file() and p.suffix.lower() in {".png", ".jpg", ".jpeg"} for p in images.iterdir()),
            "mapanything_source": str(runtime / "sources/map-anything-v1.1.2"),
            "mapanything_checkpoint": str(runtime / "downloads/map-anything-apache-00f9c245/model.safetensors"),
            "mapanything_config": str(runtime / "downloads/map-anything-apache-00f9c245/config.json"),
            "dinov2_source": str(runtime / "sources/dinov2-7764ea0"),
            "dinov2_checkpoint": str(output / "deliberately-absent-backbone.pth"),
            "colmap_executable": str(runtime / "tools/colmap/3.13.0/bin/colmap.exe"),
            "trigger_minimum_registered_ratio": 0.9, "voxel_fraction": 0.015, "seed": 42,
        },
    }
    request_path = output / "request.json"
    request_path.write_text(json.dumps(request, indent=2), encoding="utf-8")
    environment = os.environ.copy()
    environment["GAUSSIANOS_DISTRIBUTION_ROOT"] = str(stage)
    environment = external_environment(environment)
    environment.update(PYTHONHOME="Z:/absent-python", PYTHONPATH="Z:/absent-source", CONDA_PREFIX="Z:/absent-conda",
                       HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    argv = [str(runtime / "envs/mapanything-1.1.2/python.exe"), "-B", "-X", "utf8", "-m", "workers.recon_mapanything",
            "--request-json", str(request_path), "--result-json", str(output / "result.json")]
    with (output / "stdout.log").open("wb") as stdout, (output / "stderr.log").open("wb") as stderr:
        result = subprocess.run(argv, cwd=stage / "Cache", env=environment, stdout=stdout, stderr=stderr, timeout=1800)
    (output / "execution.json").write_text(json.dumps({"argv": argv, "cwd": str(stage / "Cache"),
                "return_code": result.returncode, "isolation": "standalone _pth; no PATH Python/Conda; offline model loaders"}, indent=2), encoding="utf-8")
    print(f"Packaged fallback return code: {result.returncode}", flush=True)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
