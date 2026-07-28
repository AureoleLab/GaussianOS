from __future__ import annotations

from pathlib import Path

import pytest

from scripts.package_policy import (
    DEBUG_RESOURCE_PAIRS,
    audit_core,
    prune_application,
)


def _minimal_core(root: Path) -> tuple[Path, Path]:
    package = root / "GaussianOS-Portable-Core-win-x64"
    application = package / "Application"
    for relative in (
        "GaussianOS.exe",
        "_internal/apps/desktop/qml/modern/Main.qml",
        "_internal/apps/desktop/qml/classic/Main.qml",
        "_internal/apps/desktop/viewer_web/index.html",
    ):
        path = application / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"required")
    (package / "runtime-manifest.json").write_text("{}", encoding="utf-8")
    return package, application


def test_prune_removes_only_debug_pairs_and_cache_material(tmp_path: Path) -> None:
    _, application = _minimal_core(tmp_path)
    for debug, release in DEBUG_RESOURCE_PAIRS.items():
        debug_path = application / debug
        release_path = application / release
        debug_path.parent.mkdir(parents=True, exist_ok=True)
        debug_path.write_bytes(b"debug")
        release_path.write_bytes(b"release")
    dll = application / "_internal" / "Qt6WebEngineCore.dll"
    dll.write_bytes(b"functional")
    cache = application / "_internal" / "packages" / "__pycache__"
    cache.mkdir(parents=True)
    (cache / "module.pyc").write_bytes(b"cache")

    report = prune_application(application)

    assert report["removed_bytes"] == len(DEBUG_RESOURCE_PAIRS) * len(b"debug") + len(
        b"cache"
    )
    assert dll.read_bytes() == b"functional"
    assert all(not (application / debug).exists() for debug in DEBUG_RESOURCE_PAIRS)
    assert all((application / release).is_file() for release in DEBUG_RESOURCE_PAIRS.values())
    assert not cache.exists()


def test_prune_refuses_debug_resource_without_release_pair(tmp_path: Path) -> None:
    _, application = _minimal_core(tmp_path)
    debug = next(iter(DEBUG_RESOURCE_PAIRS))
    path = application / debug
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"debug")
    with pytest.raises(RuntimeError, match="release pair"):
        prune_application(application)


def test_core_allowlist_denylist_and_runtime_nesting_gate(tmp_path: Path) -> None:
    package, _ = _minimal_core(tmp_path)
    assert audit_core(package)["forbidden"] == []
    model = package / "Cache" / "model.safetensors"
    model.parent.mkdir()
    model.write_bytes(b"model")
    with pytest.raises(RuntimeError, match="model"):
        audit_core(package)
    model.unlink()
    (package / "Runtime" / "Runtime").mkdir(parents=True)
    with pytest.raises(RuntimeError, match="runtime/runtime"):
        audit_core(package)


def test_offline_runtime_launchers_find_and_import_portable_core() -> None:
    offline = Path(__file__).parents[2] / "packaging" / "offline"
    install = (offline / "Install_Runtime.bat").read_text(encoding="utf-8")
    modern = (offline / "Start_GaussianOS.bat").read_text(encoding="utf-8")
    classic = (offline / "Start_GaussianOS_Classic.bat").read_text(
        encoding="utf-8"
    )
    presence = (offline / "Test_RuntimePresence.ps1").read_text(encoding="utf-8")

    assert "Runtime_Manager.ps1" in install
    assert '-Import "%OFFLINE_ROOT%"' in install
    assert "GaussianOS-Portable-Core-win-x64" in install
    assert 'call "%OFFLINE_ROOT%\\Install_Runtime.bat"' in modern
    assert 'call "%CORE_ROOT%\\Start_GaussianOS.bat"' in modern
    assert 'call "%CORE_ROOT%\\Start_GaussianOS_Classic.bat"' in classic
    assert all("%~dp0" in launcher for launcher in (install, modern, classic))
    assert all("Runtime-only package" in launcher for launcher in (install, modern, classic))
    assert all("set /p" not in launcher.lower() for launcher in (install, modern, classic))
    assert "runtime-manifest.json" in presence
    assert "relative_install_path" in presence
    assert "size_bytes" in presence


def test_full_offline_builder_keeps_one_application_and_runtime_root() -> None:
    script = (
        Path(__file__).parents[2] / "scripts" / "build_full_offline.ps1"
    ).read_text(encoding="utf-8")

    assert "GaussianOS-Full-Offline-win-x64" in script
    assert "Application\\GaussianOS.exe" in script
    assert "Runtime\\Runtime" in script
    assert "manifests differ" in script
    assert "doctor_report(full=True)" in script
    assert "single-folder offline launch" in script
