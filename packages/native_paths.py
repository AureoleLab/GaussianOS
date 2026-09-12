"""Paths passed to native tools with conservative Windows long-path support."""

from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path


def native_tool_path(path: str | Path) -> str:
    """Return an absolute path suitable for native Windows command-line tools."""

    resolved = str(Path(path).resolve())
    if os.name != "nt" or resolved.startswith("\\\\?\\"):
        return resolved
    if resolved.startswith("\\\\"):
        return "\\\\?\\UNC\\" + resolved[2:]
    return "\\\\?\\" + resolved


@contextmanager
def native_output_directory(path: str | Path):
    """Give a single-purpose worker an ASCII relative native output path.

    Some pycolmap Windows wheels interpret C++ narrow absolute paths using the
    system code page and reject UTF-8 names even with a long-path prefix.
    CPython changes cwd through the Unicode Windows API; native calls then use
    only relative ASCII paths. Use only in an isolated worker, never a GUI or
    multi-job host, because cwd is process-wide.
    """
    output = Path(path).resolve()
    output.mkdir(parents=True, exist_ok=True)
    previous = Path.cwd()
    os.chdir(output)
    try:
        yield "."
    finally:
        os.chdir(previous)
