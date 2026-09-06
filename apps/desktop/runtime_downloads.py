"""Bounded, hash-locked and resumable downloads for release components."""
from __future__ import annotations

import hashlib
import io
import os
import re
import shutil
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable


class SegmentedReader(io.RawIOBase):
    """Seek across verified ZIP segments without a second multi-GB archive."""
    def __init__(self, paths: list[Path]):
        super().__init__()
        self.paths = paths
        self.sizes = [p.stat().st_size for p in paths]
        self.length = sum(self.sizes)
        self.position = 0

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.position

    def seek(self, offset, whence=io.SEEK_SET):
        position = offset + (self.position if whence == io.SEEK_CUR else self.length if whence == io.SEEK_END else 0)
        if position < 0 or whence not in (io.SEEK_SET, io.SEEK_CUR, io.SEEK_END):
            raise ValueError("Invalid archive seek")
        self.position = position
        return position

    def read(self, size=-1):
        remaining = max(0, self.length - self.position)
        wanted = remaining if size < 0 else min(size, remaining)
        chunks = []
        start = 0
        for path, length in zip(self.paths, self.sizes):
            if wanted and self.position < start + length:
                offset = max(0, self.position - start)
                count = min(wanted, length - offset)
                with path.open("rb") as stream:
                    stream.seek(offset)
                    data = stream.read(count)
                if len(data) != count:
                    raise OSError(f"Archive segment changed: {path.name}")
                chunks.append(data)
                self.position += count
                wanted -= count
            start += length
        return b"".join(chunks)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def download_verified(url: str, destination: Path, *, size: int, digest: str,
                      progress: Callable[[int, int], None] | None = None,
                      cancelled: Callable[[], bool] | None = None,
                      attempts: int = 3) -> Path:
    if size <= 0 or not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise ValueError("Download requires a positive length and SHA-256")
    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_name(destination.name + ".part")
    if destination.is_file():
        if destination.stat().st_size == size and sha256(destination) == digest:
            return destination
        destination.unlink()
    last_error = None
    for attempt in range(attempts):
        if cancelled and cancelled():
            raise InterruptedError("Runtime download cancelled; partial download retained")
        try:
            offset = partial.stat().st_size if partial.exists() else 0
            if offset >= size:
                if offset == size and sha256(partial) == digest:
                    os.replace(partial, destination)
                    return destination
                partial.unlink()
                offset = 0
            if shutil.disk_usage(destination.parent).free < size - offset + 512 * 1024**2:
                raise OSError("Not enough free space to finish downloading this component")
            request = urllib.request.Request(url, headers={
                "User-Agent": "GaussianOS-Beta-Installer", "Accept-Encoding": "identity",
                **({"Range": f"bytes={offset}-"} if offset else {}),
            })
            with urllib.request.urlopen(request, timeout=30) as response:
                resumed = offset > 0 and response.status == 206
                if response.status == 206:
                    header = response.headers.get("Content-Range", "")
                    match = re.fullmatch(r"bytes (\d+)-(\d+)/(\d+)", header)
                    if not match or (int(match[1]), int(match[2]), int(match[3])) != (offset, size - 1, size):
                        partial.unlink(missing_ok=True)
                        raise RuntimeError(f"Server returned an invalid resume range: {header}")
                elif response.status != 200:
                    raise RuntimeError(f"Unexpected download HTTP status: {response.status}")
                if not resumed:
                    offset = 0
                done = offset
                with partial.open("ab" if resumed else "wb") as output:
                    while block := response.read(1024 * 1024):
                        if cancelled and cancelled():
                            raise InterruptedError("Runtime download cancelled; partial download retained")
                        if done + len(block) > size:
                            raise RuntimeError("Download exceeds its locked size")
                        output.write(block)
                        done += len(block)
                        if progress:
                            progress(done, size)
            if partial.stat().st_size != size:
                raise RuntimeError("Download was interrupted before the locked size")
            if sha256(partial) != digest:
                partial.unlink()
                raise RuntimeError("Downloaded component failed SHA-256; retrying from the beginning")
            os.replace(partial, destination)
            return destination
        except InterruptedError:
            raise
        except (OSError, ValueError, RuntimeError, urllib.error.URLError) as exc:
            last_error = exc
            if isinstance(exc, urllib.error.HTTPError) and exc.code == 416:
                partial.unlink(missing_ok=True)
            if attempt + 1 < attempts:
                time.sleep(min(2 ** attempt, 4))
    raise RuntimeError(f"Runtime download failed after {attempts} attempts: {last_error}")
