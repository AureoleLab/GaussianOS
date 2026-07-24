"""Paths passed to native tools with conservative Windows long-path support."""

from __future__ import annotations

import os
from pathlib import Path


def native_tool_path(path: str | Path) -> str:
    """Return an absolute path suitable for native Windows command-line tools."""

    resolved = str(Path(path).resolve())
    if os.name != "nt" or resolved.startswith("\\\\?\\"):
        return resolved
    if resolved.startswith("\\\\"):
        return "\\\\?\\UNC\\" + resolved[2:]
    return "\\\\?\\" + resolved
