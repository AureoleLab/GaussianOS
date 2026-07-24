from __future__ import annotations

import json
from pathlib import Path

import pytest

from apps.desktop.ui_settings import UiSettingsStore, resolve_ui


ROOT = Path(__file__).resolve().parents[2]
DESKTOP = ROOT / "apps" / "desktop"
QML = DESKTOP / "qml"


def test_ui_selection_priority_and_safe_mode() -> None:
    assert resolve_ui("classic", safe_ui=False, persisted="modern").name == "classic"
    assert resolve_ui("modern", safe_ui=False, persisted="classic").name == "modern"
    assert resolve_ui(None, safe_ui=False, persisted="classic").name == "classic"
    assert resolve_ui(None, safe_ui=False, persisted="").name == "modern"
    safe = resolve_ui("modern", safe_ui=True, persisted="modern")
    assert safe.name == "classic"
    assert safe.source == "command line --safe-ui"


def test_ui_settings_are_atomically_persisted_without_project_data(tmp_path: Path) -> None:
    path = tmp_path / "ui-settings.json"
    settings = UiSettingsStore(path)

    assert settings.preferred_ui == ""
    settings.set_preferred_ui("classic")

    assert UiSettingsStore(path).preferred_ui == "classic"
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["schema_version"] == "gaussianos-ui-settings/v1"
    assert payload["preferred_ui"] == "classic"
    assert "project_id" not in payload
    assert not list(tmp_path.glob("*.tmp"))


def test_ui_settings_reject_unknown_shell(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unsupported UI shell"):
        UiSettingsStore(tmp_path / "settings.json").set_preferred_ui("experimental")


def test_classic_and_modern_have_independent_qml_roots_and_one_backend() -> None:
    classic = (QML / "classic" / "Main.qml").read_text(encoding="utf-8")
    modern = (QML / "modern" / "Main.qml").read_text(encoding="utf-8")
    backend = (DESKTOP / "main.py").read_text(encoding="utf-8")

    assert 'DesignTokens { id: theme; mode: window.themeMode }' in classic
    assert 'title: "GaussianOS · ModernUI"' in modern
    assert "backend.projectsJson" in modern
    assert "backend.trashJson" in modern
    assert "backend.loadViewer()" in modern
    assert "backend.cleanupProject" in modern
    assert "Mock action" not in modern
    assert 'Path(__file__).with_name("qml") / name / qml_name' in backend
    assert "ModernUI load failed; falling back to ClassicUI" in backend
    assert backend.count("class Backend(QObject)") == 1


def test_launcher_forwards_ui_arguments() -> None:
    launcher = (ROOT / "start_gaussian_os.bat").read_text(encoding="utf-8")
    assert "gaussian-factory-gui %*" in launcher
