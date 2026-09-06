"""Assemble a relocatable Runtime without modifying the developer environments.

The CPython distribution and site-packages are separate inputs. Never ship a
venv redirector/pyvenv.cfg as an independent Python. Keep every native library
and model; only regenerate bytecode and replace editable install pointers.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from apps.desktop.portable import _sha256, tree_sha256, tree_size, validate_manifest

RESERVE = 15_000_000_000
SOURCE_EXCLUDES = {".git", "build", "tests", "docs", "__pycache__"}


class Budget:
    def __init__(self, root: Path, report: Path):
        self.root, self.report = root, report
        self.initial_free = shutil.disk_usage(root).free
        self.minimum_free = self.initial_free
        self.copied_bytes = 0
        self.last_sample = 0.0

    def check(self, additional: int = 0, *, force: bool = False) -> None:
        if not force and additional < 64_000_000 and time.monotonic() - self.last_sample < 2:
            return
        free = shutil.disk_usage(self.root).free
        self.minimum_free = min(self.minimum_free, free)
        self.last_sample = time.monotonic()
        data = {"initial_free_bytes": self.initial_free, "minimum_free_bytes": self.minimum_free,
                "observed_growth_bytes": self.initial_free - self.minimum_free,
                "copied_bytes": self.copied_bytes, "reserve_bytes": RESERVE,
                "sample_time": time.time(), "current_free_bytes": free}
        self.report.write_text(json.dumps(data, indent=2), encoding="utf-8")
        if free - additional < RESERVE:
            raise RuntimeError(f"Disk reserve would be violated: free={free}, next={additional}")


def copy_tree(source: Path, destination: Path, budget: Budget, *, source_tree=False) -> None:
    if not source.is_dir():
        raise FileNotFoundError(source)
    for directory, dirs, files in os.walk(source):
        dirs[:] = sorted(d for d in dirs if d not in (SOURCE_EXCLUDES if source_tree else {"__pycache__"}))
        rel = Path(directory).relative_to(source)
        target = destination / rel
        target.mkdir(parents=True, exist_ok=True)
        for name in sorted(files):
            item = Path(directory) / name
            if item.suffix.lower() in {".pyc", ".pyo"}:
                continue
            size = item.stat().st_size
            budget.check(size)
            shutil.copy2(item, target / name)
            budget.copied_bytes += size


def assemble_python(source: Path, destination: Path, budget: Budget) -> dict:
    python = source / "Scripts/python.exe"
    details = json.loads(subprocess.check_output(
        [str(python), "-I", "-c", "import json,sys; print(json.dumps({'base':sys.base_prefix,'version':list(sys.version_info[:3])}))"],
        text=True))
    base = Path(details["base"])
    version = details["version"]
    if not (base / f"python{version[0]}{version[1]}.dll").is_file():
        raise RuntimeError(f"Base is not a complete CPython distribution: {base}")
    # Preserve CPython's complete standard library, DLLs, licenses and Tcl.
    copy_tree(base, destination, budget)
    copy_tree(source / "Lib/site-packages", destination / "Lib/site-packages", budget)
    # Preserve package data stored outside site-packages too.
    for name in ("share", "etc"):
        if (source / name).is_dir():
            copy_tree(source / name, destination / name, budget)
    site = destination / "Lib/site-packages"
    editable = []
    for pointer in site.glob("__editable__*"):
        if pointer.is_file():
            editable.append(pointer.name)
            pointer.unlink()
    if source.name == "mapanything-1.1.2":
        (site / "gaussianos-mapanything.pth").write_text(
            "../../../../sources/map-anything-v1.1.2\n", encoding="utf-8")
    # _pth isolates registry, PYTHONHOME/PYTHONPATH, user site, and current cwd.
    # All worker code is pure Python, outside the frozen GUI's native modules.
    (destination / f"python{version[0]}{version[1]}._pth").write_text(
        ".\nDLLs\nLib\nLib/site-packages\n../../../Application/worker_host\nimport site\n",
        encoding="utf-8")
    return {"python_version": version, "base": str(base), "environment": str(source),
            "removed_editable_pointers": editable,
            "python_sha256": _sha256(destination / "python.exe")}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--developer-runtime", type=Path, required=True)
    parser.add_argument("--verified-offline-runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gsplat-extension", type=Path, required=True,
                        help="Multi-architecture csrc.pyd from build_beta_gsplat.ps1; checked against the manifest")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        raise RuntimeError(f"Refusing to replace existing contents: {output}")
    output.mkdir(parents=True, exist_ok=True)
    (output / ".gaussianos-release-owned.json").write_text(
        json.dumps({"purpose": "Public Beta runtime staging", "created": time.time()}), encoding="utf-8")
    budget = Budget(output, output / "assembly-disk-budget.json")
    budget.check(20_000_000_000, force=True)
    manifest = json.loads((ROOT / "dist/runtime-manifest.json").read_text(encoding="utf-8"))
    runtime = output / "Runtime"
    records = []
    for component in manifest["components"]:
        relative = component["relative_install_path"]
        source = args.developer_runtime / relative
        if not source.is_dir():
            source = args.verified_offline_runtime / relative
        destination = runtime / relative
        record = {"component_id": component["component_id"], "input": str(source)}
        print(f"ASSEMBLE {component['component_id']} <- {source}", flush=True)
        if component["component_id"].endswith("-environment"):
            record["python"] = assemble_python(source, destination, budget)
            if component["component_id"] == "gsplat-environment":
                extension = args.gsplat_extension.resolve()
                budget.check(extension.stat().st_size)
                shutil.copy2(extension, destination / "Lib/site-packages/gsplat/csrc.pyd")
                record["gsplat_extension_input"] = str(extension)
                record["gsplat_extension_sha256"] = _sha256(extension)
        else:
            copy_tree(source, destination, budget, source_tree=relative.startswith("sources/"))
        # Every historical critical file must match, even when the whole
        # developer environment has legitimately changed since the last RC.
        for check in component["verification"]:
            if check.get("type", "file") != "file":
                continue
            path = destination / check["path"]
            actual = _sha256(path)
            if path.stat().st_size != check["size_bytes"] or actual != check["sha256"]:
                raise RuntimeError(f"Locked critical file differs: {component['component_id']}/{check['path']}: {actual}")
        component["installed_size_bytes"] = tree_size(destination)
        component["tree_sha256"] = tree_sha256(destination)
        record.update(bytes=component["installed_size_bytes"], tree_sha256=component["tree_sha256"])
        records.append(record)
        (output / "assembly-provenance.json").write_text(json.dumps(records, indent=2), encoding="utf-8")
        budget.check(force=True)
        print(f"VERIFIED {component['component_id']} {record['bytes']} bytes", flush=True)
    validate_manifest(manifest)
    (output / "runtime-manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(f"ASSEMBLED {sum(c['installed_size_bytes'] for c in manifest['components'])} bytes", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
