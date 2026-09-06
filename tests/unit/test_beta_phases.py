from __future__ import annotations

import hashlib
import json
from pathlib import Path
import zipfile

from apps.desktop.portable import ensure_runtime_phase, tree_sha256, verify_runtime


def test_base_and_fallback_install_only_needed_capabilities_from_verified_cache(tmp_path: Path, monkeypatch):
    root = tmp_path / "中文 Beta"
    downloads = root / "Cache/RuntimeDownloads"
    downloads.mkdir(parents=True)
    components = []
    for phase in ("base", "fallback"):
        payload = phase.encode()
        source = tmp_path / phase
        source.mkdir()
        (source / "payload").write_bytes(payload)
        archive = downloads / f"{phase}.zip"
        with zipfile.ZipFile(archive, "w") as output:
            output.write(source / "payload", "payload")
        components.append({
            "component_id": phase, "version": "1", "platform": "windows", "architecture": "x86_64",
            "relative_install_path": f"tools/{phase}", "installed_size_bytes": len(payload),
            "tree_sha256": tree_sha256(source), "dependencies": [], "required": phase == "base",
            "install_phase": phase, "compatible_gaussianos_versions": ["0.1.0-beta.1"],
            "verification": [{"path": "payload", "type": "file", "size_bytes": len(payload),
                              "sha256": hashlib.sha256(payload).hexdigest()}],
            "source": {"kind": "download", "url": "https://invalid.example/must-not-connect", "offline_bundle": "test",
                       "artifact": {"archive": "zip", "filename": archive.name, "size_bytes": archive.stat().st_size,
                                    "sha256": hashlib.sha256(archive.read_bytes()).hexdigest()}},
        })
    manifest = {"schema_version": "gaussianos-runtime-manifest/v3", "gaussianos_version": "0.1.0-beta.1",
                "compatible_gaussianos_versions": ["0.1.0-beta.1"], "platform": {"os": "windows", "architecture": "x86_64"},
                "runtime_root": "Runtime", "components": components}
    (root / "runtime-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    monkeypatch.setenv("GAUSSIANOS_DISTRIBUTION_ROOT", str(root))
    installed = ensure_runtime_phase("base")
    assert len(installed) == 1
    assert not (root / "Runtime/tools/fallback").exists()
    assert not verify_runtime(full=True)
    assert not (downloads / "base.zip").exists()
    assert (downloads / "fallback.zip").exists()
    assert not ensure_runtime_phase("base")
    assert len(ensure_runtime_phase("fallback")) == 1
    assert not verify_runtime(full=True)
    assert not list(downloads.iterdir())
