"""Auditable distribution pruning, content gates, and build manifests."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


DEBUG_RESOURCE_PAIRS = {
    "_internal/PySide6/resources/qtwebengine_devtools_resources.debug.pak":
        "_internal/PySide6/resources/qtwebengine_devtools_resources.pak",
    "_internal/PySide6/resources/qtwebengine_resources.debug.pak":
        "_internal/PySide6/resources/qtwebengine_resources.pak",
    "_internal/PySide6/resources/qtwebengine_resources_100p.debug.pak":
        "_internal/PySide6/resources/qtwebengine_resources_100p.pak",
    "_internal/PySide6/resources/qtwebengine_resources_200p.debug.pak":
        "_internal/PySide6/resources/qtwebengine_resources_200p.pak",
    "_internal/PySide6/resources/v8_context_snapshot.debug.bin":
        "_internal/PySide6/resources/v8_context_snapshot.bin",
}
FORBIDDEN_CORE_SUFFIXES = {
    ".ckpt",
    ".mov",
    ".mp4",
    ".avi",
    ".ply",
    ".pt",
    ".pth",
    ".safetensors",
}
REQUIRED_APPLICATION_PATHS = (
    "GaussianOS.exe",
    "_internal/apps/desktop/qml/modern/Main.qml",
    "_internal/apps/desktop/qml/classic/Main.qml",
    "_internal/apps/desktop/viewer_web/index.html",
)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _files(root: Path) -> list[Path]:
    return sorted(
        (path for path in root.rglob("*") if path.is_file()),
        key=lambda path: path.relative_to(root).as_posix().casefold(),
    )


def prune_application(application: Path) -> dict[str, Any]:
    """Remove only proven release-unreachable cache/debug material."""

    removed: list[dict[str, Any]] = []
    for debug_relative, release_relative in DEBUG_RESOURCE_PAIRS.items():
        debug = application / debug_relative
        release = application / release_relative
        if debug.is_file():
            if not release.is_file():
                raise RuntimeError(
                    f"refusing to remove {debug_relative}; release pair is missing"
                )
            size = debug.stat().st_size
            debug.unlink()
            removed.append(
                {
                    "path": debug_relative,
                    "bytes": size,
                    "reason": "Qt WebEngine debug-build resource; release pair retained",
                }
            )
    for path in list(application.rglob("*")):
        if path.is_file() and path.suffix.casefold() == ".pdb":
            relative = path.relative_to(application).as_posix()
            size = path.stat().st_size
            path.unlink()
            removed.append(
                {
                    "path": relative,
                    "bytes": size,
                    "reason": "debug symbol; executable/library retained",
                }
            )
        elif path.is_file() and path.suffix.casefold() in {".pyc", ".pyo"}:
            relative = path.relative_to(application).as_posix()
            size = path.stat().st_size
            path.unlink()
            removed.append(
                {
                    "path": relative,
                    "bytes": size,
                    "reason": "source-data bytecode cache; frozen PYZ retained",
                }
            )
    for cache in sorted(
        (path for path in application.rglob("__pycache__") if path.is_dir()),
        key=lambda path: len(path.parts),
        reverse=True,
    ):
        if cache.exists():
            shutil.rmtree(cache)
    return {
        "schema_version": "gaussianos-prune-report/v1",
        "removed": removed,
        "removed_bytes": sum(item["bytes"] for item in removed),
    }


def audit_core(package: Path) -> dict[str, Any]:
    application = package / "Application"
    missing = [
        relative
        for relative in REQUIRED_APPLICATION_PATHS
        if not (application / relative).is_file()
    ]
    if not (package / "runtime-manifest.json").is_file():
        missing.append("runtime-manifest.json")
    if missing:
        raise RuntimeError(f"Core package is missing required files: {missing}")
    forbidden = [
        path.relative_to(package).as_posix()
        for path in _files(package)
        if path.suffix.casefold() in FORBIDDEN_CORE_SUFFIXES
        or ".scene-bundle" in {
            part.casefold() for part in path.relative_to(package).parts
        }
    ]
    if forbidden:
        raise RuntimeError(
            "Core contains model, media, project, or export payloads: "
            + ", ".join(forbidden[:20])
        )
    nested = [
        path.relative_to(package).as_posix()
        for path in package.rglob("*")
        if path.is_dir()
        and len(path.relative_to(package).parts) >= 2
        and path.relative_to(package).parts[-2].casefold() == "runtime"
        and path.name.casefold() == "runtime"
    ]
    if nested:
        raise RuntimeError(f"forbidden runtime/runtime nesting: {nested}")
    files = _files(package)
    duplicate_candidates: dict[tuple[int, str], list[str]] = {}
    for path in files:
        size = path.stat().st_size
        if size < 1024 * 1024:
            continue
        key = (size, _sha256(path))
        duplicate_candidates.setdefault(key, []).append(
            path.relative_to(package).as_posix()
        )
    duplicates = [
        {"bytes_each": size, "sha256": digest, "paths": paths}
        for (size, digest), paths in duplicate_candidates.items()
        if len(paths) > 1
    ]
    return {
        "schema_version": "gaussianos-package-audit/v1",
        "package": str(package),
        "files": len(files),
        "bytes": sum(path.stat().st_size for path in files),
        "forbidden": forbidden,
        "duplicate_groups_retained": duplicates,
    }


def build_manifest(
    package: Path,
    *,
    product: str,
    features: list[str],
    prune_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    files = [
        {
            "path": path.relative_to(package).as_posix(),
            "size_bytes": path.stat().st_size,
            "sha256": _sha256(path),
        }
        for path in _files(package)
        if path.name != "build-manifest.json"
    ]
    return {
        "schema_version": "gaussianos-build-manifest/v1",
        "product": product,
        "version": "0.1.0-alpha",
        "platform": "windows-x86_64",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "features": features,
        "file_count": len(files),
        "unpacked_size_bytes": sum(item["size_bytes"] for item in files),
        "files": files,
        "pruning": prune_report
        or {
            "schema_version": "gaussianos-prune-report/v1",
            "removed": [],
            "removed_bytes": 0,
        },
    }


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    subcommands = parser.add_subparsers(dest="command", required=True)
    prune = subcommands.add_parser("prune")
    prune.add_argument("--application", type=Path, required=True)
    prune.add_argument("--report", type=Path, required=True)
    audit = subcommands.add_parser("audit-core")
    audit.add_argument("--package", type=Path, required=True)
    audit.add_argument("--report", type=Path, required=True)
    manifest = subcommands.add_parser("build-manifest")
    manifest.add_argument("--package", type=Path, required=True)
    manifest.add_argument("--product", required=True)
    manifest.add_argument("--feature", action="append", default=[])
    manifest.add_argument("--prune-report", type=Path)
    args = parser.parse_args()
    if args.command == "prune":
        _write_json(args.report, prune_application(args.application.resolve()))
    elif args.command == "audit-core":
        _write_json(args.report, audit_core(args.package.resolve()))
    else:
        prune_report = (
            json.loads(args.prune_report.read_text(encoding="utf-8"))
            if args.prune_report
            else None
        )
        payload = build_manifest(
            args.package.resolve(),
            product=args.product,
            features=args.feature,
            prune_report=prune_report,
        )
        _write_json(args.package / "build-manifest.json", payload)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
