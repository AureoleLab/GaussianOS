"""Small cross-process advisory file locks for filesystem transactions.

Lock files are durable diagnostics, not ownership markers.  Ownership is held
by the operating-system lock on the open file handle, so a crashed process
cannot leave a permanently blocking stale lock merely because the file remains.
"""

from __future__ import annotations

import json
import os
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import IO, Any


class ProjectLockError(RuntimeError):
    """Raised when another process owns an incompatible project operation."""


_LOCAL_GUARD = threading.Lock()
_LOCAL_LOCKS: dict[str, threading.RLock] = {}


def _local_lock(path: Path) -> threading.RLock:
    key = os.path.normcase(str(path.resolve()))
    with _LOCAL_GUARD:
        return _LOCAL_LOCKS.setdefault(key, threading.RLock())


class FileLock:
    """An exclusive advisory lock with bounded waiting and crash recovery."""

    def __init__(
        self,
        path: str | Path,
        *,
        operation: str,
        project_id: str,
        timeout: float = 0.0,
    ) -> None:
        if timeout < 0:
            raise ValueError("lock timeout cannot be negative")
        self.path = Path(path).resolve()
        self.operation = operation
        self.project_id = project_id
        self.timeout = timeout
        self._local = _local_lock(self.path)
        self._stream: IO[bytes] | None = None
        self._local_acquired = False

    def _try_os_lock(self, stream: IO[bytes]) -> bool:
        if os.name == "nt":
            import msvcrt

            stream.seek(0)
            try:
                msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
                return True
            except OSError:
                return False
        import fcntl

        try:
            fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except BlockingIOError:
            return False

    def _unlock(self, stream: IO[bytes]) -> None:
        if os.name == "nt":
            import msvcrt

            stream.seek(0)
            msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
            return
        import fcntl

        fcntl.flock(stream.fileno(), fcntl.LOCK_UN)

    def _owner_description(self) -> str:
        try:
            payload: dict[str, Any] = json.loads(self.path.read_text(encoding="utf-8"))
            return (
                f"pid={payload.get('pid', '?')}, operation={payload.get('operation', '?')}, "
                f"acquired_at={payload.get('acquired_at', '?')}"
            )
        except (OSError, ValueError, TypeError):
            return "owner details unavailable"

    def acquire(self) -> "FileLock":
        deadline = time.monotonic() + self.timeout
        while True:
            remaining = max(0.0, deadline - time.monotonic())
            acquired = self._local.acquire(
                blocking=self.timeout > 0,
                timeout=remaining if self.timeout > 0 else -1,
            ) if self.timeout > 0 else self._local.acquire(blocking=False)
            if acquired:
                self._local_acquired = True
                break
            if self.timeout == 0 or time.monotonic() >= deadline:
                raise ProjectLockError(
                    f"project {self.project_id} is busy with another {self.operation} operation"
                )

        stream: IO[bytes] | None = None
        os_locked = False
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            stream = self.path.open("a+b")
            if stream.seek(0, os.SEEK_END) == 0:
                stream.write(b"\n")
                stream.flush()
            while not self._try_os_lock(stream):
                if self.timeout == 0 or time.monotonic() >= deadline:
                    owner = self._owner_description()
                    stream.close()
                    stream = None
                    raise ProjectLockError(
                        f"project {self.project_id} is locked for {self.operation} ({owner})"
                    )
                time.sleep(min(0.05, max(0.0, deadline - time.monotonic())))
            os_locked = True
            payload = {
                "schema_version": "gaussianos-lock/v1",
                "project_id": self.project_id,
                "operation": self.operation,
                "pid": os.getpid(),
                "thread_id": threading.get_ident(),
                "acquired_at": datetime.now(timezone.utc).isoformat(),
            }
            stream.seek(0)
            stream.truncate()
            stream.write((json.dumps(payload, sort_keys=True) + "\n").encode("utf-8"))
            stream.flush()
            os.fsync(stream.fileno())
            self._stream = stream
            return self
        except Exception:
            if stream is not None:
                try:
                    if os_locked:
                        self._unlock(stream)
                finally:
                    stream.close()
            if self._local_acquired:
                self._local.release()
                self._local_acquired = False
            raise

    def release(self) -> None:
        stream, self._stream = self._stream, None
        try:
            if stream is not None:
                try:
                    self._unlock(stream)
                finally:
                    stream.close()
        finally:
            if self._local_acquired:
                self._local.release()
                self._local_acquired = False

    def __enter__(self) -> "FileLock":
        return self.acquire()

    def __exit__(self, _exc_type: object, _exc: object, _traceback: object) -> None:
        self.release()
