"""Run an algorithm worker without importing it into the host process."""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from packages.artifact_store import (
    ArtifactCommitError,
    ArtifactStore,
    ArtifactStoreError,
    ArtifactValidationError,
    AttemptHandle,
    CommitRecord,
)
from packages.artifact_store.store import atomic_write_json
from packages.licensing import PolicyError, ProfilePolicyRegistry
from packages.plugin_sdk import (
    ErrorCode,
    PluginManifest,
    StageError,
    StageRequest,
    StageResult,
    StageStatus,
)


@dataclass(frozen=True, slots=True)
class ExecutionOutcome:
    result: StageResult
    committed_artifacts: tuple[CommitRecord, ...] = ()
    attempt_archive: Path | None = None
    return_code: int | None = None


class CancellationToken:
    """Thread-safe host cancellation signal with a human-readable reason."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self._lock = threading.Lock()
        self._reason = "cancelled by caller"

    def cancel(self, reason: str = "cancelled by caller") -> None:
        if not reason:
            raise ValueError("cancellation reason cannot be empty")
        with self._lock:
            if not self._event.is_set():
                self._reason = reason
                self._event.set()

    @property
    def is_cancelled(self) -> bool:
        return self._event.is_set()

    @property
    def reason(self) -> str:
        with self._lock:
            return self._reason


class SubprocessWorkerRunner:
    """Policy-gated, timeout-aware worker runner.

    The runner imports shared contracts only.  Worker commands are executed with
    ``shell=False`` in a new process group and communicate exclusively through
    versioned JSON files in their attempt directory.
    """

    MAX_RESULT_JSON_BYTES = 16 * 1024 * 1024

    def __init__(
        self,
        artifact_store: ArtifactStore,
        policy_registry: ProfilePolicyRegistry,
        *,
        worker_cwd: str | Path | None = None,
        python_executable: str | Path | None = None,
        poll_interval_seconds: float = 0.025,
        cancellation_grace_seconds: float = 0.25,
    ) -> None:
        if poll_interval_seconds <= 0:
            raise ValueError("poll_interval_seconds must be positive")
        if cancellation_grace_seconds < 0:
            raise ValueError("cancellation_grace_seconds cannot be negative")
        self.artifact_store = artifact_store
        self.policy_registry = policy_registry
        self.worker_cwd = Path(worker_cwd or Path.cwd()).resolve()
        self.python_executable = str(python_executable or sys.executable)
        self.poll_interval_seconds = poll_interval_seconds
        self.cancellation_grace_seconds = cancellation_grace_seconds

    def run(
        self,
        request: StageRequest,
        manifest: PluginManifest,
        *,
        timeout_seconds: float,
        cancellation_token: CancellationToken | None = None,
    ) -> ExecutionOutcome:
        started_at = datetime.now(timezone.utc)
        if cancellation_token is not None and cancellation_token.is_cancelled:
            result = self._failure_result(
                request,
                started_at,
                ErrorCode.CANCELLED,
                cancellation_token.reason,
                retryable=False,
                status=StageStatus.CANCELLED,
            )
            return ExecutionOutcome(result=result)
        if timeout_seconds <= 0:
            return self._rejected_outcome(
                request,
                started_at,
                ErrorCode.INVALID_REQUEST,
                "timeout_seconds must be positive",
            )
        effective_timeout_seconds = timeout_seconds
        if request.deadline_utc is not None:
            remaining = (request.deadline_utc - started_at).total_seconds()
            if remaining <= 0:
                return self._rejected_outcome(
                    request,
                    started_at,
                    ErrorCode.TIMEOUT,
                    "request deadline has already expired",
                )
            effective_timeout_seconds = min(timeout_seconds, remaining)
        contract_error = self._request_manifest_error(request, manifest)
        if contract_error is not None:
            return self._rejected_outcome(
                request,
                started_at,
                ErrorCode.INVALID_REQUEST,
                contract_error,
            )
        try:
            self.policy_registry.enforce(manifest, request.profile)
        except (PolicyError, KeyError) as exc:
            return self._rejected_outcome(
                request,
                started_at,
                ErrorCode.POLICY_DENIED,
                str(exc),
            )

        attempt = self.artifact_store.begin_attempt(
            request.run_id, request.stage_id, str(request.request_id)
        )
        bound_request = request.model_copy(
            update={
                "attempt_id": attempt.attempt_id,
                "attempt_dir": str(attempt.path),
                "cancellation_file": str(attempt.cancellation_file),
            }
        )
        # model_copy does not validate updates; force a complete validation before
        # serializing anything a worker can consume.
        bound_request = StageRequest.model_validate(bound_request.model_dump())
        request_path = attempt.path / "request.json"
        result_path = attempt.path / "result.worker.json"
        stdout_path = attempt.path / "stdout.log"
        stderr_path = attempt.path / "stderr.log"
        atomic_write_json(request_path, bound_request.model_dump(mode="json"))

        command = self._build_command(manifest, request_path, result_path)
        env = os.environ.copy()
        env.update(manifest.entrypoint.environment)
        env.update(
            {
                "GAUSSIAN_FACTORY_ATTEMPT_ID": attempt.attempt_id,
                "GAUSSIAN_FACTORY_ATTEMPT_DIR": str(attempt.path),
                "GAUSSIAN_FACTORY_PROFILE": request.profile.value,
            }
        )

        process: subprocess.Popen[bytes] | None = None
        stop_reason: ErrorCode | None = None
        stop_message = ""
        return_code: int | None = None
        try:
            with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
                popen_options: dict[str, Any] = {
                    "args": command,
                    "cwd": self.worker_cwd,
                    "env": env,
                    "stdin": subprocess.DEVNULL,
                    "stdout": stdout,
                    "stderr": stderr,
                    "shell": False,
                    "close_fds": True,
                }
                if os.name == "nt":
                    popen_options["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
                else:
                    popen_options["start_new_session"] = True
                process = subprocess.Popen(**popen_options)
                return_code, stop_reason, stop_message = self._wait_for_process(
                    process,
                    attempt,
                    effective_timeout_seconds,
                    cancellation_token,
                )
        except OSError as exc:
            result = self._failure_result(
                request,
                started_at,
                ErrorCode.DEPENDENCY_MISSING,
                f"worker process could not start: {exc}",
                retryable=False,
            )
            archive = self._finish_failure(attempt, result, return_code)
            return ExecutionOutcome(result, attempt_archive=archive, return_code=return_code)
        except Exception as exc:
            if process is not None and process.poll() is None:
                self._terminate_process_tree(process)
            result = self._failure_result(
                request,
                started_at,
                ErrorCode.INTERNAL_ERROR,
                f"runner failed while supervising worker: {exc}",
                retryable=False,
            )
            archive = self._finish_failure(attempt, result, return_code)
            return ExecutionOutcome(result, attempt_archive=archive, return_code=return_code)

        if stop_reason is not None:
            status = (
                StageStatus.CANCELLED
                if stop_reason is ErrorCode.CANCELLED
                else StageStatus.FAILED
            )
            result = self._failure_result(
                request,
                started_at,
                stop_reason,
                stop_message,
                retryable=stop_reason is ErrorCode.TIMEOUT,
                status=status,
            )
            archive = self._finish_failure(attempt, result, return_code)
            return ExecutionOutcome(result, attempt_archive=archive, return_code=return_code)

        result, parse_error = self._load_and_validate_result(
            result_path, request, manifest, started_at
        )
        if parse_error is not None:
            stderr_tail = self._read_tail(stderr_path)
            error_code = self._classify_process_failure(return_code, stderr_tail)
            if return_code == 0:
                error_code = ErrorCode.INVALID_RESULT
            result = self._failure_result(
                request,
                started_at,
                error_code,
                parse_error,
                retryable=error_code in {ErrorCode.WORKER_CRASHED, ErrorCode.CUDA_OOM},
                details={"return_code": return_code, "stderr_tail": stderr_tail},
            )
            archive = self._finish_failure(attempt, result, return_code)
            return ExecutionOutcome(result, attempt_archive=archive, return_code=return_code)

        assert result is not None
        if result.status is not StageStatus.SUCCEEDED:
            archive = self._finish_failure(attempt, result, return_code)
            return ExecutionOutcome(result, attempt_archive=archive, return_code=return_code)
        if return_code != 0:
            result = self._failure_result(
                request,
                started_at,
                self._classify_process_failure(return_code, self._read_tail(stderr_path)),
                f"worker returned exit code {return_code} despite a success result",
                retryable=True,
                details={"return_code": return_code},
            )
            archive = self._finish_failure(attempt, result, return_code)
            return ExecutionOutcome(result, attempt_archive=archive, return_code=return_code)

        try:
            commits = self.artifact_store.commit(attempt, result.artifacts)
        except ArtifactValidationError as exc:
            failed = self._failure_result(
                request,
                started_at,
                ErrorCode.OUTPUT_VALIDATION_FAILED,
                str(exc),
                retryable=False,
            )
            archive = self._finish_failure(attempt, failed, return_code)
            return ExecutionOutcome(failed, attempt_archive=archive, return_code=return_code)
        except (ArtifactCommitError, ArtifactStoreError) as exc:
            failed = self._failure_result(
                request,
                started_at,
                ErrorCode.ARTIFACT_COMMIT_FAILED,
                str(exc),
                retryable=True,
            )
            archive = self._finish_failure(attempt, failed, return_code)
            return ExecutionOutcome(failed, attempt_archive=archive, return_code=return_code)

        try:
            archive = self.artifact_store.finish_attempt(
                attempt,
                "succeeded",
                {
                    "return_code": return_code,
                    "artifact_ids": [item.artifact_id for item in commits],
                },
            )
        except (ArtifactStoreError, OSError):
            # Artifacts have already been atomically published.  Failure to move
            # audit logs must not turn a successful, committed stage into a
            # misleading failure or throw through the host process.
            archive = attempt.path
        return ExecutionOutcome(
            result=result,
            committed_artifacts=commits,
            attempt_archive=archive,
            return_code=return_code,
        )

    @staticmethod
    def _request_manifest_error(
        request: StageRequest, manifest: PluginManifest
    ) -> str | None:
        if request.attempt_id is not None:
            return "attempt runtime fields are host-owned and must be unset"
        if request.plugin_id != manifest.plugin_id:
            return "request plugin_id does not match manifest"
        if request.plugin_version != manifest.plugin_version:
            return "request plugin_version does not match manifest"
        if request.stage_kind not in manifest.stage_kinds:
            return "request stage_kind is not supported by the plugin"
        if request.schema_version not in manifest.supported_request_versions:
            return "request schema version is not supported by the plugin"
        return None

    def _build_command(
        self, manifest: PluginManifest, request_path: Path, result_path: Path
    ) -> list[str]:
        command = [
            self.python_executable if item == "{python}" else item
            for item in manifest.entrypoint.command
        ]
        return command + [
            "--request-json",
            str(request_path),
            "--result-json",
            str(result_path),
        ]

    def _wait_for_process(
        self,
        process: subprocess.Popen[bytes],
        attempt: AttemptHandle,
        timeout_seconds: float,
        token: CancellationToken | None,
    ) -> tuple[int, ErrorCode | None, str]:
        deadline = time.monotonic() + timeout_seconds
        requested_stop: ErrorCode | None = None
        stop_message = ""
        grace_deadline = 0.0

        while True:
            return_code = process.poll()
            if return_code is not None:
                return return_code, requested_stop, stop_message

            now = time.monotonic()
            if requested_stop is None and token is not None and token.is_cancelled:
                requested_stop = ErrorCode.CANCELLED
                stop_message = token.reason
                grace_deadline = now + self.cancellation_grace_seconds
                atomic_write_json(
                    attempt.cancellation_file,
                    {"schema_version": "1.0.0", "reason": stop_message},
                )
            elif requested_stop is None and now >= deadline:
                requested_stop = ErrorCode.TIMEOUT
                stop_message = f"worker exceeded timeout of {timeout_seconds:.3f} seconds"
                grace_deadline = now + self.cancellation_grace_seconds
                atomic_write_json(
                    attempt.cancellation_file,
                    {"schema_version": "1.0.0", "reason": stop_message},
                )

            if requested_stop is not None and now >= grace_deadline:
                self._terminate_process_tree(process)
                return process.wait(), requested_stop, stop_message
            time.sleep(self.poll_interval_seconds)

    @staticmethod
    def _terminate_process_tree(process: subprocess.Popen[bytes]) -> None:
        if process.poll() is not None:
            return
        if os.name == "nt":
            try:
                subprocess.run(
                    ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    check=False,
                    timeout=5,
                )
            except (OSError, subprocess.TimeoutExpired):
                pass
            if process.poll() is None:
                process.kill()
            return

        try:
            os.killpg(process.pid, signal.SIGTERM)
            process.wait(timeout=1)
        except (ProcessLookupError, subprocess.TimeoutExpired):
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass

    @staticmethod
    def _load_and_validate_result(
        result_path: Path,
        request: StageRequest,
        manifest: PluginManifest,
        runner_started_at: datetime,
    ) -> tuple[StageResult | None, str | None]:
        if not result_path.is_file() or result_path.is_symlink():
            return None, "worker did not write a result JSON file"
        try:
            if result_path.stat().st_size > SubprocessWorkerRunner.MAX_RESULT_JSON_BYTES:
                return None, "worker result exceeds the 16 MiB protocol limit"
            result = StageResult.model_validate_json(result_path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError, ValidationError) as exc:
            return None, f"worker result failed schema validation: {exc}"
        if result.request_id != request.request_id:
            return None, "worker result request_id does not match"
        if result.run_id != request.run_id or result.stage_id != request.stage_id:
            return None, "worker result run/stage identity does not match"
        if result.plugin_id != manifest.plugin_id:
            return None, "worker result plugin_id does not match manifest"
        if result.plugin_version != manifest.plugin_version:
            return None, "worker result plugin_version does not match manifest"
        if result.schema_version not in manifest.supported_result_versions:
            return None, "worker result schema version is not supported"
        for artifact in result.artifacts:
            if artifact.producer_plugin_id != manifest.plugin_id:
                return None, "artifact producer_plugin_id does not match manifest"
            if artifact.producer_plugin_version != manifest.plugin_version:
                return None, "artifact producer_plugin_version does not match manifest"
        # Allow small clock skew, but reject a result claiming to have completed
        # before this execution was started by more than one second.
        if result.finished_at < runner_started_at.replace(microsecond=0):
            return None, "worker result timestamps predate this execution"
        return result, None

    @staticmethod
    def _read_tail(path: Path, limit: int = 4096) -> str:
        try:
            with path.open("rb") as stream:
                stream.seek(0, os.SEEK_END)
                length = stream.tell()
                stream.seek(max(0, length - limit))
                return stream.read().decode("utf-8", errors="replace")
        except OSError:
            return ""

    @staticmethod
    def _classify_process_failure(return_code: int | None, stderr_tail: str) -> ErrorCode:
        lowered = stderr_tail.lower()
        cuda_signatures = (
            "cuda out of memory",
            "cudnn_status_alloc_failed",
            "cuda_error_out_of_memory",
        )
        if any(signature in lowered for signature in cuda_signatures):
            return ErrorCode.CUDA_OOM
        if "no module named" in lowered or "module not found" in lowered:
            return ErrorCode.DEPENDENCY_MISSING
        return ErrorCode.WORKER_CRASHED

    @staticmethod
    def _failure_result(
        request: StageRequest,
        started_at: datetime,
        code: ErrorCode,
        message: str,
        *,
        retryable: bool,
        status: StageStatus = StageStatus.FAILED,
        details: dict[str, Any] | None = None,
    ) -> StageResult:
        return StageResult(
            request_id=request.request_id,
            run_id=request.run_id,
            stage_id=request.stage_id,
            plugin_id=request.plugin_id,
            plugin_version=request.plugin_version,
            status=status,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            error=StageError(
                code=code,
                message=message[:4000] or code.value,
                retryable=retryable,
                details=details or {},
            ),
        )

    def _finish_failure(
        self, attempt: AttemptHandle, result: StageResult, return_code: int | None
    ) -> Path:
        try:
            atomic_write_json(
                attempt.path / "result.host.json", result.model_dump(mode="json")
            )
            return self.artifact_store.finish_attempt(
                attempt,
                "cancelled" if result.status is StageStatus.CANCELLED else "failed",
                {
                    "return_code": return_code,
                    "error_code": result.error.code.value if result.error else None,
                },
            )
        except (ArtifactStoreError, OSError):
            # Preserve the best available diagnostic path while ensuring a
            # worker/storage failure cannot propagate through the orchestrator.
            return attempt.path

    @classmethod
    def _rejected_outcome(
        cls,
        request: StageRequest,
        started_at: datetime,
        code: ErrorCode,
        message: str,
    ) -> ExecutionOutcome:
        result = cls._failure_result(
            request,
            started_at,
            code,
            message,
            retryable=False,
        )
        return ExecutionOutcome(result=result)
