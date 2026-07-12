"""Freeze identical per-scene keyframes and holdouts for every candidate."""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field


PROTOCOL_VERSION = "p1-static-video-v1"
MANIFEST_VERSION = "benchmark-dataset/v1"


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class VideoMetadata(StrictModel):
    codec: str
    width: int = Field(gt=0)
    height: int = Field(gt=0)
    pixel_format: str
    average_frame_rate: str
    duration_seconds: float = Field(gt=0)
    source_frame_count: int = Field(gt=0)


class SourceVideo(StrictModel):
    file_name: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    size_bytes: int = Field(gt=0)
    metadata: VideoMetadata


class FrameQC(StrictModel):
    laplacian_variance: float = Field(ge=0)
    mean_luma: float = Field(ge=0, le=1)
    luma_stddev: float = Field(ge=0, le=1)
    previous_frame_mad: float | None = Field(default=None, ge=0, le=1)


class PreparedFrame(StrictModel):
    frame_id: str
    image_path: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    sample_index: int = Field(ge=0)
    nominal_timestamp_seconds: float = Field(ge=0)
    split: Literal["train", "holdout"]
    qc: FrameQC


class PreparedScene(StrictModel):
    scene_id: str
    source: SourceVideo
    frames: list[PreparedFrame] = Field(min_length=3)


class ToolFingerprint(StrictModel):
    executable: str
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    version_line: str


class SamplingConfig(StrictModel):
    frames_per_second: float = Field(gt=0)
    holdout_stride: int = Field(ge=3)
    holdout_offset: int = Field(ge=0)
    image_format: Literal["png"] = "png"
    qc_is_advisory_only: Literal[True] = True


class BenchmarkDatasetManifest(StrictModel):
    schema_version: Literal["benchmark-dataset/v1"] = MANIFEST_VERSION
    protocol_version: Literal["p1-static-video-v1"] = PROTOCOL_VERSION
    dataset_id: str = Field(pattern=r"^sha256:[0-9a-f]{64}$")
    created_at: datetime
    input_root: str
    ffmpeg: ToolFingerprint
    sampling: SamplingConfig
    scenes: list[PreparedScene] = Field(min_length=1)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _run_json(command: list[str]) -> dict:
    result = subprocess.run(command, check=True, capture_output=True, text=True, encoding="utf-8")
    return json.loads(result.stdout)


def _video_metadata(ffprobe: str, video: Path) -> VideoMetadata:
    payload = _run_json(
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height,pix_fmt,avg_frame_rate,nb_frames,duration",
            "-of",
            "json",
            str(video),
        ]
    )
    streams = payload.get("streams", [])
    if len(streams) != 1:
        raise ValueError(f"expected exactly one primary video stream in {video}")
    stream = streams[0]
    return VideoMetadata(
        codec=stream["codec_name"],
        width=int(stream["width"]),
        height=int(stream["height"]),
        pixel_format=stream["pix_fmt"],
        average_frame_rate=stream["avg_frame_rate"],
        duration_seconds=float(stream["duration"]),
        source_frame_count=int(stream["nb_frames"]),
    )


def _safe_scene_id(stem: str) -> str:
    scene_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", stem).strip("-.")
    if not scene_id:
        raise ValueError(f"cannot derive scene id from {stem!r}")
    return scene_id


def frame_split(sample_index: int, *, holdout_stride: int, holdout_offset: int) -> Literal["train", "holdout"]:
    if holdout_stride < 3:
        raise ValueError("holdout_stride must be at least 3")
    if not 0 <= holdout_offset < holdout_stride:
        raise ValueError("holdout_offset must be in [0, holdout_stride)")
    return "holdout" if sample_index % holdout_stride == holdout_offset else "train"


def _qc(image_path: Path, previous_small: np.ndarray | None) -> tuple[FrameQC, np.ndarray]:
    with Image.open(image_path) as image:
        grayscale = image.convert("L")
        grayscale.thumbnail((640, 640), Image.Resampling.BILINEAR)
        pixels = np.asarray(grayscale, dtype=np.float32) / 255.0
        small_image = grayscale.resize((160, 90), Image.Resampling.BILINEAR)
        small = np.asarray(small_image, dtype=np.float32) / 255.0
    center = pixels[1:-1, 1:-1]
    laplacian = (
        pixels[:-2, 1:-1]
        + pixels[2:, 1:-1]
        + pixels[1:-1, :-2]
        + pixels[1:-1, 2:]
        - 4.0 * center
    )
    previous_mad = None if previous_small is None else float(np.mean(np.abs(small - previous_small)))
    return (
        FrameQC(
            laplacian_variance=float(np.var(laplacian)),
            mean_luma=float(np.mean(pixels)),
            luma_stddev=float(np.std(pixels)),
            previous_frame_mad=previous_mad,
        ),
        small,
    )


def _tool_fingerprint(executable: str) -> ToolFingerprint:
    resolved = shutil.which(executable)
    if not resolved:
        raise FileNotFoundError(f"required executable is not available: {executable}")
    result = subprocess.run([resolved, "-version"], check=True, capture_output=True, text=True, encoding="utf-8")
    first_line = result.stdout.splitlines()[0]
    return ToolFingerprint(executable=str(Path(resolved).resolve()), sha256=sha256_file(Path(resolved)), version_line=first_line)


def _dataset_id(ffmpeg: ToolFingerprint, sampling: SamplingConfig, scenes: list[PreparedScene]) -> str:
    identity = {
        "protocol_version": PROTOCOL_VERSION,
        "ffmpeg_sha256": ffmpeg.sha256,
        "sampling": sampling.model_dump(mode="json"),
        "scenes": [
            {
                "scene_id": scene.scene_id,
                "source_sha256": scene.source.sha256,
                "frames": [(frame.frame_id, frame.sha256, frame.split) for frame in scene.frames],
            }
            for scene in scenes
        ],
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def prepare_dataset(
    input_root: Path,
    output_root: Path,
    *,
    frames_per_second: float = 15.0,
    holdout_stride: int = 8,
    holdout_offset: int = 4,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
) -> BenchmarkDatasetManifest:
    """Extract a frozen, hash-addressed benchmark dataset from independent videos."""

    input_root = input_root.resolve()
    output_root = output_root.resolve()
    videos = sorted(input_root.glob("*.mp4"))
    if not videos:
        raise FileNotFoundError(f"no .mp4 files found in {input_root}")
    sampling = SamplingConfig(
        frames_per_second=frames_per_second,
        holdout_stride=holdout_stride,
        holdout_offset=holdout_offset,
    )
    # Validate before touching output paths.
    frame_split(0, holdout_stride=holdout_stride, holdout_offset=holdout_offset)
    ffmpeg_fingerprint = _tool_fingerprint(ffmpeg)
    resolved_ffmpeg = ffmpeg_fingerprint.executable
    resolved_ffprobe = shutil.which(ffprobe)
    if not resolved_ffprobe:
        raise FileNotFoundError(f"required executable is not available: {ffprobe}")

    output_root.mkdir(parents=True, exist_ok=True)
    scenes: list[PreparedScene] = []
    seen_ids: set[str] = set()
    for video in videos:
        scene_id = _safe_scene_id(video.stem)
        if scene_id in seen_ids:
            raise ValueError(f"duplicate scene id: {scene_id}")
        seen_ids.add(scene_id)
        scene_dir = output_root / "scenes" / scene_id
        if scene_dir.exists():
            raise FileExistsError(f"refusing to overwrite frozen scene directory: {scene_dir}")
        frames_dir = scene_dir / "frames"
        frames_dir.mkdir(parents=True)
        rate = str(Fraction(str(frames_per_second)).limit_denominator(100_000))
        command = [
            resolved_ffmpeg,
            "-hide_banner",
            "-loglevel",
            "error",
            "-nostdin",
            "-i",
            str(video),
            "-map",
            "0:v:0",
            "-vf",
            f"fps={rate}",
            "-fps_mode",
            "vfr",
            "-map_metadata",
            "-1",
            "-start_number",
            "0",
            "-compression_level",
            "9",
            str(frames_dir / "frame_%06d.png"),
        ]
        subprocess.run(command, check=True)
        images = sorted(frames_dir.glob("frame_*.png"))
        if len(images) < 3:
            raise RuntimeError(f"sampling produced fewer than 3 frames for {video}")
        frames: list[PreparedFrame] = []
        previous_small: np.ndarray | None = None
        for index, image_path in enumerate(images):
            qc, previous_small = _qc(image_path, previous_small)
            relative = image_path.relative_to(output_root).as_posix()
            frames.append(
                PreparedFrame(
                    frame_id=f"{scene_id}:{index:06d}",
                    image_path=relative,
                    sha256=sha256_file(image_path),
                    sample_index=index,
                    nominal_timestamp_seconds=index / frames_per_second,
                    split=frame_split(index, holdout_stride=holdout_stride, holdout_offset=holdout_offset),
                    qc=qc,
                )
            )
        source = SourceVideo(
            file_name=video.name,
            sha256=sha256_file(video),
            size_bytes=video.stat().st_size,
            metadata=_video_metadata(str(resolved_ffprobe), video),
        )
        scenes.append(PreparedScene(scene_id=scene_id, source=source, frames=frames))

    manifest = BenchmarkDatasetManifest(
        dataset_id=_dataset_id(ffmpeg_fingerprint, sampling, scenes),
        created_at=datetime.now(timezone.utc),
        input_root=str(input_root),
        ffmpeg=ffmpeg_fingerprint,
        sampling=sampling,
        scenes=scenes,
    )
    manifest_path = output_root / "dataset.manifest.json"
    manifest_path.write_text(manifest.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return manifest
