"""MapAnything v1.1.2 Apache fallback with a real COLMAP 3.13 BA gate."""

from __future__ import annotations

import argparse
import gc
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal
from uuid import uuid4

import numpy as np
import torch
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from safetensors.torch import load_file

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
from packages.quality import parse_model_analyzer, read_images_txt
from packages.scene_bundle import CameraTensors


MAPANYTHING_COMMIT = "c845b8f4f6cde0c20aecd87573656c3f69f5b2b0"
DINO_COMMIT = "7764ea0f912e53c92e82eb78a2a1631e92725fc8"
CHECKPOINT_SHA256 = "fa06c0fdccefc5048e072c85935d5789b1e36b307f3859033c17f9dcb9fd5201"
DINO_WEIGHT_SHA256 = "baf8467e50af277596bbbafa06887c177ee899ab46033649c383577d7e9309d3"
COLMAP_SHA256 = "74470eec4cd484b1875fed83e7cefa407e35e93ea05eb294f0bed5a34d7e4e1a"


class FallbackConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    config_version: Literal["recon-mapanything/v1"]
    images_path: str = Field(min_length=1)
    expected_image_count: int = Field(gt=2)
    mapanything_source: str = Field(min_length=1)
    mapanything_checkpoint: str = Field(min_length=1)
    mapanything_config: str = Field(min_length=1)
    dinov2_source: str = Field(min_length=1)
    dinov2_checkpoint: str = Field(min_length=1)
    colmap_executable: str = Field(min_length=1)
    trigger_minimum_registered_ratio: float = Field(default=0.9, ge=0, le=1)
    voxel_fraction: float = Field(default=0.015, gt=0, le=0.1)
    seed: int = Field(default=42, ge=0)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _git_commit(path: Path) -> str:
    return subprocess.check_output(
        ["git", "-C", str(path), "rev-parse", "HEAD"], text=True, encoding="utf-8"
    ).strip()


def _atomic_result(path: Path, result: StageResult) -> None:
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    temporary.write_text(
        json.dumps(result.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), allow_nan=False) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def _failure(request: StageRequest, started: datetime, code: ErrorCode, message: str) -> StageResult:
    return StageResult(
        request_id=request.request_id,
        run_id=request.run_id,
        stage_id=request.stage_id,
        plugin_id=request.plugin_id,
        plugin_version=request.plugin_version,
        status=StageStatus.FAILED,
        started_at=started,
        finished_at=datetime.now(timezone.utc),
        error=StageError(code=code, message=message[:4000], retryable=code in {ErrorCode.CUDA_OOM, ErrorCode.WORKER_CRASHED}),
    )


def _command(command: list[str], log_path: Path, *, allow_failure: bool = False) -> tuple[int, float, str]:
    started = time.perf_counter()
    completed = subprocess.run(
        command,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    elapsed = time.perf_counter() - started
    text = completed.stdout + completed.stderr
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_path.write_text(text, encoding="utf-8")
    if completed.returncode and not allow_failure:
        raise RuntimeError(f"{command[1] if len(command) > 1 else command[0]} failed ({completed.returncode}): {text[-2000:]}")
    return completed.returncode, elapsed, text


def _baseline_colmap(config: FallbackConfig, work: Path, logs: Path) -> dict[str, object]:
    colmap = config.colmap_executable
    database = work / "database.db"
    sparse = work / "sparse"
    sparse.mkdir(parents=True)
    commands = [
        [colmap, "feature_extractor", "--database_path", native_tool_path(database), "--image_path", native_tool_path(config.images_path),
         "--ImageReader.single_camera", "1", "--ImageReader.camera_model", "SIMPLE_RADIAL",
         "--FeatureExtraction.use_gpu", "1", "--FeatureExtraction.gpu_index", "0", "--default_random_seed", "0"],
        [colmap, "exhaustive_matcher", "--database_path", native_tool_path(database), "--FeatureMatching.use_gpu", "1",
         "--FeatureMatching.gpu_index", "0", "--FeatureMatching.guided_matching", "1", "--default_random_seed", "0"],
        [colmap, "mapper", "--database_path", native_tool_path(database), "--image_path", native_tool_path(config.images_path),
         "--output_path", native_tool_path(sparse), "--Mapper.multiple_models", "0", "--Mapper.random_seed", "0",
         "--Mapper.ba_refine_principal_point", "0", "--default_random_seed", "0"],
    ]
    timings: list[float] = []
    mapper_code = 0
    mapper_text = ""
    for index, command in enumerate(commands):
        code, elapsed, text = _command(command, logs / f"baseline_{command[1]}.log", allow_failure=index == 2)
        timings.append(elapsed)
        if index < 2 and code:
            raise RuntimeError(f"baseline {command[1]} failed")
        if index == 2:
            mapper_code, mapper_text = code, text
    if mapper_code and "No images with matches found" not in mapper_text:
        retry_sparse = work / "sparse_retry"
        retry_sparse.mkdir()
        retry_command = list(commands[2])
        retry_command[retry_command.index("--output_path") + 1] = native_tool_path(retry_sparse)
        mapper_code, elapsed, mapper_text = _command(
            retry_command, logs / "baseline_mapper_retry.log", allow_failure=True
        )
        timings.append(elapsed)
        if mapper_code and "No images with matches found" not in mapper_text:
            raise RuntimeError(
                "baseline COLMAP mapper crashed twice; this is not a quality-gate fallback: "
                + mapper_text[-1500:]
            )
        sparse = retry_sparse
    models = sorted(path for path in sparse.iterdir() if path.is_dir())
    if mapper_code or not models:
        return {
            "registered_images": 0,
            "registered_ratio": 0.0,
            "reprojection_error_px": None,
            "mean_track_length": None,
            "points": 0,
            "seconds": sum(timings),
            "failure": mapper_text[-2000:],
        }
    _, analyzer_seconds, analyzer = _command(
        [colmap, "model_analyzer", "--path", native_tool_path(models[0])], logs / "baseline_model_analyzer.log"
    )
    metrics = parse_model_analyzer(analyzer)
    return {
        "registered_images": metrics.registered_images,
        "registered_ratio": metrics.registered_images / config.expected_image_count,
        "reprojection_error_px": metrics.mean_reprojection_error_px,
        "mean_track_length": metrics.mean_track_length,
        "points": metrics.points,
        "seconds": sum(timings) + analyzer_seconds,
        "failure": None,
    }


def _load_model(config: FallbackConfig):
    source = Path(config.mapanything_source).resolve()
    dino_source = Path(config.dinov2_source).resolve()
    if _git_commit(source) != MAPANYTHING_COMMIT or _git_commit(dino_source) != DINO_COMMIT:
        raise RuntimeError("source commit lock mismatch")
    # A portable runtime installs MapAnything from the locked source directory
    # rather than retaining an editable-install pointer to the build machine.
    source_text = str(source)
    if source_text not in sys.path:
        sys.path.insert(0, source_text)
    from mapanything.models import MapAnything
    checkpoint = Path(config.mapanything_checkpoint).resolve()
    dino_checkpoint = Path(config.dinov2_checkpoint).resolve()
    if checkpoint.stat().st_size != 4914062480 or _sha256(checkpoint) != CHECKPOINT_SHA256:
        raise RuntimeError("MapAnything Apache checkpoint lock mismatch")
    if _sha256(dino_checkpoint) != DINO_WEIGHT_SHA256:
        raise RuntimeError("DINOv2 backbone checkpoint lock mismatch")
    model_config = json.loads(Path(config.mapanything_config).read_text(encoding="utf-8"))
    model_config["encoder_config"]["uses_torch_hub"] = False
    original_hub_load = torch.hub.load

    def pinned_hub_load(repo_or_dir, model, *args, **kwargs):
        if repo_or_dir == "facebookresearch/dinov2":
            kwargs["source"] = "local"
            kwargs.pop("force_reload", None)
            return original_hub_load(str(dino_source), model, *args, **kwargs)
        return original_hub_load(repo_or_dir, model, *args, **kwargs)

    torch.hub.load = pinned_hub_load
    model = MapAnything(**model_config)
    state = load_file(str(checkpoint), device="cpu")
    loaded_keys = set(state)
    incompatible = model.load_state_dict(state, strict=False)
    unexpected = list(incompatible.unexpected_keys)
    model_state = model.state_dict()
    uncovered_aliases: list[str] = []
    loaded_storage = {
        model_state[key].untyped_storage().data_ptr()
        for key in loaded_keys
        if key in model_state
    }
    for key in incompatible.missing_keys:
        if model_state[key].untyped_storage().data_ptr() not in loaded_storage:
            uncovered_aliases.append(key)
    if unexpected or uncovered_aliases:
        raise RuntimeError(
            f"checkpoint incompatibility is not shared-module aliasing: unexpected={unexpected[:3]}, uncovered={uncovered_aliases[:3]}"
        )
    del state, model_state, loaded_storage
    gc.collect()
    return model.to("cuda:0").eval(), len(incompatible.missing_keys)


def _install_pycolmap_313_adapter(colmap_export) -> None:
    """Adapt the upstream 3.10 builder to COLMAP's 3.13 Rig/Frame API."""
    import pycolmap

    def build(
        points_3d,
        points_rgb,
        extrinsics,
        intrinsics,
        image_width,
        image_height,
        image_names=None,
        camera_type="PINHOLE",
        skip_point2d=False,
    ):
        num_frames = extrinsics.shape[0]
        image_names = image_names or [f"image_{index + 1}.jpg" for index in range(num_frames)]
        observations = (
            [[] for _ in range(num_frames)]
            if skip_point2d
            else colmap_export.backproject_points_to_frames(
                points_3d, extrinsics, intrinsics, image_width, image_height
            )
        )
        track_counts: dict[int, int] = {}
        for frame_observations in observations:
            for point3d_id, _, _ in frame_observations:
                track_counts[point3d_id] = track_counts.get(point3d_id, 0) + 1
        retained_old_ids = sorted(point_id for point_id, count in track_counts.items() if count >= 2)
        id_map = {old_id: new_id for new_id, old_id in enumerate(retained_old_ids, start=1)}
        reconstruction = pycolmap.Reconstruction()
        for old_id in retained_old_ids:
            point_index = old_id - 1
            reconstruction.add_point3D(points_3d[point_index], pycolmap.Track(), points_rgb[point_index])
        for frame_index in range(num_frames):
            object_id = frame_index + 1
            camera = pycolmap.Camera(
                model=camera_type,
                width=image_width,
                height=image_height,
                params=colmap_export._build_pycolmap_intrinsics(intrinsics[frame_index], camera_type),
                camera_id=object_id,
            )
            reconstruction.add_camera(camera)
            sensor = pycolmap.sensor_t(type=pycolmap.SensorType.CAMERA, id=object_id)
            rig = pycolmap.Rig()
            rig.rig_id = object_id
            rig.add_ref_sensor(sensor)
            reconstruction.add_rig(rig)
            frame = pycolmap.Frame()
            frame.frame_id = object_id
            frame.rig_id = object_id
            frame.add_data_id(pycolmap.data_t(sensor_id=sensor, id=object_id))
            reconstruction.add_frame(frame)
            points2d = []
            for point3d_id, u, v in observations[frame_index]:
                if point3d_id not in id_map:
                    continue
                remapped_id = id_map[point3d_id]
                point2d_index = len(points2d)
                points2d.append(pycolmap.Point2D(np.asarray([u, v]), remapped_id))
                reconstruction.points3D[remapped_id].track.add_element(object_id, point2d_index)
            image = pycolmap.Image(
                image_id=object_id,
                name=image_names[frame_index],
                camera_id=object_id,
                points2D=pycolmap.Point2DList(points2d),
            )
            image.frame_id = object_id
            reconstruction.add_image(image)
            ext = extrinsics[frame_index]
            reconstruction.frames[object_id].set_cam_from_world(
                object_id,
                pycolmap.Rigid3d(pycolmap.Rotation3d(ext[:3, :3]), ext[:3, 3]),
            )
            reconstruction.register_frame(object_id)
        print(
            f"Built COLMAP 3.13 reconstruction: {num_frames} frames, "
            f"{len(retained_old_ids)} multi-view points (from {points_3d.shape[0]}), "
            f"{sum(track_counts[old_id] for old_id in retained_old_ids)} observations"
        )
        return reconstruction

    colmap_export.build_colmap_reconstruction = build


def _infer_and_export(config: FallbackConfig, output: Path) -> tuple[float, float, int]:
    from mapanything.utils import colmap_export
    from mapanything.utils.image import load_images
    from mapanything.utils.misc import seed_everything

    _install_pycolmap_313_adapter(colmap_export)
    seed_everything(config.seed)
    images = sorted(
        path for path in Path(config.images_path).iterdir()
        if path.suffix.lower() in {".png", ".jpg", ".jpeg"}
    )
    views = load_images([str(path) for path in images])
    model, alias_count = _load_model(config)
    torch.cuda.reset_peak_memory_stats(0)
    started = time.perf_counter()
    with torch.inference_mode():
        predictions = model.infer(
            views,
            memory_efficient_inference=True,
            minibatch_size=1,
            use_amp=True,
            amp_dtype="bf16",
            apply_mask=True,
            mask_edges=True,
            apply_confidence_mask=False,
        )
    torch.cuda.synchronize(0)
    inference_seconds = time.perf_counter() - started
    if len(predictions) != config.expected_image_count:
        raise RuntimeError("MapAnything returned the wrong number of cameras")
    if not all(torch.isfinite(item["camera_poses"]).all() and torch.isfinite(item["depth_z"]).all() for item in predictions):
        raise RuntimeError("MapAnything returned NaN or Inf")
    peak = torch.cuda.max_memory_allocated(0) / (1024**3)
    colmap_export.export_predictions_to_colmap(
        outputs=predictions,
        processed_views=views,
        image_names=[path.name for path in images],
        output_dir=str(output),
        voxel_fraction=config.voxel_fraction,
        data_norm_type=model.encoder.data_norm_type,
        save_ply=True,
        save_images=True,
        skip_point2d=False,
    )
    (output / "checkpoint_alias_validation.json").write_text(
        json.dumps({"missing_keys": alias_count, "all_missing_keys_are_loaded_storage_aliases": True}, indent=2) + "\n",
        encoding="utf-8",
    )
    return inference_seconds, peak, alias_count


def _camera_payload(text_model: Path) -> CameraTensors:
    cameras: dict[int, tuple[np.ndarray, tuple[int, int]]] = {}
    with (text_model / "cameras.txt").open("r", encoding="utf-8") as stream:
        for line in stream:
            if not line.strip() or line.startswith("#"):
                continue
            fields = line.split()
            camera_id, model = int(fields[0]), fields[1]
            width, height = int(fields[2]), int(fields[3])
            values = [float(value) for value in fields[4:]]
            if model == "PINHOLE":
                fx, fy, cx, cy = values[:4]
            elif model == "SIMPLE_PINHOLE":
                fx = fy = values[0]
                cx, cy = values[1:3]
            else:
                raise ValueError(f"unsupported fallback camera model: {model}")
            cameras[camera_id] = (np.asarray([[fx, 0, cx], [0, fy, cy], [0, 0, 1]], dtype=np.float32), (width, height))
    poses = read_images_txt(text_model / "images.txt")
    return CameraTensors(
        camtoworlds=np.ascontiguousarray(np.stack([pose.cam2world for pose in poses]).astype(np.float32)),
        intrinsics=np.ascontiguousarray(np.stack([cameras[pose.camera_id][0] for pose in poses])),
        image_sizes=np.ascontiguousarray(np.asarray([cameras[pose.camera_id][1] for pose in poses], dtype=np.int32)),
        camera_ids=np.asarray([pose.image_id for pose in poses], dtype=np.int64),
    )


def _artifact_files(root: Path) -> tuple[ArtifactFile, ...]:
    media = {".json": "application/json", ".txt": "text/plain; charset=utf-8", ".log": "text/plain; charset=utf-8", ".bin": "application/octet-stream", ".ply": "application/vnd.ply", ".png": "image/png"}
    return tuple(
        ArtifactFile(relative_path=path.relative_to(root).as_posix(), sha256=_sha256(path), size_bytes=path.stat().st_size, media_type=media.get(path.suffix.lower(), "application/octet-stream"))
        for path in sorted(root.rglob("*")) if path.is_file()
    )


def _run(request: StageRequest, started: datetime) -> tuple[StageResult, int]:
    try:
        config = FallbackConfig.model_validate(request.config)
        if request.attempt_dir is None or request.attempt_id is None or request.cancellation_file is None:
            raise ValueError("host did not bind attempt paths")
        images = Path(config.images_path).resolve()
        image_count = len([path for path in images.iterdir() if path.suffix.lower() in {".png", ".jpg", ".jpeg"}])
        if image_count != config.expected_image_count:
            raise ValueError(f"expected {config.expected_image_count} images, found {image_count}")
        if _sha256(Path(config.colmap_executable)) != COLMAP_SHA256:
            raise ValueError("COLMAP executable hash mismatch")
    except (ValidationError, ValueError, OSError) as exc:
        return _failure(request, started, ErrorCode.INVALID_REQUEST, str(exc)), 2
    attempt = Path(request.attempt_dir)
    work = attempt / "work"
    output = attempt / "outputs" / f"mapanything-{request.request_id.hex}"
    logs = output / "logs"
    logs.mkdir(parents=True)
    try:
        baseline = _baseline_colmap(config, work / "baseline", logs)
        if float(baseline["registered_ratio"]) >= config.trigger_minimum_registered_ratio:
            return _failure(
                request, started, ErrorCode.POLICY_DENIED,
                f"COLMAP registered ratio {baseline['registered_ratio']:.3f}; fallback correctly not triggered",
            ), 10
        if Path(request.cancellation_file).is_file():
            return _failure(request, started, ErrorCode.CANCELLED, "cancelled before MapAnything inference"), 10
        inference_seconds, peak_vram, alias_count = _infer_and_export(config, output)
        sparse = output / "sparse"
        _, pre_seconds, pre_text = _command(
            [config.colmap_executable, "model_analyzer", "--path", native_tool_path(sparse)], logs / "mapanything_model_analyzer.log"
        )
        pre = parse_model_analyzer(pre_text)
        ba = output / "sparse_ba"
        ba.mkdir()
        ba_code, ba_seconds, ba_text = _command(
            [config.colmap_executable, "bundle_adjuster", "--input_path", native_tool_path(sparse), "--output_path", native_tool_path(ba),
             "--BundleAdjustment.max_num_iterations", "100", "--BundleAdjustment.refine_principal_point", "0",
             "--BundleAdjustment.use_gpu", "0", "--default_random_seed", "0"],
            logs / "bundle_adjuster.log",
        )
        _, post_seconds, post_text = _command(
            [config.colmap_executable, "model_analyzer", "--path", native_tool_path(ba)], logs / "ba_model_analyzer.log"
        )
        post = parse_model_analyzer(post_text)
        text_model = output / "sparse_ba_txt"
        text_model.mkdir()
        _command(
            [config.colmap_executable, "model_converter", "--input_path", native_tool_path(ba), "--output_path", native_tool_path(text_model), "--output_type", "TXT"],
            logs / "ba_model_converter.log",
        )
        cameras = _camera_payload(text_model)
        validation = {
            "scene_bundle_camera_payload": "PASS",
            "camera_convention": "opencv_cam2world",
            "camera_count": int(cameras.camtoworlds.shape[0]),
            "camera_tensors": {key: list(value.shape) for key, value in cameras.to_safetensors().items()},
            "note": "Reconstruction-stage validation covers canonical CameraTensors; no Gaussian trainer is claimed here.",
        }
        (output / "scene_bundle_validation.json").write_text(json.dumps(validation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        ba_executed = ba_code == 0 and "Bundle adjustment report" in ba_text and any(ba.glob("*.bin"))
        def report_number(label: str) -> float:
            match = re.search(rf"{re.escape(label)}\s*:\s*([0-9.eE+-]+)", ba_text)
            if match is None:
                raise RuntimeError(f"BA report is missing {label}")
            return float(match.group(1))

        ba_initial_cost = report_number("Initial cost")
        ba_final_cost = report_number("Final cost")
        ba_iterations = report_number("Iterations")
        metrics_json = {
            "baseline": baseline,
            "mapanything_before_ba": {
                "registered_images": pre.registered_images, "registered_ratio": pre.registered_images / config.expected_image_count,
                "reprojection_error_px": pre.mean_reprojection_error_px, "mean_track_length": pre.mean_track_length, "points": pre.points,
            },
            "after_ba": {
                "registered_images": post.registered_images, "registered_ratio": post.registered_images / config.expected_image_count,
                "reprojection_error_px": post.mean_reprojection_error_px, "mean_track_length": post.mean_track_length, "points": post.points,
            },
            "ba_executed": ba_executed,
            "ba_initial_cost_px": ba_initial_cost,
            "ba_final_cost_px": ba_final_cost,
            "ba_iterations": ba_iterations,
            "inference_seconds": inference_seconds,
            "peak_vram_gib": peak_vram,
            "checkpoint_shared_alias_count": alias_count,
            "analyzer_seconds": pre_seconds + post_seconds,
            "ba_seconds": ba_seconds,
        }
        (output / "metrics.json").write_text(json.dumps(metrics_json, indent=2, sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
        checks = (
            QualityCheck(check_id="fallback.triggered", passed=float(baseline["registered_ratio"]) < config.trigger_minimum_registered_ratio, message="COLMAP quality gate genuinely failed", metrics={"baseline_registered_ratio": float(baseline["registered_ratio"])}),
            QualityCheck(check_id="fallback.mapanything_cameras", passed=post.registered_images == config.expected_image_count, message="MapAnything exported all expected cameras", metrics={"registered_ratio": post.registered_images / config.expected_image_count}),
            QualityCheck(check_id="fallback.bundle_adjustment", passed=ba_executed, message="COLMAP 3.13 bundle_adjuster completed and wrote a model"),
            QualityCheck(check_id="fallback.scene_bundle_camera_payload", passed=cameras.camtoworlds.shape[0] == config.expected_image_count, message="canonical CameraTensors validation passed"),
        )
        if not all(check.passed for check in checks):
            return _failure(request, started, ErrorCode.OUTPUT_VALIDATION_FAILED, f"fallback quality gate failed: {metrics_json}"), 10
        flat_metrics = {
            "baseline_registered_ratio": float(baseline["registered_ratio"]),
            "registered_ratio_after_ba": post.registered_images / config.expected_image_count,
            "reprojection_error_after_ba_px": post.mean_reprojection_error_px,
            "mean_track_length_after_ba": post.mean_track_length,
            "cameras_after_ba": float(post.registered_images), "points_after_ba": float(post.points),
            "inference_seconds": inference_seconds, "ba_seconds": ba_seconds, "peak_vram_gib": peak_vram,
            "ba_initial_cost_px": ba_initial_cost, "ba_final_cost_px": ba_final_cost, "ba_iterations": ba_iterations,
        }
        artifact = ArtifactManifest(
            artifact_id=output.name, artifact_type="mapanything_colmap_ba_reconstruction", format_version="mapanything-v1.1.2+colmap-3.13.0",
            producer_plugin_id=request.plugin_id, producer_plugin_version=request.plugin_version,
            source_request_id=request.request_id, source_attempt_id=request.attempt_id,
            files=_artifact_files(output),
            metadata={"mapanything_commit": MAPANYTHING_COMMIT, "checkpoint_sha256": CHECKPOINT_SHA256, "dinov2_commit": DINO_COMMIT, "dinov2_weight_sha256": DINO_WEIGHT_SHA256},
        )
        quality = QualityReport(passed=True, checks=checks, metrics=flat_metrics)
        return StageResult(
            request_id=request.request_id, run_id=request.run_id, stage_id=request.stage_id,
            plugin_id=request.plugin_id, plugin_version=request.plugin_version,
            status=StageStatus.SUCCEEDED, started_at=started, finished_at=datetime.now(timezone.utc),
            artifacts=(artifact,), quality_report=quality,
        ), 0
    except torch.cuda.OutOfMemoryError as exc:
        return _failure(request, started, ErrorCode.CUDA_OOM, str(exc)), 10
    except Exception as exc:
        return _failure(request, started, ErrorCode.WORKER_CRASHED, f"{type(exc).__name__}: {exc}"), 10


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--request-json", type=Path, required=True)
    parser.add_argument("--result-json", type=Path, required=True)
    args = parser.parse_args()
    started = datetime.now(timezone.utc)
    try:
        request = StageRequest.model_validate_json(args.request_json.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"invalid request: {exc}", file=sys.stderr)
        return 2
    result, code = _run(request, started)
    _atomic_result(args.result_json, result)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
