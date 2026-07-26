from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import sys

import pytest


def test_qsettings_initializes_and_persists_with_application_identity(
    tmp_path: Path,
) -> None:
    if importlib.util.find_spec("PySide6") is None:
        pytest.skip("PySide6 desktop extra is not installed")
    script = f"""
from pathlib import Path
from PySide6.QtCore import QSettings
from PySide6.QtGui import QGuiApplication
from apps.desktop.main import _configure_application_identity

target = Path({str(tmp_path)!r})
QSettings.setDefaultFormat(QSettings.IniFormat)
QSettings.setPath(QSettings.IniFormat, QSettings.UserScope, str(target))
_configure_application_identity(QGuiApplication)
app = QGuiApplication([])
assert app.organizationName() == "AureoleLab"
assert app.organizationDomain() == "gaussianos.com"
assert app.applicationName() == "GaussianOS"
first = QSettings()
assert first.status() == QSettings.NoError
first.setValue("modern-ui-v1/themeMode", "dark")
first.sync()
assert first.status() == QSettings.NoError
second = QSettings()
assert second.value("modern-ui-v1/themeMode") == "dark"
print("qsettings-persisted")
"""
    environment = os.environ.copy()
    environment["QT_QPA_PLATFORM"] = "offscreen"
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path(__file__).resolve().parents[2],
        env=environment,
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "qsettings-persisted" in result.stdout
