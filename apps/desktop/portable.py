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
import sys
import urllib.request
from pathlib import Path
from typing import Any


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


def doctor() -> list[str]:
    """Return actionable diagnostics; this check is deliberately non-mutating."""
    root, messages = portable_root(), []
    if not manifest_path().is_file():
        return ["Runtime manifest is missing; reinstall the Portable Core archive."]
    if os.name == "nt" and not shutil.which("nvidia-smi"):
        messages.append("NVIDIA driver was not detected. GPU reconstruction and training require a supported NVIDIA driver.")
    for asset in _runtime_assets():
        target = root / asset["target"]
        if not target.is_file():
            messages.append(f"Missing runtime: {asset['id']}. Use Runtime Import or download it from the manifest.")
        elif _sha256(target) != asset["sha256"]:
            messages.append(f"Runtime integrity check failed: {asset['id']}. Delete it and import/download again.")
    return messages


def install(asset_id: str, progress: callable | None = None) -> Path:
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
    with urllib.request.urlopen(request) as response, partial.open("ab" if offset else "wb") as output:
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
    return target


def import_offline(source: str | Path) -> list[Path]:
    """Import a directory matching manifest targets, verifying every copied file."""
    source, installed = Path(source), []
    for asset in _runtime_assets():
        candidate = source / asset["target"]
        if candidate.is_file() and _sha256(candidate) == asset["sha256"]:
            target = portable_root() / asset["target"]
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(candidate, target); installed.append(target)
    return installed
