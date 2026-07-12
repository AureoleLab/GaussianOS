"""Shared subprocess entrypoint for locked P1 candidates not installed locally."""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError

from packages.plugin_sdk import ErrorCode, StageError, StageRequest, StageResult, StageStatus


def run_unavailable(plugin_id: str, reason: str) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-json", type=Path, required=True)
    parser.add_argument("--result-json", type=Path, required=True)
    args = parser.parse_args()
    started_at = datetime.now(timezone.utc)
    try:
        request = StageRequest.model_validate_json(args.request_json.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, ValidationError) as exc:
        print(f"invalid request: {exc}", file=sys.stderr)
        return 2
    if request.plugin_id != plugin_id or request.attempt_dir is None:
        print("request plugin or attempt binding mismatch", file=sys.stderr)
        return 2
    try:
        args.result_json.resolve().relative_to(Path(request.attempt_dir).resolve())
    except ValueError:
        print("result path is outside attempt", file=sys.stderr)
        return 2
    result = StageResult(
        request_id=request.request_id,
        run_id=request.run_id,
        stage_id=request.stage_id,
        plugin_id=request.plugin_id,
        plugin_version=request.plugin_version,
        status=StageStatus.FAILED,
        started_at=started_at,
        finished_at=datetime.now(timezone.utc),
        error=StageError(code=ErrorCode.DEPENDENCY_MISSING, message=reason, retryable=False),
    )
    temporary = args.result_json.with_name(f".{args.result_json.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            json.dump(result.model_dump(mode="json"), stream, sort_keys=True, separators=(",", ":"))
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, args.result_json)
    finally:
        temporary.unlink(missing_ok=True)
    return 10
