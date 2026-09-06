"""Archive only the audited Core package, with flat installer-relative paths."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import zipfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--package", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / "GaussianOS-Core-win-x64.zip"
    temporary = target.with_suffix(".zip.tmp")
    if target.exists() or temporary.exists():
        raise RuntimeError("Refusing to replace an existing Core artifact")
    manifest = json.loads((args.package / "build-manifest.json").read_text(encoding="utf-8"))
    expected = {entry["path"]: entry for entry in manifest["files"]}
    total = 0
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(args.package.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(args.package).as_posix()
            if relative != "build-manifest.json" and relative not in expected:
                raise RuntimeError(f"Unaudited file in Core: {relative}")
            digest = hashlib.sha256()
            info = zipfile.ZipInfo(relative, (2000, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            with path.open("rb") as source, archive.open(info, "w", force_zip64=True) as out:
                while block := source.read(4 * 1024 * 1024):
                    digest.update(block)
                    out.write(block)
                    total += len(block)
            if relative in expected and digest.hexdigest() != expected[relative]["sha256"]:
                raise RuntimeError(f"Core changed after build manifest: {relative}")
    with zipfile.ZipFile(temporary) as archive:
        if archive.testzip():
            raise RuntimeError("Core archive CRC failed")
        if set(archive.namelist()) != set(expected) | {"build-manifest.json"}:
            raise RuntimeError("Core archive inventory differs from build manifest")
    os.replace(temporary, target)
    digest = hashlib.sha256()
    with target.open("rb") as source:
        for block in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(block)
    record = {"filename": target.name, "sha256": digest.hexdigest(), "size_bytes": target.stat().st_size,
              "installed_bytes": total, "file_count": len(expected) + 1,
              "runtime_manifest_sha256": hashlib.sha256((args.package / "runtime-manifest.json").read_bytes()).hexdigest()}
    (args.output / "core-artifact.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(record), flush=True)


if __name__ == "__main__":
    main()
