"""Place locked redistributable C++ libraries beside the standalone COLMAP EXE."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]
NOTICE = """Microsoft Visual C++ Runtime 14.44.35211.0 (x64)
Copyright Microsoft Corporation. All rights reserved.
These unmodified release CRT and OpenMP DLLs retain Microsoft's license terms.
They are not licensed under GaussianOS's Apache-2.0 license.
Source: Visual Studio 2022 VC/Redist/MSVC/14.44.35112/x64.
Redistribution terms: https://learn.microsoft.com/en-us/visualstudio/releases/2022/redistribution
"""


def bundle_colmap_crt(redist: Path, component: Path) -> list[dict]:
    lock = json.loads((ROOT / "third_party/locks/microsoft-vc-runtime.json").read_text(encoding="utf-8"))
    if not (component / "bin/colmap.exe").is_file():
        raise RuntimeError("Expected the standalone COLMAP component, not an arbitrary directory")
    verified = []
    for entry in lock["files"]:
        source = redist / entry["source"]
        if source.stat().st_size != entry["size_bytes"] or hashlib.sha256(source.read_bytes()).hexdigest() != entry["sha256"]:
            raise RuntimeError(f"Microsoft redistributable differs from its locked input: {source}")
        target = component / "bin" / entry["filename"]
        if target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() != entry["sha256"]:
            raise RuntimeError(f"Refusing to overwrite an unknown existing COLMAP library: {target}")
        verified.append((source, target, entry))
    for source, target, entry in verified:
        if not target.exists():
            shutil.copy2(source, target)
    (component / "MICROSOFT-VC-RUNTIME-NOTICE.txt").write_text(NOTICE, encoding="utf-8")
    return [{"path": "bin/" + entry["filename"], "type": "file", "size_bytes": entry["size_bytes"],
             "sha256": entry["sha256"]} for _, _, entry in verified]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--redist", type=Path, required=True)
    parser.add_argument("--component", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(bundle_colmap_crt(args.redist, args.component), indent=2))


if __name__ == "__main__":
    main()
