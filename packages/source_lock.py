"""Verify an exact source checkout with or without bundled Git metadata."""

from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def source_tree_sha256(root: str | Path) -> str:
    base = Path(root).resolve()
    digest = hashlib.sha256()
    files = sorted(
        (path for path in base.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(base).as_posix().casefold(),
    )
    for path in files:
        relative = path.relative_to(base).as_posix()
        size = path.stat().st_size
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(str(size).encode("ascii"))
        digest.update(b"\0")
        digest.update(_sha256(path).encode("ascii"))
        digest.update(b"\n")
    return digest.hexdigest()


def verify_source_lock(
    root: str | Path,
    *,
    expected_commit: str,
    expected_tree_sha256: str,
    label: str,
) -> str:
    """Verify a developer checkout by Git or a pruned portable tree by hash."""

    source = Path(root).resolve()
    if not source.is_dir():
        raise FileNotFoundError(f"{label} source directory is missing: {source}")
    if (source / ".git").exists():
        completed = subprocess.run(
            ["git", "-C", str(source), "rev-parse", "HEAD"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        commit = completed.stdout.strip()
        if completed.returncode != 0:
            raise RuntimeError(
                f"{label} source commit check failed ({completed.returncode}): "
                f"{completed.stderr[-1000:]}"
            )
        if commit != expected_commit:
            raise RuntimeError(f"{label} source commit mismatch: {commit}")
        return "git"
    actual_tree = source_tree_sha256(source)
    if actual_tree != expected_tree_sha256:
        raise RuntimeError(f"{label} portable source tree hash mismatch: {actual_tree}")
    return "tree_sha256"
