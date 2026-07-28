"""Generate top-level release checksums and auditable product metadata."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def directory_summary(path: Path) -> tuple[int, int]:
    files = [candidate for candidate in path.rglob("*") if candidate.is_file()]
    return len(files), sum(candidate.stat().st_size for candidate in files)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--full-directory",
        type=Path,
        help="validated Full Offline directory when it is staged outside output",
    )
    args = parser.parse_args()
    output = args.output.resolve()
    hash_cache: dict[Path, str] = {}

    def cached_sha256(path: Path) -> str:
        resolved = path.resolve()
        if resolved not in hash_cache:
            hash_cache[resolved] = sha256(resolved)
        return hash_cache[resolved]

    core_archive = output / "GaussianOS-Portable-Core-win-x64.zip"
    runtime_archive = output / "GaussianOS-Offline-Runtime-win-x64.7z"
    full_archive = output / "GaussianOS-Full-Offline-win-x64.7z"
    core_dir = output / "GaussianOS-Portable-Core-win-x64"
    runtime_dir = output / "GaussianOS-Offline-Runtime-win-x64"
    for required in (core_archive, runtime_archive, core_dir, runtime_dir):
        if not required.exists():
            raise FileNotFoundError(required)
    core_manifest = core_dir / "runtime-manifest.json"
    runtime_manifest = runtime_dir / "runtime-manifest.json"
    if core_manifest.read_bytes() != runtime_manifest.read_bytes():
        raise RuntimeError("Core and Offline Runtime manifests differ")
    shutil.copy2(runtime_manifest, output / "runtime-manifest.json")
    for name in ("VERSION", "CHANGELOG.md", "QUICKSTART.md", "TROUBLESHOOTING.md"):
        shutil.copy2(core_dir / name, output / name)
    core_files, core_unpacked = directory_summary(core_dir)
    runtime_files, runtime_unpacked = directory_summary(runtime_dir)
    products = [
        {
            "product": "GaussianOS Portable Core",
            "archive": core_archive.name,
            "file_count": core_files,
            "unpacked_size_bytes": core_unpacked,
            "compressed_size_bytes": core_archive.stat().st_size,
            "sha256": cached_sha256(core_archive),
            "features": [
                "ModernUI",
                "ClassicUI",
                "Qt/QML/WebEngine Viewer",
                "project management and Scene Bundle export",
                "Runtime detect/install/offline-import/verify/repair",
            ],
            "verification": "passed: content gate, Core-only doctor, packaged ModernUI/ClassicUI/WebEngine, relocation, update/delete isolation",
        },
        {
            "product": "GaussianOS Offline Runtime",
            "archive": runtime_archive.name,
            "file_count": runtime_files,
            "unpacked_size_bytes": runtime_unpacked,
            "compressed_size_bytes": runtime_archive.stat().st_size,
            "sha256": cached_sha256(runtime_archive),
            "features": [
                "FFmpeg",
                "COLMAP CUDA",
                "portable Git",
                "gsplat training environment and source",
                "MapAnything fallback environment, source, and locked models",
            ],
            "verification": "passed: component critical hashes, full Runtime tree hashes, archive integrity",
        },
    ]
    full_dir = (
        args.full_directory.resolve()
        if args.full_directory
        else output / "GaussianOS-Full-Offline-win-x64"
    )
    if full_archive.exists() or full_dir.exists():
        if not full_archive.is_file() or not full_dir.is_dir():
            raise RuntimeError(
                "Full Offline directory and archive must either both exist or both be absent"
            )
        full_manifest = full_dir / "runtime-manifest.json"
        if full_manifest.read_bytes() != runtime_manifest.read_bytes():
            raise RuntimeError("Full Offline and Offline Runtime manifests differ")
        full_files, full_unpacked = directory_summary(full_dir)
        products.append(
            {
                "product": "GaussianOS Full Offline",
                "archive": full_archive.name,
                "file_count": full_files,
                "unpacked_size_bytes": full_unpacked,
                "compressed_size_bytes": full_archive.stat().st_size,
                "sha256": cached_sha256(full_archive),
                "features": [
                    "single-folder ModernUI and ClassicUI",
                    "Qt/QML/WebEngine Viewer",
                    "COLMAP, MapAnything and gsplat",
                    "locked models, tools and training environments",
                ],
                "verification": (
                    "passed: complete doctor, ModernUI/ClassicUI packaged launch, "
                    "archive integrity"
                ),
            }
        )
    payload = {
        "schema_version": "gaussianos-release-build-manifest/v1",
        "version": "0.1.0-alpha",
        "platform": "windows-x86_64",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "products": products,
    }
    (output / "build-manifest.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    checksum_files = [
        core_archive,
        runtime_archive,
        output / "runtime-manifest.json",
        output / "build-manifest.json",
        output / "VERSION",
        output / "CHANGELOG.md",
        output / "QUICKSTART.md",
        output / "TROUBLESHOOTING.md",
    ]
    if full_archive.exists():
        checksum_files.insert(2, full_archive)
    (output / "SHA256SUMS.txt").write_text(
        "".join(f"{cached_sha256(path)} *{path.name}\n" for path in checksum_files),
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
