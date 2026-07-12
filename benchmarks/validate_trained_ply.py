"""Load every formal gsplat PLY in the P1 consumer set."""

from __future__ import annotations

import gc
import hashlib
import json
import subprocess
from pathlib import Path

import gsply

from packages.exportkit import read_gaussian_ply


ROOT = Path(__file__).resolve().parents[1]
SUMMARY = ROOT / "benchmark_runs" / "gsplat-1.5.3" / "run-summary.json"
BRUSH = ROOT / ".gaussian-factory" / "tools" / "brush" / "v0.3.0" / "brush_app.exe"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(command: list[str], timeout: int) -> dict[str, object]:
    completed = subprocess.run(command, capture_output=True, text=True, errors="replace", timeout=timeout)
    combined = completed.stdout + "\n" + completed.stderr
    return {"return_code": completed.returncode, "output_tail": combined[-4000:]}


def main() -> int:
    summary = json.loads(SUMMARY.read_text(encoding="utf-8"))
    evidence: dict[str, object] = {
        "schema_version": "trained-ply-consumers/v1",
        "consumer_locks": {
            "exportkit": "gaussian-factory P1",
            "gsply": "0.4.6",
            "splat_transform": "3.0.0 / daf6338",
            "brush": "0.3.0 / 3edecbb2fe79d3e2c87eeab85b15e0b1dd10d486",
        },
        "scenes": {},
    }
    passed = True
    for scene_id, item in summary["scenes"].items():
        artifact = Path(item["artifacts"][0])
        ply = next(artifact.glob("*.graphdeco-gs-v1.ply"))
        exportkit = read_gaussian_ply(ply)
        expected = int(item["metrics"]["gaussian_count"])
        exportkit_count = int(exportkit.means.shape[0])
        del exportkit
        gc.collect()
        independent = gsply.plyread(ply)
        gsply_count = int(independent.means.shape[0])
        gsply_degree = int(independent.get_sh_degree())
        del independent
        gc.collect()
        splat = _run([
            "npx.cmd", "--yes", "--package=@playcanvas/splat-transform@3.0.0",
            "splat-transform", str(ply), "--info", "json", "null",
        ], 600)
        brush = _run([str(BRUSH), str(ply), "--total-steps", "0"], 600)
        scene_passed = (
            exportkit_count == expected
            and gsply_count == expected
            and gsply_degree == 3
            and splat["return_code"] == 0
            and brush["return_code"] == 0
        )
        passed = passed and scene_passed
        evidence["scenes"][scene_id] = {
            "path": str(ply), "sha256": _sha256(ply), "bytes": ply.stat().st_size,
            "expected_gaussians": expected, "exportkit_count": exportkit_count,
            "gsply_count": gsply_count, "gsply_sh_degree": gsply_degree,
            "splat_transform": splat, "brush": brush, "passed": scene_passed,
        }
        print(f"{scene_id}: {'PASS' if scene_passed else 'FAIL'} ({expected} Gaussians)", flush=True)
    evidence["passed"] = passed
    destination = ROOT / "benchmarks" / "evidence" / "trained_ply_consumers.json"
    destination.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return 0 if passed else 10


if __name__ == "__main__":
    raise SystemExit(main())
