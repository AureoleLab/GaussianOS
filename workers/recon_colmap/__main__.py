"""Version-locked COLMAP 3.13.0 sparse reconstruction worker."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

import numpy as np
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from packages.exportkit import write_pointcloud_ply
from packages.native_paths import native_tool_path
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
from packages.quality import camera_trajectory_continuity, parse_model_analyzer, read_images_txt
from packages.scene_bundle import PointCloudTensors


EXPECTED_COLMAP_VERSION = "3.13.0"
EXPECTED_COLMAP_COMMIT = "0b31f98133b470eae62811b557dc2bcff1e4f9a5"
EXPECTED_WINDOWS_CUDA_EXE_SHA256 = "74470eec4cd484b1875fed83e7cefa407e35e93ea05eb294f0bed5a34d7e4e1a"


class ColmapConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    config_version: Literal["recon-colmap/v1"]
    colmap_executable: str = Field(min_length=1)
    colmap_executable_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    images_path: str = Field(min_length=1)
    expected_image_count: int = Field(gt=2)
    camera_model: Literal["SIMPLE_RADIAL", "OPENCV"] = "SIMPLE_RADIAL"
    use_gpu: bool = True
    minimum_registered_ratio: float = Field(default=0.9, ge=0.0, le=1.0)
    maximum_reprojection_error_px: float = Field(default=2.0, gt=0.0)
    maximum_step_over_median: float = Field(default=4.0, gt=1.0)


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _atomic_result(path: Path, result: StageResult) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    payload = json.dumps(
        result.model_dump(mode="json"),
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    try:
        with temporary.open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(payload + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _failure(
    request: StageRequest,
    started_at: datetime,
    code: ErrorCode,
    message: str,
    *,
    status: StageStatus = StageStatus.FAILED,
    details: dict[str, object] | None = None,
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
            message=message[:4000],
            retryable=code in {ErrorCode.CUDA_OOM, ErrorCode.WORKER_CRASHED},
            details=details or {},
        ),
    )


def _cancelled(request: StageRequest, started_at: datetime) -> StageResult:
    return _failure(
        request,
        started_at,
        ErrorCode.CANCELLED,
        "COLMAP worker observed cancellation",
        status=StageStatus.CANCELLED,
    )


def _run_command(command: list[str], log_path: Path) -> tuple[float, str]:
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    elapsed = time.perf_counter() - started
    combined = completed.stdout + completed.stderr
    log_path.write_text(combined, encoding="utf-8")
    if completed.returncode != 0:
        raise RuntimeError(
            f"command {command[1] if len(command) > 1 else command[0]} failed with "
            f"exit code {completed.returncode}: {combined[-2000:]}"
        )
    return elapsed, combined


def _parse_points3d(path: Path) -> PointCloudTensors:
    positions: list[tuple[float, float, float]] = []
    colors: list[tuple[int, int, int]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip() or line.startswith("#"):
                continue
            fields = line.split()
            if len(fields) < 8:
                raise ValueError("invalid COLMAP points3D.txt line")
            positions.append((float(fields[1]), float(fields[2]), float(fields[3])))
            colors.append((int(fields[4]), int(fields[5]), int(fields[6])))
    if not positions:
        raise ValueError("COLMAP reconstruction contains no sparse points")
    return PointCloudTensors(
        positions=np.asarray(positions, dtype=np.float32),
        colors_rgb=np.asarray(colors, dtype=np.uint8),
    )


def _artifact_files(root: Path) -> tuple[ArtifactFile, ...]:
    media_types = {
        ".json": "application/json",
        ".txt": "text/plain; charset=utf-8",
        ".log": "text/plain; charset=utf-8",
        ".bin": "application/octet-stream",
        ".ply": "application/vnd.ply",
    }
    files: list[ArtifactFile] = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        relative = path.relative_to(root).as_posix()
        files.append(
            ArtifactFile(
                relative_path=relative,
                sha256=_sha256_file(path),
                size_bytes=path.stat().st_size,
                media_type=media_types.get(path.suffix.lower(), "application/octet-stream"),
            )
        )
    return tuple(files)


def _run(request: StageRequest, result_path: Path, started_at: datetime) -> tuple[StageResult, int]:
    try:
        config = ColmapConfig.model_validate(request.config)
    except ValidationError as exc:
        return _failure(request, started_at, ErrorCode.INVALID_REQUEST, f"invalid COLMAP config: {exc}"), 2
    if request.attempt_dir is None or request.attempt_id is None or request.cancellation_file is None:
        return _failure(request, started_at, ErrorCode.INVALID_REQUEST, "host did not bind attempt paths"), 2

    executable = Path(config.colmap_executable).resolve()
    images = Path(config.images_path).resolve()
    if not executable.is_file():
        return _failure(request, started_at, ErrorCode.DEPENDENCY_MISSING, "COLMAP executable is missing"), 10
    actual_executable_hash = _sha256_file(executable)
    if actual_executable_hash != config.colmap_executable_sha256:
        return _failure(request, started_at, ErrorCode.POLICY_DENIED, "COLMAP executable SHA-256 differs from request lock"), 10
    if os.name == "nt" and actual_executable_hash != EXPECTED_WINDOWS_CUDA_EXE_SHA256:
        return _failure(request, started_at, ErrorCode.POLICY_DENIED, "COLMAP Windows CUDA executable is not the P1-approved release artifact"), 10
    image_files = sorted(item for item in images.iterdir() if item.is_file() and item.suffix.lower() in {".png", ".jpg", ".jpeg"}) if images.is_dir() else []
    if len(image_files) != config.expected_image_count:
        return _failure(
            request,
            started_at,
            ErrorCode.INVALID_REQUEST,
            f"expected {config.expected_image_count} images, found {len(image_files)}",
        ), 2

    cancellation_file = Path(request.cancellation_file)
    if cancellation_file.is_file():
        return _cancelled(request, started_at), 0

    artifact_id = f"colmap-{request.request_id.hex}"
    attempt = Path(request.attempt_dir)
    work = attempt / "work" / "colmap"
    output = attempt / "outputs" / artifact_id
    sparse = work / "sparse"
    text_model = output / "model_txt"
    binary_model = output / "model_bin"
    logs = output / "logs"
    for directory in (sparse, text_model, binary_model, logs):
        directory.mkdir(parents=True, exist_ok=False)
    database = work / "database.db"
    gpu = "1" if config.use_gpu else "0"
    timings: dict[str, float] = {}

    commands = {
        "feature_extractor": [
            str(executable), "feature_extractor",
            "--database_path", native_tool_path(database),
            "--image_path", native_tool_path(images),
            "--ImageReader.single_camera", "1",
            "--ImageReader.camera_model", config.camera_model,
            "--default_random_seed", "0",
            "--FeatureExtraction.use_gpu", gpu,
            "--FeatureExtraction.gpu_index", "0",
        ],
        "exhaustive_matcher": [
            str(executable), "exhaustive_matcher",
            "--database_path", native_tool_path(database),
            "--default_random_seed", "0",
            "--FeatureMatching.use_gpu", gpu,
            "--FeatureMatching.gpu_index", "0",
            "--FeatureMatching.guided_matching", "1",
            "--TwoViewGeometry.random_seed", "0",
        ],
        "mapper": [
            str(executable), "mapper",
            "--database_path", native_tool_path(database),
            "--image_path", native_tool_path(images),
            "--output_path", native_tool_path(sparse),
            "--default_random_seed", "0",
            "--Mapper.random_seed", "0",
            "--Mapper.multiple_models", "0",
            "--Mapper.ba_refine_principal_point", "0",
        ],
    }
    try:
        for name, command in commands.items():
            timings[name], _ = _run_command(command, logs / f"{name}.log")
            if cancellation_file.is_file():
                return _cancelled(request, started_at), 0
        model = sparse / "0"
        if not model.is_dir():
            raise RuntimeError("COLMAP mapper did not produce sparse/0")
        analyzer_command = [
            str(executable), "model_analyzer", "--path", native_tool_path(model)
        ]
        timings["model_analyzer"], analyzer_text = _run_command(analyzer_command, logs / "model_analyzer.log")
        converter_command = [
            str(executable), "model_converter",
            "--input_path", native_tool_path(model),
            "--output_path", native_tool_path(text_model),
            "--output_type", "TXT",
        ]
        timings["model_converter"] , _ = _run_command(converter_command, logs / "model_converter.log")
        for source in model.iterdir():
            if source.is_file():
                shutil.copy2(source, binary_model / source.name)
    except (OSError, RuntimeError, ValueError) as exc:
        message = str(exc)
        code = ErrorCode.CUDA_OOM if "out of memory" in message.casefold() else ErrorCode.WORKER_CRASHED
        return _failure(request, started_at, code, message), 10

    try:
        metrics = parse_model_analyzer(analyzer_text)
        poses = read_images_txt(text_model / "images.txt")
        continuity = camera_trajectory_continuity(np.stack([pose.cam2world for pose in poses]))
        pointcloud = _parse_points3d(text_model / "points3D.txt")
        write_pointcloud_ply(output / "scene.pointcloud.ply", pointcloud)
    except (OSError, ValueError) as exc:
        return _failure(request, started_at, ErrorCode.OUTPUT_VALIDATION_FAILED, str(exc)), 10

    registered_ratio = metrics.registered_images / config.expected_image_count
    checks = (
        QualityCheck(
            check_id="reconstruction.registered_ratio",
            passed=registered_ratio >= config.minimum_registered_ratio,
            message=f"{metrics.registered_images}/{config.expected_image_count} images registered",
            metrics={"registered_ratio": registered_ratio},
        ),
        QualityCheck(
            check_id="reconstruction.reprojection_error",
            passed=metrics.mean_reprojection_error_px <= config.maximum_reprojection_error_px,
            message="mean COLMAP reprojection error",
            metrics={"reprojection_error_px": metrics.mean_reprojection_error_px},
        ),
        QualityCheck(
            check_id="reconstruction.trajectory_continuity",
            passed=continuity.max_step_over_median <= config.maximum_step_over_median,
            message="maximum adjacent translation step normalized by the median",
            metrics={"max_step_over_median": continuity.max_step_over_median},
        ),
    )
    passed = all(check.passed for check in checks)
    metrics_payload = {
        "registered_frames": metrics.registered_frames,
        "registered_images": metrics.registered_images,
        "registered_frame_ratio": registered_ratio,
        "points": metrics.points,
        "observations": metrics.observations,
        "mean_track_length": metrics.mean_track_length,
        "mean_reprojection_error_px": metrics.mean_reprojection_error_px,
        "trajectory_median_step_scene_units": continuity.median_step,
        "trajectory_max_step_over_median": continuity.max_step_over_median,
        "trajectory_p95_turn_degrees": continuity.p95_turn_degrees,
        "trajectory_max_turn_degrees": continuity.max_turn_degrees,
        "feature_extractor_seconds": timings["feature_extractor"],
        "matching_seconds": timings["exhaustive_matcher"],
        "mapping_seconds": timings["mapper"],
        "total_algorithm_seconds": sum(timings.values()),
    }
    (output / "metrics.json").write_text(
        json.dumps(metrics_payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if not passed:
        return _failure(
            request,
            started_at,
            ErrorCode.OUTPUT_VALIDATION_FAILED,
            "COLMAP reconstruction failed a required quality gate",
            details={"metrics": metrics_payload},
        ), 10

    artifact = ArtifactManifest(
        artifact_id=artifact_id,
        artifact_type="colmap_sparse_reconstruction",
        format_version="colmap-3.13.0+gf-v1",
        producer_plugin_id=request.plugin_id,
        producer_plugin_version=request.plugin_version,
        source_request_id=request.request_id,
        source_attempt_id=request.attempt_id,
        files=_artifact_files(output),
        metadata={
            "colmap_version": EXPECTED_COLMAP_VERSION,
            "colmap_commit": EXPECTED_COLMAP_COMMIT,
            "colmap_executable_sha256": actual_executable_hash,
            "camera_model": config.camera_model,
            "camera_convention_after_text_conversion": "opencv_world2camera",
            "dataset_image_count": config.expected_image_count,
        },
    )
    quality = QualityReport(passed=True, checks=checks, metrics=metrics_payload)
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
    ), 0


def main() -> int:
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
    if request.attempt_dir is None:
        print("request has no attempt directory", file=sys.stderr)
        return 2
    try:
        args.result_json.resolve().relative_to(Path(request.attempt_dir).resolve())
    except ValueError:
        print("result path is outside attempt directory", file=sys.stderr)
        return 2
    result, exit_code = _run(request, args.result_json, started_at)
    _atomic_result(args.result_json, result)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
