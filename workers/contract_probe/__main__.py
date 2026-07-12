"""Contract probe worker; intentionally contains no algorithm dependency."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from packages.plugin_sdk import (
    ArtifactFile,
    ArtifactManifest,
    ErrorCode,
    QualityCheck,
    QualityReport,
    StageError,
    StageRequest,
    StageResult,
    StageStatus,
)


def _atomic_json(path: Path, model: StageResult) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    payload = json.dumps(
        model.model_dump(mode="json"),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _cancelled_result(request: StageRequest, started_at: datetime) -> StageResult:
    return StageResult(
        request_id=request.request_id,
        run_id=request.run_id,
        stage_id=request.stage_id,
        plugin_id=request.plugin_id,
        plugin_version=request.plugin_version,
        status=StageStatus.CANCELLED,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        error=StageError(
            code=ErrorCode.CANCELLED,
            message="worker observed cancellation file",
            retryable=False,
        ),
    )


def _successful_result(request: StageRequest, started_at: datetime, mode: str) -> StageResult:
    assert request.attempt_dir is not None
    assert request.attempt_id is not None
    artifact_id = f"probe-{request.request_id.hex}"
    output_root = Path(request.attempt_dir) / "outputs" / artifact_id
    output_root.mkdir(parents=True, exist_ok=False)

    payload_value = request.config.get("payload", "contract probe ok")
    if not isinstance(payload_value, str):
        raise TypeError("probe payload must be a string")
    payload = payload_value.encode("utf-8")
    payload_path = output_root / "payload.txt"
    payload_path.write_bytes(payload)
    digest = hashlib.sha256(payload).hexdigest()
    if mode == "bad_hash":
        digest = "0" * 64
    if mode == "undeclared_file":
        (output_root / "undeclared.bin").write_bytes(b"not in manifest")

    artifact = ArtifactManifest(
        artifact_id=artifact_id,
        artifact_type="contract_probe",
        format_version="1.0.0",
        producer_plugin_id=request.plugin_id,
        producer_plugin_version=request.plugin_version,
        source_request_id=request.request_id,
        source_attempt_id=request.attempt_id,
        files=(
            ArtifactFile(
                relative_path="payload.txt",
                sha256=digest,
                size_bytes=len(payload),
                media_type="text/plain; charset=utf-8",
            ),
        ),
        metadata={"probe_mode": mode},
    )
    quality = QualityReport(
        passed=True,
        checks=(
            QualityCheck(
                check_id="probe.output",
                passed=True,
                required=True,
                message="probe output was written",
            ),
        ),
        metrics={"payload_bytes": float(len(payload))},
    )
    return StageResult(
        request_id=request.request_id,
        run_id=request.run_id,
        stage_id=request.stage_id,
        plugin_id=request.plugin_id,
        plugin_version=request.plugin_version,
        status=StageStatus.SUCCEEDED,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        artifacts=(artifact,),
        quality_report=quality,
    )


def run(request_path: Path, result_path: Path) -> int:
    started_at = datetime.now(timezone.utc)
    try:
        request = StageRequest.model_validate_json(request_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValidationError) as exc:
        print(f"invalid request: {exc}", file=sys.stderr)
        return 2

    if request.attempt_dir is None or request.attempt_id is None:
        print("request has no host-bound attempt", file=sys.stderr)
        return 2
    attempt_root = Path(request.attempt_dir).resolve()
    try:
        result_path.resolve().relative_to(attempt_root)
    except ValueError:
        print("result path is outside the attempt directory", file=sys.stderr)
        return 2

    mode_value: Any = request.config.get("mode", "success")
    if not isinstance(mode_value, str):
        print("mode must be a string", file=sys.stderr)
        return 2
    mode = mode_value

    if mode == "crash":
        raise RuntimeError("intentional contract probe crash")
    if mode == "cuda_oom":
        print("CUDA out of memory: intentional contract probe", file=sys.stderr)
        return 20
    if mode == "invalid_json":
        result_path.write_text("{not valid json", encoding="utf-8")
        return 0
    if mode == "no_result":
        return 0
    if mode == "reported_failure":
        result = StageResult(
            request_id=request.request_id,
            run_id=request.run_id,
            stage_id=request.stage_id,
            plugin_id=request.plugin_id,
            plugin_version=request.plugin_version,
            status=StageStatus.FAILED,
            started_at=started_at,
            finished_at=datetime.now(timezone.utc),
            error=StageError(
                code=ErrorCode.DEPENDENCY_MISSING,
                message="intentional reported failure",
                retryable=False,
            ),
        )
        _atomic_json(result_path, result)
        return 10

    delay_value = request.config.get("delay_seconds", 0.0)
    if not isinstance(delay_value, (int, float)) or isinstance(delay_value, bool):
        print("delay_seconds must be numeric", file=sys.stderr)
        return 2
    finish_wait_at = time.monotonic() + max(0.0, float(delay_value))
    cancellation_file = Path(request.cancellation_file or "")
    while time.monotonic() < finish_wait_at:
        if cancellation_file.is_file():
            _atomic_json(result_path, _cancelled_result(request, started_at))
            return 0
        time.sleep(0.01)

    if cancellation_file.is_file():
        _atomic_json(result_path, _cancelled_result(request, started_at))
        return 0

    if mode not in {"success", "bad_hash", "undeclared_file"}:
        print(f"unsupported probe mode: {mode}", file=sys.stderr)
        return 2
    _atomic_json(result_path, _successful_result(request, started_at, mode))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-json", type=Path, required=True)
    parser.add_argument("--result-json", type=Path, required=True)
    arguments = parser.parse_args()
    return run(arguments.request_json, arguments.result_json)


if __name__ == "__main__":
    raise SystemExit(main())
