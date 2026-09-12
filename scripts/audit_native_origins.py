"""Reject native dependencies collected from outside the isolated GUI build."""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import sys


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def audit_native_origins(toc: Path, application: Path, allowed_roots: dict[str, Path]) -> dict:
    roots = {name: path.resolve() for name, path in allowed_roots.items()}
    records = []
    issues = []
    seen = set()

    def visit(value):
        if not isinstance(value, (list, tuple)):
            return
        if len(value) == 3 and all(isinstance(v, str) for v in value) and value[2] in {"BINARY", "EXTENSION"}:
            destination, origin, kind = value
            if destination in seen:
                return
            seen.add(destination)
            source = Path(origin).resolve()
            group = next((name for name, root in roots.items() if source.is_relative_to(root)), None)
            packaged = (application / "_internal" / destination).resolve()
            record = {"path": destination, "source": str(source), "kind": kind, "origin_group": group}
            if group is None:
                issues.append(f"Unapproved native origin: {destination} <- {source}")
            if not packaged.is_relative_to(application.resolve()):
                issues.append(f"Native destination escapes application: {destination}")
            elif not packaged.is_file():
                issues.append(f"Missing collected native file: {destination}")
            elif not source.is_file():
                issues.append(f"Missing native source: {source}")
            else:
                record["source_sha256"] = sha256(source)
                record["packaged_sha256"] = sha256(packaged)
                if record["source_sha256"] != record["packaged_sha256"]:
                    issues.append(f"Collected native bytes differ from approved source: {destination}")
            records.append(record)
            return
        for item in value:
            visit(item)

    visit(ast.literal_eval(toc.read_text(encoding="utf-8")))
    if not records:
        issues.append("No native dependency records found in PyInstaller analysis")
    return {"schema_version": "gaussianos-native-origins/v1", "status": "failed" if issues else "succeeded",
            "allowed_roots": {name: str(path) for name, path in roots.items()}, "issues": issues, "files": records}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--toc", type=Path, required=True)
    parser.add_argument("--application", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    report = audit_native_origins(args.toc, args.application, {
        "locked_gui_environment": Path(sys.prefix),
        "managed_cpython": Path(sys.base_prefix),
        "windows_system": Path(os.environ["SystemRoot"]) / "System32",
    })
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Native provenance: {report['status']}, {len(report['files'])} dependencies")
    for issue in report["issues"]:
        print(issue)
    return 0 if report["status"] == "succeeded" else 3


if __name__ == "__main__":
    raise SystemExit(main())
