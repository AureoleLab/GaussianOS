"""Create deterministic, independently hashed Runtime ZIP segments in one pass.

No aggregate ZIP or Runtime copy is made. The output manifest is published only
after every input tree and archive segment has been verified. Existing complete
components can be reused after interruption; incomplete segments are not reused.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from apps.desktop.portable import _sha256, tree_sha256, tree_size, validate_manifest
from apps.desktop.runtime_downloads import SegmentedReader

RESERVE = 15_000_000_000
FALLBACK = {"mapanything-source", "mapanything-environment", "mapanything-model", "dinov2-source"}
REMOVED = {"portable-git", "dinov2-model"}


class SplitWriter(io.RawIOBase):
    def __init__(self, directory: Path, stem: str, limit: int):
        super().__init__()
        self.directory, self.stem, self.limit = directory, stem, limit
        self.position = 0
        self.current = None
        self.current_size = 0
        self.paths = []
        self.digest = hashlib.sha256()

    def writable(self):
        return True

    def tell(self):
        return self.position

    def write(self, data):
        view = memoryview(data)
        count = len(view)
        while view:
            if self.current is None or self.current_size == self.limit:
                if self.current:
                    self.current.close()
                if shutil.disk_usage(self.directory).free < RESERVE + self.limit:
                    raise OSError("Release disk reserve would be violated")
                path = self.directory / f"{self.stem}.zip.part{len(self.paths) + 1:03d}"
                self.current = path.open("xb")
                self.paths.append(path)
                self.current_size = 0
            block = view[:self.limit - self.current_size]
            self.current.write(block)
            self.digest.update(block)
            self.current_size += len(block)
            self.position += len(block)
            view = view[len(block):]
        return count

    def close(self):
        if self.current:
            self.current.close()
        super().close()


def package_component(root: Path, component: dict, output: Path, base_url: str, limit: int) -> dict:
    cid = component["component_id"]
    if tree_size(root) != component["installed_size_bytes"] or tree_sha256(root) != component["tree_sha256"]:
        raise RuntimeError(f"Staged Runtime changed: {cid}")
    stem = f"runtime-{cid}-{component['tree_sha256'][:16]}"
    record_path = output / f"{stem}.artifact.json"
    if record_path.is_file():
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if all((output / p["filename"]).stat().st_size == p["size_bytes"]
               and _sha256(output / p["filename"]) == p["sha256"] for p in record["parts"]):
            return record
        raise RuntimeError(f"Existing release payload is damaged: {record_path}")
    # Deliberately fail on existing incomplete parts; never silently replace a
    # payload that may already have been published.
    with SplitWriter(output, stem, limit) as stream:
        with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6, allowZip64=True) as archive:
            for file in sorted(root.rglob("*")):
                if not file.is_file():
                    continue
                info = zipfile.ZipInfo(file.relative_to(root).as_posix(), date_time=(2000, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o100644 << 16
                info.file_size = file.stat().st_size
                with file.open("rb") as source, archive.open(info, "w", force_zip64=True) as target:
                    shutil.copyfileobj(source, target, length=4 * 1024 * 1024)
        record = {"filename": stem + ".zip", "archive": "zip", "strip_components": 0,
                  "size_bytes": stream.position, "sha256": stream.digest.hexdigest(), "parts": []}
    for path in stream.paths:
        record["parts"].append({"filename": path.name, "url": base_url.rstrip("/") + "/" + path.name,
                                "size_bytes": path.stat().st_size, "sha256": _sha256(path)})
    # Reading every decompressed entry also verifies CRC, central directory and
    # cross-segment seeks without allocating another installed component.
    with SegmentedReader(stream.paths) as reader, zipfile.ZipFile(reader) as archive:
        bad = archive.testzip()
        if bad:
            raise RuntimeError(f"Archive CRC failed: {bad}")
    record_path.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--part-bytes", type=int, default=1_000_000_000)
    args = parser.parse_args()
    if not 1_000_000 <= args.part_bytes <= 1_900_000_000:
        raise ValueError("Segment size must stay below release hosting limits")
    args.output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((args.stage / "runtime-manifest.json").read_text(encoding="utf-8-sig"))
    manifest.update(gaussianos_version="0.1.0-beta.1", compatible_gaussianos_versions=["0.1.0-beta.1"],
                    minimum_driver_major=580, minimum_compute_capability=7.5)
    manifest["components"] = [c for c in manifest["components"] if c["component_id"] not in REMOVED]
    for c in manifest["components"]:
        cid = c["component_id"]
        c["required"] = cid not in FALLBACK
        c["install_phase"] = "fallback" if cid in FALLBACK else "base"
        c["dependencies"] = [d for d in c["dependencies"] if d not in REMOVED]
        c["compatible_gaussianos_versions"] = ["0.1.0-beta.1"]
        print(f"PACK {cid} ({c['installed_size_bytes']} bytes)", flush=True)
        artifact = package_component(args.stage / "Runtime" / c["relative_install_path"], c,
                                     args.output, args.base_url, args.part_bytes)
        c["source"] = {"kind": "download", "url": artifact["parts"][0]["url"],
                       "offline_bundle": "GaussianOS-Public-Beta-Runtime", "artifact": artifact}
        print(f"VERIFIED {cid}: {artifact['size_bytes']} compressed bytes", flush=True)
    validate_manifest(manifest)
    (args.output / "runtime-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    summary = {phase: {"installed_bytes": sum(c["installed_size_bytes"] for c in manifest["components"] if c["install_phase"] == phase),
                       "download_bytes": sum(c["source"]["artifact"]["size_bytes"] for c in manifest["components"] if c["install_phase"] == phase)}
               for phase in ("base", "fallback")}
    (args.output / "runtime-size-report.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary), flush=True)


if __name__ == "__main__":
    main()
