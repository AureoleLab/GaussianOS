"""Portable-runtime doctor and verified asset importer.

The Core archive intentionally contains no model or Worker runtime.  Assets
are materialised below ``runtime/`` next to the executable, never in a user
profile or a developer checkout.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Callable


def portable_root() -> Path:
    return Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parents[2]


def manifest_path() -> Path:
    installed = portable_root() / "runtime-manifest.json"
    # Keep the distributable manifest in dist/ for source-tree development.
    return installed if installed.is_file() or getattr(sys, "frozen", False) else portable_root() / "dist" / "runtime-manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _runtime_assets() -> list[dict[str, Any]]:
    return json.loads(manifest_path().read_text(encoding="utf-8"))["assets"]


def prepare_environment() -> Path:
    """Pin caches and tool discovery to the portable directory."""
    root = portable_root()
    data = root / "data"
    if not getattr(sys, "frozen", False):
        return data
    cache = data / "cache"
    temp = data / "temp"
    for path in (data, cache, temp):
        path.mkdir(parents=True, exist_ok=True)
    os.environ["TORCH_HOME"] = str(cache / "torch")
    os.environ["HF_HOME"] = str(cache / "huggingface")
    os.environ["TEMP"] = str(temp)
    os.environ["TMP"] = str(temp)
    tool_dirs = (
        root / "runtime" / "tools" / "ffmpeg" / "bin",
        root / "runtime" / "tools" / "git" / "cmd",
        root / "runtime" / "tools" / "git" / "bin",
    )
    existing = os.environ.get("PATH", "")
    os.environ["PATH"] = os.pathsep.join([*(str(path) for path in tool_dirs if path.is_dir()), existing])
    return data


def _check_path(root: Path, check: dict[str, Any]) -> str | None:
    target = root / check["path"]
    expected_type = check.get("type", "file")
    exists = target.is_dir() if expected_type == "directory" else target.is_file()
    if not exists:
        return f"Missing runtime: {check['id']} ({check['path']})."
    expected_hash = check.get("sha256")
    if expected_hash and _sha256(target) != expected_hash:
        return f"Runtime integrity check failed: {check['id']} ({check['path']})."
    return None


def doctor() -> list[str]:
    """Return actionable diagnostics; this check is deliberately non-mutating."""
    root, messages = portable_root(), []
    prepare_environment()
    if not manifest_path().is_file():
        return ["Runtime manifest is missing; reinstall the Portable Core archive."]
    manifest = json.loads(manifest_path().read_text(encoding="utf-8"))
    if os.name == "nt" and not shutil.which("nvidia-smi"):
        messages.append("NVIDIA driver was not detected. GPU reconstruction and training require a supported NVIDIA driver.")
    else:
        try:
            query = subprocess.run(
                ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10, check=False,
            )
            if query.returncode == 0:
                memory = max(int(line.strip()) for line in query.stdout.splitlines() if line.strip())
                if memory < int(manifest.get("minimum_vram_mib", 8192)):
                    messages.append(f"GPU VRAM is {memory} MiB; at least {manifest.get('minimum_vram_mib', 8192)} MiB is recommended.")
        except (OSError, ValueError, subprocess.SubprocessError):
            messages.append("NVIDIA driver was found but VRAM could not be queried with nvidia-smi.")
    for check in manifest.get("checks", []):
        problem = _check_path(root, check)
        if problem:
            messages.append(problem)
    return messages


def _safe_extract(archive: Path, destination: Path, strip_components: int = 0) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as source:
        for member in source.infolist():
            parts = Path(member.filename).parts[strip_components:]
            if not parts:
                continue
            target = destination.joinpath(*parts)
            if destination.resolve() not in target.resolve().parents and target.resolve() != destination.resolve():
                raise RuntimeError(f"unsafe archive member: {member.filename}")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.open(member) as input_stream, target.open("wb") as output_stream:
                    shutil.copyfileobj(input_stream, output_stream)


def install(asset_id: str, progress: Callable[[str, int, int], None] | None = None) -> Path:
    """Download one locked asset with HTTP Range resume and SHA-256 validation."""
    asset = next((item for item in _runtime_assets() if item["id"] == asset_id), None)
    if asset is None:
        raise ValueError(f"Unknown runtime asset: {asset_id}")
    url = asset.get("url")
    if not url:
        raise RuntimeError(f"{asset_id} has no approved downloadable artifact. Use the offline runtime import entry.")
    target = portable_root() / asset["target"]
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_suffix(target.suffix + ".part")
    offset = partial.stat().st_size if partial.exists() else 0
    request = urllib.request.Request(url, headers={"Range": f"bytes={offset}-"} if offset else {})
    response = urllib.request.urlopen(request)
    resumed = offset and getattr(response, "status", None) == 206
    if offset and not resumed:
        offset = 0
    with response, partial.open("ab" if resumed else "wb") as output:
        total = int(response.headers.get("Content-Length", "0")) + offset
        done = offset
        while block := response.read(1024 * 1024):
            output.write(block); done += len(block)
            if progress:
                progress(asset_id, done, total)
    if _sha256(partial) != asset["sha256"]:
        partial.unlink(missing_ok=True)
        raise RuntimeError(f"SHA-256 mismatch for {asset_id}; downloaded content was discarded.")
    partial.replace(target)
    if asset.get("archive") == "zip":
        extract_to = portable_root() / asset["extract_to"]
        _safe_extract(target, extract_to, int(asset.get("strip_components", 0)))
    return target


def import_offline(source: str | Path) -> list[Path]:
    """Import a verified Full Offline runtime or individually locked assets."""
    source, installed = Path(source).resolve(), []
    package_source = source if (source / "runtime-manifest.json").is_file() else source.parent
    runtime_source = source / "runtime" if (source / "runtime").is_dir() else source
    source_manifest = package_source / "runtime-manifest.json"
    if source_manifest.is_file() and _sha256(source_manifest) == _sha256(manifest_path()):
        problems = []
        for check in json.loads(source_manifest.read_text(encoding="utf-8")).get("checks", []):
            problem = _check_path(package_source, check)
            if problem:
                problems.append(problem)
        if problems:
            raise RuntimeError("Offline runtime verification failed:\n" + "\n".join(problems))
        destination = portable_root() / "runtime"
        shutil.copytree(runtime_source, destination, dirs_exist_ok=True)
        return [destination]
    for asset in _runtime_assets():
        candidate = source / asset["target"]
        if not candidate.is_file():
            candidate = runtime_source / Path(asset["target"]).relative_to("runtime")
        if candidate.is_file() and _sha256(candidate) == asset["sha256"]:
            target = portable_root() / asset["target"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate, target)
            if asset.get("archive") == "zip":
                _safe_extract(
                    target,
                    portable_root() / asset["extract_to"],
                    int(asset.get("strip_components", 0)),
                )
            installed.append(target)
    return installed
