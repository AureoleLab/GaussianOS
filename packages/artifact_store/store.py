"""Filesystem artifact store with fail-before-publish validation.

Workers may only write under ``attempts/<run>/<stage>/<attempt>/outputs``.  The
host verifies the exact declared file set, sizes and SHA-256 hashes before an
``os.replace`` publishes each artifact directory.  Attempts that fail remain in
``failed_attempts`` for diagnosis and never appear under ``artifacts``.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence
from uuid import uuid4

from packages.file_lock import FileLock, ProjectLockError
from packages.plugin_sdk import ArtifactManifest


class ArtifactStoreError(RuntimeError):
    pass


class ArtifactValidationError(ArtifactStoreError):
    pass


class ArtifactConflictError(ArtifactStoreError):
    pass


class ArtifactCommitError(ArtifactStoreError):
    pass


@dataclass(frozen=True, slots=True)
class AttemptHandle:
    attempt_id: str
    run_id: str
    stage_id: str
    request_id: str
    path: Path

    @property
    def outputs_dir(self) -> Path:
        return self.path / "outputs"

    @property
    def cancellation_file(self) -> Path:
        return self.path / "cancel.json"


@dataclass(frozen=True, slots=True)
class CommitRecord:
    artifact_id: str
    path: Path
    manifest_sha256: str


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _canonical_json_bytes(payload: Any) -> bytes:
    return (
        json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        + b"\n"
    )


def atomic_write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    data = _canonical_json_bytes(payload)
    try:
        with temporary.open("xb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


class ArtifactStore:
    """A single-filesystem store so directory rename is atomic."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root).resolve()
        self.attempts_root = self.root / "attempts"
        self.completed_attempts_root = self.root / "completed_attempts"
        self.failed_attempts_root = self.root / "failed_attempts"
        self.artifacts_root = self.root / "artifacts"
        self.commit_locks_root = self.root / ".commit_locks"
        for directory in (
            self.attempts_root,
            self.completed_attempts_root,
            self.failed_attempts_root,
            self.artifacts_root,
            self.commit_locks_root,
        ):
            directory.mkdir(parents=True, exist_ok=True)

    def begin_attempt(self, run_id: str, stage_id: str, request_id: str) -> AttemptHandle:
        # run_id/stage_id are already contract-validated.  Re-check the resolved
        # path boundary because this class can also be used independently.
        for label, value in (("run_id", run_id), ("stage_id", stage_id)):
            if not value or any(item in value for item in ("/", "\\", "..")):
                raise ValueError(f"unsafe {label}")
        attempt_id = f"attempt-{uuid4().hex}"
        path = self.attempts_root / run_id / stage_id / attempt_id
        path.mkdir(parents=True, exist_ok=False)
        (path / "outputs").mkdir()
        handle = AttemptHandle(
            attempt_id=attempt_id,
            run_id=run_id,
            stage_id=stage_id,
            request_id=request_id,
            path=path,
        )
        atomic_write_json(
            path / "attempt.json",
            {
                "schema_version": "1.0.0",
                "attempt_id": attempt_id,
                "request_id": request_id,
                "run_id": run_id,
                "stage_id": stage_id,
                "state": "running",
                "created_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        return handle

    def artifact_output_path(self, attempt: AttemptHandle, artifact_id: str) -> Path:
        if not artifact_id or any(item in artifact_id for item in ("/", "\\", "..")):
            raise ValueError("unsafe artifact_id")
        return attempt.outputs_dir / artifact_id

    def validate_artifacts(
        self,
        attempt: AttemptHandle,
        manifests: Sequence[ArtifactManifest],
    ) -> None:
        if not manifests:
            raise ArtifactValidationError("at least one artifact manifest is required")
        ids = [manifest.artifact_id for manifest in manifests]
        if len(ids) != len(set(ids)):
            raise ArtifactValidationError("artifact_id values must be unique")

        for manifest in manifests:
            self._validate_artifact(attempt, manifest)

    def _validate_artifact(
        self, attempt: AttemptHandle, manifest: ArtifactManifest
    ) -> None:
        if manifest.source_attempt_id != attempt.attempt_id:
            raise ArtifactValidationError(
                f"artifact {manifest.artifact_id}: source_attempt_id does not match"
            )
        if str(manifest.source_request_id) != attempt.request_id:
            raise ArtifactValidationError(
                f"artifact {manifest.artifact_id}: source_request_id does not match"
            )

        artifact_root = self.artifact_output_path(attempt, manifest.artifact_id)
        if not artifact_root.is_dir() or artifact_root.is_symlink():
            raise ArtifactValidationError(
                f"artifact {manifest.artifact_id}: output directory is missing or unsafe"
            )
        resolved_root = artifact_root.resolve(strict=True)
        expected_paths = {item.relative_path for item in manifest.files}
        actual_paths: set[str] = set()

        for candidate in artifact_root.rglob("*"):
            if candidate.is_symlink():
                raise ArtifactValidationError(
                    f"artifact {manifest.artifact_id}: symlinks are forbidden"
                )
            if candidate.is_file():
                actual_paths.add(candidate.relative_to(artifact_root).as_posix())
            elif not candidate.is_dir():
                raise ArtifactValidationError(
                    f"artifact {manifest.artifact_id}: unsupported filesystem entry"
                )

        if actual_paths != expected_paths:
            missing = sorted(expected_paths - actual_paths)
            undeclared = sorted(actual_paths - expected_paths)
            raise ArtifactValidationError(
                f"artifact {manifest.artifact_id}: file set mismatch; "
                f"missing={missing}, undeclared={undeclared}"
            )

        for declared in manifest.files:
            path = artifact_root.joinpath(*declared.relative_path.split("/"))
            try:
                resolved = path.resolve(strict=True)
                resolved.relative_to(resolved_root)
            except (OSError, ValueError) as exc:
                raise ArtifactValidationError(
                    f"artifact {manifest.artifact_id}: file escapes output directory"
                ) from exc
            if not resolved.is_file() or resolved.is_symlink():
                raise ArtifactValidationError(
                    f"artifact {manifest.artifact_id}: declared path is not a regular file"
                )
            stat = resolved.stat()
            if stat.st_size != declared.size_bytes:
                raise ArtifactValidationError(
                    f"artifact {manifest.artifact_id}: size mismatch for "
                    f"{declared.relative_path}"
                )
            actual_hash = sha256_file(resolved)
            if actual_hash != declared.sha256:
                raise ArtifactValidationError(
                    f"artifact {manifest.artifact_id}: SHA-256 mismatch for "
                    f"{declared.relative_path}"
                )

    def commit(
        self,
        attempt: AttemptHandle,
        manifests: Sequence[ArtifactManifest],
    ) -> tuple[CommitRecord, ...]:
        """Validate every output, then atomically publish each artifact directory.

        Validation is performed for the complete set before the first rename.
        If a later rename fails, already-renamed directories are moved back into
        the attempt before the error is returned.
        """

        locks = self._acquire_commit_locks(manifests)
        try:
            self.validate_artifacts(attempt, manifests)
            manifest_payloads: dict[str, bytes] = {}
            committed: list[tuple[ArtifactManifest, Path, Path]] = []
            records: list[CommitRecord] = []
            try:
                for manifest in manifests:
                    payload = _canonical_json_bytes(manifest.model_dump(mode="json"))
                    manifest_payloads[manifest.artifact_id] = payload
                    atomic_write_json(
                        self.artifact_output_path(attempt, manifest.artifact_id)
                        / "artifact.manifest.json",
                        manifest.model_dump(mode="json"),
                    )
                for manifest in manifests:
                    source = self.artifact_output_path(attempt, manifest.artifact_id)
                    destination = self.artifacts_root / manifest.artifact_id
                    if destination.exists():
                        raise ArtifactConflictError(
                            f"artifact destination already exists: {manifest.artifact_id}"
                        )
                    os.replace(source, destination)
                    committed.append((manifest, source, destination))
                    records.append(
                        CommitRecord(
                            artifact_id=manifest.artifact_id,
                            path=destination,
                            manifest_sha256=hashlib.sha256(
                                manifest_payloads[manifest.artifact_id]
                            ).hexdigest(),
                        )
                    )
            except Exception as exc:
                rollback_errors: list[str] = []
                for _manifest, source, destination in reversed(committed):
                    try:
                        os.replace(destination, source)
                    except OSError as rollback_exc:
                        rollback_errors.append(str(rollback_exc))
                if isinstance(exc, ArtifactStoreError) and not rollback_errors:
                    raise
                suffix = f"; rollback errors={rollback_errors}" if rollback_errors else ""
                raise ArtifactCommitError(f"artifact commit failed: {exc}{suffix}") from exc

            return tuple(records)
        finally:
            for lock in reversed(locks):
                lock.release()

    def _acquire_commit_locks(
        self, manifests: Sequence[ArtifactManifest]
    ) -> tuple[FileLock, ...]:
        acquired: list[FileLock] = []
        try:
            for artifact_id in sorted(manifest.artifact_id for manifest in manifests):
                lock = FileLock(
                    self.commit_locks_root / f"{artifact_id}.lock",
                    operation="artifact-commit",
                    project_id=artifact_id,
                )
                try:
                    lock.acquire()
                except ProjectLockError as exc:
                    raise ArtifactConflictError(
                        f"artifact commit is already in progress: {artifact_id}"
                    ) from exc
                acquired.append(lock)
        except Exception:
            for lock in reversed(acquired):
                lock.release()
            raise
        return tuple(acquired)

    def finish_attempt(
        self,
        attempt: AttemptHandle,
        state: str,
        details: dict[str, Any] | None = None,
    ) -> Path:
        if state not in {"succeeded", "failed", "cancelled"}:
            raise ValueError("attempt state must be terminal")
        atomic_write_json(
            attempt.path / "attempt.final.json",
            {
                "schema_version": "1.0.0",
                "attempt_id": attempt.attempt_id,
                "request_id": attempt.request_id,
                "run_id": attempt.run_id,
                "stage_id": attempt.stage_id,
                "state": state,
                "finished_at": datetime.now(timezone.utc).isoformat(),
                "details": details or {},
            },
        )
        state_root = (
            self.completed_attempts_root if state == "succeeded" else self.failed_attempts_root
        )
        destination = state_root / attempt.run_id / attempt.stage_id / attempt.attempt_id
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            raise ArtifactStoreError(f"attempt archive already exists: {destination}")
        os.replace(attempt.path, destination)
        self._prune_empty_parents(attempt.path.parent, self.attempts_root)
        return destination

    @staticmethod
    def _prune_empty_parents(start: Path, stop: Path) -> None:
        current = start
        while current != stop:
            try:
                current.rmdir()
            except OSError:
                return
            current = current.parent

    def read_manifest(self, artifact_id: str) -> ArtifactManifest:
        path = self.artifacts_root / artifact_id / "artifact.manifest.json"
        return ArtifactManifest.model_validate_json(path.read_text(encoding="utf-8"))
