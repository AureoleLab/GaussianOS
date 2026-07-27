from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from apps.desktop.portable import (
    RUNTIME_SCHEMA,
    doctor_report,
    import_offline,
    layout_paths,
    repair,
    tree_sha256,
    validate_manifest,
)


def _sha256(payload: bytes) -> str:
    return hashlib.sha256(payload).hexdigest()


def _manifest(payload: bytes) -> dict:
    return {
        "schema_version": RUNTIME_SCHEMA,
        "gaussianos_version": "0.1.0-alpha",
        "compatible_gaussianos_versions": ["0.1.0-alpha"],
        "platform": {"os": "windows", "architecture": "x86_64"},
        "runtime_root": "Runtime",
        "minimum_vram_mib": 1,
        "components": [
            {
                "component_id": "test-component",
                "version": "1.0.0",
                "platform": "windows",
                "architecture": "x86_64",
                "relative_install_path": "tools/test-component",
                "installed_size_bytes": len(payload),
                "tree_sha256": "",
                "dependencies": [],
                "required": True,
                "source": {
                    "kind": "offline",
                    "url": None,
                    "offline_bundle": "test-offline",
                },
                "compatible_gaussianos_versions": ["0.1.0-alpha"],
                "verification": [
                    {
                        "path": "payload.bin",
                        "type": "file",
                        "size_bytes": len(payload),
                        "sha256": _sha256(payload),
                    }
                ],
            }
        ],
    }


def _write_manifest(root: Path, manifest: dict) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / "runtime-manifest.json").write_text(
        json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
    )


def _offline_package(root: Path, manifest: dict, payload: bytes) -> Path:
    _write_manifest(root, manifest)
    component = root / "Runtime" / "tools" / "test-component"
    component.mkdir(parents=True)
    (component / "payload.bin").write_bytes(payload)
    manifest["components"][0]["tree_sha256"] = tree_sha256(component)
    _write_manifest(root, manifest)
    return root


def test_checked_in_runtime_manifest_has_complete_v3_component_schema() -> None:
    manifest = json.loads(
        (Path(__file__).parents[2] / "dist" / "runtime-manifest.json").read_text(
            encoding="utf-8"
        )
    )
    validate_manifest(manifest)
    assert manifest["schema_version"] == RUNTIME_SCHEMA
    assert all(
        {
            "component_id",
            "version",
            "platform",
            "architecture",
            "relative_install_path",
            "installed_size_bytes",
            "tree_sha256",
            "dependencies",
            "required",
            "source",
            "compatible_gaussianos_versions",
        }
        <= set(component)
        for component in manifest["components"]
    )


@pytest.mark.parametrize(
    "relative",
    ["../escape", "Runtime/Runtime/tools", "C:/absolute/runtime"],
)
def test_manifest_rejects_escaping_and_nested_runtime_paths(relative: str) -> None:
    manifest = _manifest(b"safe")
    manifest["components"][0]["relative_install_path"] = relative
    with pytest.raises(ValueError):
        validate_manifest(manifest)


def test_core_only_doctor_distinguishes_missing_runtime_from_core_damage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "中文 空格" / ("long-" + "x" * 80)
    _write_manifest(root, _manifest(b"runtime"))
    monkeypatch.setenv("GAUSSIANOS_DISTRIBUTION_ROOT", str(root))

    report = doctor_report(full=True)

    assert report.core_status == "ok"
    assert report.runtime_status == "not_installed"
    assert report.exit_code == 2
    assert {issue.code for issue in report.issues} >= {"component_missing"}
    layout = layout_paths()
    assert layout.application == root / "Application"
    assert layout.runtime == root / "Runtime"
    assert layout.projects == root / "Projects"
    assert layout.exports == root / "Exports"


def test_offline_import_is_verified_atomic_and_does_not_touch_projects(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"locked-runtime-payload"
    manifest = _manifest(payload)
    offline = _offline_package(tmp_path / "offline", manifest, payload)
    core = tmp_path / "可移动 Core with spaces"
    _write_manifest(core, manifest)
    project = core / "Projects" / "existing" / "project.json"
    project.parent.mkdir(parents=True)
    project.write_text('{"project_id":"unchanged"}', encoding="utf-8")
    monkeypatch.setenv("GAUSSIANOS_DISTRIBUTION_ROOT", str(core))

    installed = import_offline(offline)

    assert installed == [core / "Runtime" / "tools" / "test-component"]
    assert (installed[0] / "payload.bin").read_bytes() == payload
    assert project.read_text(encoding="utf-8") == '{"project_id":"unchanged"}'
    assert not list((core / "Runtime" / ".staging").glob("test-component-*"))
    assert doctor_report(full=True).runtime_status == "ok"


def test_corruption_is_component_specific_and_offline_repair_restores_it(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"verified-component"
    manifest = _manifest(payload)
    offline = _offline_package(tmp_path / "offline", manifest, payload)
    core = tmp_path / "core"
    _write_manifest(core, manifest)
    monkeypatch.setenv("GAUSSIANOS_DISTRIBUTION_ROOT", str(core))
    [installed] = import_offline(offline)
    (installed / "payload.bin").write_bytes(b"damaged")

    damaged = doctor_report(full=True)
    assert damaged.runtime_status == "integrity_failed"
    assert {
        issue.component_id
        for issue in damaged.issues
        if issue.category == "runtime_integrity"
    } == {"test-component"}

    repaired = repair("test-component", offline)
    assert repaired == installed
    assert (installed / "payload.bin").read_bytes() == payload
    assert doctor_report(full=True).runtime_status == "ok"


def test_offline_import_rejects_runtime_runtime_nesting(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"runtime"
    manifest = _manifest(payload)
    offline = _offline_package(tmp_path / "offline", manifest, payload)
    (offline / "Runtime" / "Runtime").mkdir()
    core = tmp_path / "core"
    _write_manifest(core, manifest)
    monkeypatch.setenv("GAUSSIANOS_DISTRIBUTION_ROOT", str(core))

    with pytest.raises(RuntimeError, match="runtime/runtime"):
        import_offline(offline)
    assert not (core / "Runtime" / "tools" / "test-component").exists()


def test_moved_core_relocates_runtime_without_old_absolute_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    payload = b"relocatable"
    manifest = _manifest(payload)
    offline = _offline_package(tmp_path / "offline", manifest, payload)
    first = tmp_path / "first core"
    _write_manifest(first, manifest)
    monkeypatch.setenv("GAUSSIANOS_DISTRIBUTION_ROOT", str(first))
    import_offline(offline)
    second = tmp_path / "移动 后的 Core"
    shutil.copytree(first, second)
    monkeypatch.setenv("GAUSSIANOS_DISTRIBUTION_ROOT", str(second))

    assert layout_paths().runtime == second / "Runtime"
    assert doctor_report(full=True).runtime_status == "ok"


def test_repair_only_cli_has_shared_progress_callback(tmp_path: Path) -> None:
    payload = b"cli-repair"
    manifest = _manifest(payload)
    offline = _offline_package(tmp_path / "offline", manifest, payload)
    core = tmp_path / "core with spaces"
    _write_manifest(core, manifest)
    installed = core / "Runtime" / "tools" / "test-component"
    installed.mkdir(parents=True)
    (installed / "payload.bin").write_bytes(b"bad")
    environment = os.environ.copy()
    environment["GAUSSIANOS_DISTRIBUTION_ROOT"] = str(core)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "apps.desktop",
            "--runtime-repair",
            "test-component",
            "--runtime-repair-source",
            str(offline),
        ],
        cwd=Path(__file__).parents[2],
        env=environment,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert (installed / "payload.bin").read_bytes() == payload
    assert "Repaired and verified" in (
        core / "Logs" / "runtime-operation-report.txt"
    ).read_text(encoding="utf-8")
