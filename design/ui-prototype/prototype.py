"""Standalone GaussianOS visual-system prototype.

This launcher deliberately has no imports from apps.desktop and exposes no
backend object to QML. Everything visible in the prototype is static mock data.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="Launch the isolated GaussianOS UI prototype")
    parser.add_argument("--theme", choices=("light", "dark"), default="light")
    parser.add_argument("--width", type=int, default=1600)
    parser.add_argument("--height", type=int, default=900)
    parser.add_argument("--scale", type=float, default=None, help="Optional Qt DPI scale, e.g. 1.25")
    parser.add_argument("--page", choices=("workspace", "library"), default="workspace")
    parser.add_argument("--dialog", choices=("none", "settings"), default="none")
    parser.add_argument(
        "--density",
        choices=("compact", "standard", "comfortable"),
        default="standard",
    )
    parser.add_argument(
        "--weight",
        choices=("light", "balanced", "strong"),
        default="balanced",
    )
    parser.add_argument("--screenshot", type=Path, help="Save a rendered PNG, then exit")
    args = parser.parse_args()

    if args.scale is not None:
        os.environ["QT_SCALE_FACTOR"] = str(args.scale)
    os.environ.setdefault("QT_QUICK_CONTROLS_STYLE", "Basic")

    try:
        from PySide6.QtCore import QMetaObject, QObject, QTimer, QUrl, Qt
        from PySide6.QtGui import QCursor, QFont, QFontDatabase, QGuiApplication
        from PySide6.QtQml import QQmlApplicationEngine
    except ImportError as exc:
        raise SystemExit(
            "PySide6 is required. Run through launch.ps1 or use "
            "`uv run --extra desktop python design/ui-prototype/prototype.py`."
        ) from exc

    app = QGuiApplication(sys.argv[:1])
    app.setApplicationName("GaussianOS UI Prototype")
    app.setOrganizationName("GaussianOS")

    font_names = (
        "Montserrat-Regular.ttf",
        "Montserrat-Medium.ttf",
        "Montserrat-SemiBold.ttf",
        "Montserrat-Bold.ttf",
    )
    font_candidates = tuple(
        root / name
        for root in (
            Path(os.environ.get("WINDIR", r"C:\Windows")) / "Fonts",
            Path.home() / "AppData/Local/Microsoft/Windows/Fonts",
        )
        for name in font_names
    )
    for candidate in font_candidates:
        if candidate.exists():
            QFontDatabase.addApplicationFont(str(candidate))
    app.setFont(QFont("Montserrat", 10))

    engine = QQmlApplicationEngine()
    engine.warnings.connect(
        lambda warnings: [
            print(error.toString(), file=sys.stderr, flush=True) for error in warnings
        ]
    )
    engine.rootContext().setContextProperty("startupTheme", args.theme)
    engine.rootContext().setContextProperty("useSavedSettings", not bool(args.screenshot))
    engine.rootContext().setContextProperty("startupWidth", args.width)
    engine.rootContext().setContextProperty("startupHeight", args.height)
    qml_file = Path(__file__).resolve().parent / "qml" / "Main.qml"
    engine.load(QUrl.fromLocalFile(str(qml_file)))
    if not engine.rootObjects():
        print(f"Failed to load QML root: {qml_file}", file=sys.stderr, flush=True)
        return 2

    window = engine.rootObjects()[0]
    window.setProperty("currentPage", args.page)
    if args.screenshot:
        window.setProperty("interfaceSize", args.density)
        window.setProperty("typographyWeight", args.weight)
    if args.dialog == "settings":
        dialog = window.findChild(QObject, "settingsDialog")
        if dialog is not None:
            QMetaObject.invokeMethod(dialog, "open", Qt.ConnectionType.QueuedConnection)
    if args.screenshot:
        destination = args.screenshot.resolve()
        destination.parent.mkdir(parents=True, exist_ok=True)

        def capture() -> None:
            QCursor.setPos(0, 0)
            pixmap = app.primaryScreen().grabWindow(int(window.winId()))
            if pixmap.width() != args.width or pixmap.height() != args.height:
                pixmap = pixmap.scaled(args.width, args.height)
            if not pixmap.save(str(destination), "PNG"):
                app.exit(3)
                return
            print(f"Saved {pixmap.width()}x{pixmap.height()} preview to {destination}")
            app.quit()

        QTimer.singleShot(1800, capture)

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
