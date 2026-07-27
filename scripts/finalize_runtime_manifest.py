"""Finalize component sizes and hashes from an assembled Offline Runtime."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from apps.desktop.portable import (
    _sha256,
    tree_sha256,
    tree_size,
    validate_manifest,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", type=Path, required=True)
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--component", action="append", default=[])
    args = parser.parse_args()
    manifest = json.loads(args.template.read_text(encoding="utf-8-sig"))
    selected = set(args.component)
    known = {component["component_id"] for component in manifest["components"]}
    unknown = sorted(selected - known)
    if unknown:
        raise ValueError(f"unknown components requested for finalization: {unknown}")
    for component in manifest["components"]:
        if selected and component["component_id"] not in selected:
            continue
        root = args.runtime / Path(component["relative_install_path"])
        if not root.is_dir():
            raise FileNotFoundError(
                f"component root is missing: {component['component_id']} -> {root}"
            )
        component["installed_size_bytes"] = tree_size(root)
        component["tree_sha256"] = tree_sha256(root)
        for check in component["verification"]:
            target = root / Path(check["path"])
            if check.get("type", "file") == "file":
                if not target.is_file():
                    raise FileNotFoundError(
                        f"verification file is missing: {component['component_id']} "
                        f"-> {target}"
                    )
                check["size_bytes"] = target.stat().st_size
                check["sha256"] = _sha256(target)
    validate_manifest(manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
