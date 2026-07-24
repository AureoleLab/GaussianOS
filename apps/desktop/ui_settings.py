"""UI-shell selection and persistence.

This module deliberately contains no Qt imports.  It can therefore resolve the
desktop shell before QML/WebEngine starts, and it remains independently
testable.  Project metadata and pipeline state never pass through this store.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


UI_CHOICES = ("modern", "classic")


@dataclass(frozen=True)
class UiSelection:
    name: str
    source: str


class UiSettingsStore:
    """Small atomic JSON store for process-level desktop preferences."""

    SCHEMA_VERSION = "gaussianos-ui-settings/v1"

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def read(self) -> dict[str, Any]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        except (OSError, TypeError, ValueError):
            return {}
        if not isinstance(payload, dict):
            return {}
        return payload

    @property
    def preferred_ui(self) -> str:
        value = str(self.read().get("preferred_ui", "")).lower()
        return value if value in UI_CHOICES else ""

    def set_preferred_ui(self, value: str) -> None:
        normalized = value.strip().lower()
        if normalized not in UI_CHOICES:
            raise ValueError(f"Unsupported UI shell: {value}")
        payload = self.read()
        payload.update(
            {
                "schema_version": self.SCHEMA_VERSION,
                "preferred_ui": normalized,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
        self._write_atomic(payload)

    def _write_atomic(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        handle, temporary = tempfile.mkstemp(
            prefix=f".{self.path.name}.",
            suffix=".tmp",
            dir=self.path.parent,
        )
        temporary_path = Path(temporary)
        try:
            with os.fdopen(handle, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(payload, stream, ensure_ascii=False, indent=2, sort_keys=True)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary_path, self.path)
        finally:
            try:
                temporary_path.unlink()
            except FileNotFoundError:
                pass


def resolve_ui(
    command_line: str | None,
    *,
    safe_ui: bool,
    persisted: str,
) -> UiSelection:
    """Resolve command line, persisted preference, then the Modern default."""

    if safe_ui:
        return UiSelection("classic", "command line --safe-ui")
    if command_line:
        normalized = command_line.lower()
        if normalized not in UI_CHOICES:
            raise ValueError(f"Unsupported UI shell: {command_line}")
        return UiSelection(normalized, "command line --ui")
    if persisted in UI_CHOICES:
        return UiSelection(persisted, "persisted setting")
    return UiSelection("modern", "default")
