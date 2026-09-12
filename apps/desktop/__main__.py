"""Desktop entry point with a readable frozen-startup diagnostic."""
import sys
import traceback
from pathlib import Path

try:
    from apps.desktop.main import main
    raise SystemExit(main())
except Exception:
    if getattr(sys, "frozen", False):
        application = Path(sys.executable).resolve().parent
        root = application.parent if application.name.casefold() == "application" else application
        try:
            log = root / "Logs" / "startup-error.txt"
            log.parent.mkdir(parents=True, exist_ok=True)
            log.write_text(traceback.format_exc(), encoding="utf-8")
        except OSError:
            pass
    raise
