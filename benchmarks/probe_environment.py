"""Collect reproducible P1 environment and input evidence without running models.

The probe deliberately treats reconstructors, trainers, and viewers as optional.
Missing executables are evidence, not a probe failure.  Third-party Python
runtime checks run in child processes so an import failure cannot terminate the
probe itself.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROBE_SCHEMA_VERSION = "p1-environment-probe/v1"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run(command: list[str], *, timeout_seconds: float = 20.0) -> dict[str, Any]:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "status": "timeout",
            "exit_code": None,
            "stdout": (exc.stdout or "")[-20_000:],
            "stderr": (exc.stderr or "")[-20_000:],
        }
    except OSError as exc:
        return {"status": "spawn_error", "exit_code": None, "error": str(exc)}
    return {
        "status": "ok" if result.returncode == 0 else "nonzero_exit",
        "exit_code": result.returncode,
        "stdout": result.stdout[-20_000:],
        "stderr": result.stderr[-20_000:],
    }


def _command_probe(
    executable: str,
    arguments: list[str],
    *,
    explicit_path: Path | None = None,
) -> dict[str, Any]:
    resolved = str(explicit_path.resolve()) if explicit_path is not None else shutil.which(executable)
    if resolved is None:
        return {"available": False, "executable": None, "probe": None}
    path = Path(resolved).resolve()
    if not path.is_file():
        return {
            "available": False,
            "executable": str(path),
            "probe": None,
            "error": "explicit executable is not a file",
        }
    return {
        "available": True,
        "executable": str(path),
        "executable_sha256": _sha256_file(path),
        "probe": _run([str(path), *arguments]),
    }


def _package_versions() -> dict[str, str | None]:
    distributions = {
        "numpy": "numpy",
        "pillow": "Pillow",
        "pydantic": "pydantic",
        "safetensors": "safetensors",
        "torch": "torch",
        "gsplat": "gsplat",
        "pycolmap": "pycolmap",
    }
    versions: dict[str, str | None] = {}
    for label, distribution in distributions.items():
        try:
            versions[label] = importlib.metadata.version(distribution)
        except importlib.metadata.PackageNotFoundError:
            versions[label] = None
    return versions


def _torch_runtime_probe() -> dict[str, Any]:
    script = r"""
import json
try:
    import torch
    available = bool(torch.cuda.is_available())
    payload = {
        "imported": True,
        "torch_version": torch.__version__,
        "torch_cuda_version": torch.version.cuda,
        "cuda_available": available,
        "compiled_arches": torch.cuda.get_arch_list() if available else [],
        "device_name": torch.cuda.get_device_name(0) if available else None,
        "device_capability": list(torch.cuda.get_device_capability(0)) if available else None,
    }
except Exception as exc:
    payload = {"imported": False, "error_type": type(exc).__name__, "error": str(exc)}
print(json.dumps(payload, sort_keys=True))
"""
    result = _run([sys.executable, "-c", script], timeout_seconds=30.0)
    payload: dict[str, Any] = {"subprocess": result}
    if result.get("status") == "ok":
        try:
            runtime = json.loads(result["stdout"].strip().splitlines()[-1])
        except (IndexError, json.JSONDecodeError) as exc:
            payload["parse_error"] = str(exc)
        else:
            payload["runtime"] = runtime
            capability = runtime.get("device_capability")
            arches = runtime.get("compiled_arches") or []
            if capability:
                expected = f"sm_{capability[0]}{capability[1]}"
                payload["expected_compiled_arch"] = expected
                payload["compiled_arch_compatible"] = expected in arches
    return payload


def _ffprobe_video(ffprobe: str, path: Path) -> dict[str, Any]:
    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration,format_name,size,bit_rate:stream=index,codec_type,codec_name,width,height,pix_fmt,avg_frame_rate,nb_frames,sample_rate,channels",
        "-of",
        "json",
        str(path),
    ]
    result = _run(command, timeout_seconds=30.0)
    if result.get("status") != "ok":
        return {"status": "ffprobe_failed", "probe": result}
    try:
        metadata = json.loads(result["stdout"])
    except json.JSONDecodeError as exc:
        return {"status": "invalid_ffprobe_json", "error": str(exc), "probe": result}
    return {"status": "ok", "metadata": metadata}


def _input_inventory(input_dir: Path, ffprobe: str | None) -> dict[str, Any]:
    if not input_dir.is_dir():
        return {"status": "missing_input_directory", "path": str(input_dir), "files": []}
    files: list[dict[str, Any]] = []
    for path in sorted(item for item in input_dir.iterdir() if item.is_file()):
        item: dict[str, Any] = {
            "name": path.name,
            "size_bytes": path.stat().st_size,
            "sha256": _sha256_file(path),
        }
        if ffprobe is not None and path.suffix.lower() in {".mp4", ".mov", ".mkv", ".avi", ".webm"}:
            item["media"] = _ffprobe_video(ffprobe, path)
        files.append(item)
    identity = "".join(f"{item['name']}\0{item['sha256']}\n" for item in files).encode("utf-8")
    return {
        "status": "ok" if files else "empty_input_directory",
        "path": str(input_dir.resolve()),
        "files": files,
        "inventory_sha256": hashlib.sha256(identity).hexdigest(),
    }


def _prepared_dataset(manifest_path: Path | None) -> dict[str, Any] | None:
    if manifest_path is None:
        return None
    if not manifest_path.is_file():
        return {"status": "missing", "path": str(manifest_path)}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {"status": "invalid", "path": str(manifest_path), "error": str(exc)}
    scenes = []
    for scene in payload.get("scenes", []):
        frames = scene.get("frames", [])
        scenes.append(
            {
                "scene_id": scene.get("scene_id"),
                "frame_count": len(frames),
                "train_count": sum(frame.get("split") == "train" for frame in frames),
                "holdout_count": sum(frame.get("split") == "holdout" for frame in frames),
            }
        )
    return {
        "status": "ok",
        "path": str(manifest_path.resolve()),
        "manifest_sha256": _sha256_file(manifest_path),
        "dataset_id": payload.get("dataset_id"),
        "protocol_version": payload.get("protocol_version"),
        "sampling": payload.get("sampling"),
        "scenes": scenes,
    }


def collect(
    input_dir: Path,
    dataset_manifest: Path | None,
    *,
    colmap_path: Path | None = None,
) -> dict[str, Any]:
    command_specs = {
        "ffmpeg": ["-version"],
        "ffprobe": ["-version"],
        "nvidia_smi": [
            "--query-gpu=name,driver_version,memory.total,compute_cap",
            "--format=csv,noheader,nounits",
        ],
        "nvcc": ["--version"],
        "colmap": ["-h"],
        "splat_transform": ["--version"],
        "brush": ["--version"],
        "node": ["--version"],
        "npm": ["--version"],
        "rustc": ["--version"],
        "cargo": ["--version"],
        "git": ["--version"],
    }
    executable_names = {
        "nvidia_smi": "nvidia-smi",
        "splat_transform": "splat-transform",
        **{name: name for name in command_specs if name not in {"nvidia_smi", "splat_transform"}},
    }
    commands = {}
    for label, arguments in command_specs.items():
        explicit_path = colmap_path if label == "colmap" else None
        commands[label] = _command_probe(
            executable_names[label], arguments, explicit_path=explicit_path
        )
    ffprobe_path = commands["ffprobe"].get("executable") if commands["ffprobe"]["available"] else None
    return {
        "schema_version": PROBE_SCHEMA_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "host": {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "python_executable": sys.executable,
            "machine": platform.machine(),
            "processor": platform.processor(),
            "logical_cpu_count": os.cpu_count(),
        },
        "commands": commands,
        "python_packages": _package_versions(),
        "torch_runtime": _torch_runtime_probe(),
        "input": _input_inventory(input_dir, ffprobe_path),
        "prepared_dataset": _prepared_dataset(dataset_manifest),
        "probe_actions": {
            "reconstruction_executed_by_this_probe": False,
            "gaussian_training_executed_by_this_probe": False,
            "third_party_ply_consumers_executed_by_this_probe": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=Path("testvid"))
    parser.add_argument("--dataset-manifest", type=Path)
    parser.add_argument(
        "--colmap",
        type=Path,
        help="explicit COLMAP executable when the project-local binary is not on PATH",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    payload = collect(args.input_dir, args.dataset_manifest, colmap_path=args.colmap)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
