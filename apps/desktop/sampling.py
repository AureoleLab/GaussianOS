"""Deterministic video analysis and quality-aware keyframe selection for P2.6."""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import subprocess
from dataclasses import asdict, dataclass, field
from fractions import Fraction
from pathlib import Path
from typing import Callable, Iterable, Literal

import numpy as np
from PIL import Image


SAMPLING_VERSION = "p2.7-trimmed-selection/v1"
SamplingMode = Literal["auto", "target_count", "interval", "all_frames"]
IntervalUnit = Literal["frames", "seconds"]
PROFILE_RATIOS = {"preview": 0.10, "balanced": 0.20, "quality": 0.40}
PROFILE_MINIMUMS = {"preview": 12, "balanced": 24, "quality": 36}
PROFILE_MAXIMUMS = {"preview": 60, "balanced": 120, "quality": 240}


@dataclass(frozen=True, slots=True)
class VideoProbe:
    total_frames: int
    duration_seconds: float
    fps: float
    width: int
    height: int

    def to_dict(self) -> dict[str, int | float]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class SamplingConfig:
    mode: SamplingMode = "auto"
    requested_frame_count: int | None = None
    interval_value: float = 1.0
    interval_unit: IntervalUnit = "seconds"
    profile: str = "balanced"
    manual_override: bool = False
    in_frame: int = 0
    out_frame: int | None = None

    def __post_init__(self) -> None:
        if self.mode not in {"auto", "target_count", "interval", "all_frames"}:
            raise ValueError(f"unsupported sampling mode: {self.mode}")
        if self.profile not in PROFILE_RATIOS:
            raise ValueError(f"unsupported profile: {self.profile}")
        if self.interval_unit not in {"frames", "seconds"}:
            raise ValueError(f"unsupported interval unit: {self.interval_unit}")
        if self.interval_value <= 0:
            raise ValueError("sampling interval must be positive")
        if self.in_frame < 0:
            raise ValueError("In frame must not be negative")
        if self.out_frame is not None and self.out_frame < self.in_frame:
            raise ValueError("Out frame must not precede In frame")

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(slots=True)
class FrameScore:
    index: int
    timestamp_seconds: float
    sharpness: float
    exposure: float
    clipped_fraction: float
    difference: float
    motion: float
    descriptor: np.ndarray = field(repr=False)
    quality: float = 0.0
    acceptable: bool = True
    rejection_reason: str | None = None
    thumbnail_path: str | None = None

    def record(self, selected: set[int], candidates: set[int]) -> dict[str, object]:
        if self.index in selected:
            reason = None
        elif self.rejection_reason:
            reason = self.rejection_reason
        elif self.index not in candidates:
            reason = "not admitted to candidate pool"
        else:
            reason = "not selected for final time/view coverage"
        return {
            "index": self.index,
            "timestamp_seconds": round(self.timestamp_seconds, 6),
            "sharpness": round(self.sharpness, 8),
            "exposure": round(self.exposure, 6),
            "difference": round(self.difference, 8),
            "motion": round(self.motion, 8),
            "quality": round(self.quality, 8),
            "status": "selected" if self.index in selected else "rejected",
            "candidate": self.index in candidates,
            "reason": reason,
            "thumbnail_path": self.thumbnail_path,
        }


def _fraction(value: str | None) -> float:
    if not value or value in {"0/0", "N/A"}:
        return 0.0
    try:
        return float(Fraction(value))
    except (ValueError, ZeroDivisionError):
        return 0.0


def discover_ffprobe(ffmpeg: str | os.PathLike[str]) -> str:
    ffmpeg_path = Path(ffmpeg)
    if ffmpeg_path.is_file():
        sibling = ffmpeg_path.with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
        if sibling.is_file():
            return str(sibling)
    return shutil.which("ffprobe") or "ffprobe"


def probe_video(source: str | Path, ffprobe: str) -> VideoProbe:
    command = [
        ffprobe,
        "-v", "error",
        "-count_frames",
        "-select_streams", "v:0",
        "-show_entries", "stream=width,height,avg_frame_rate,r_frame_rate,nb_frames,nb_read_frames:format=duration",
        "-of", "json",
        str(Path(source).resolve()),
    ]
    completed = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False)
    if completed.returncode:
        raise RuntimeError(f"ffprobe failed: {completed.stderr[-1000:]}")
    try:
        payload = json.loads(completed.stdout)
        stream = payload["streams"][0]
        duration_value = payload.get("format", {}).get("duration")
        duration = 0.0 if duration_value in {None, "", "N/A"} else float(duration_value)
        fps = _fraction(stream.get("avg_frame_rate")) or _fraction(stream.get("r_frame_rate"))
        declared_counts = (stream.get("nb_read_frames"), stream.get("nb_frames"))
        total = next((int(value) for value in declared_counts if value not in {None, "", "N/A"}), int(round(duration * fps)))
        width, height = int(stream["width"]), int(stream["height"])
    except (KeyError, TypeError, ValueError, IndexError) as exc:
        raise RuntimeError("ffprobe returned incomplete video metadata") from exc
    if total <= 0 or fps <= 0 or width <= 0 or height <= 0:
        raise RuntimeError("video metadata has invalid frame count, FPS, or resolution")
    if duration <= 0:
        duration = total / fps
    return VideoProbe(total, duration, fps, width, height)


def default_auto_count(total_frames: int, profile: str) -> int:
    return min(
        total_frames,
        PROFILE_MAXIMUMS[profile],
        max(PROFILE_MINIMUMS[profile], int(round(total_frames * PROFILE_RATIOS[profile]))),
    )


def frame_range(probe: VideoProbe, config: SamplingConfig) -> tuple[int, int, int]:
    """Return inclusive source In/Out and the number of usable source frames."""
    start = config.in_frame
    end = probe.total_frames - 1 if config.out_frame is None else config.out_frame
    if start >= probe.total_frames or end >= probe.total_frames:
        raise ValueError(
            f"trim range {start}-{end} is outside source total {probe.total_frames}"
        )
    return start, end, end - start + 1


def requested_count(probe: VideoProbe, config: SamplingConfig) -> int:
    _, _, available = frame_range(probe, config)
    if config.mode == "all_frames":
        return available
    if config.mode == "target_count":
        return int(config.requested_frame_count or default_auto_count(available, config.profile))
    if config.mode == "interval":
        step = config.interval_value if config.interval_unit == "frames" else config.interval_value * probe.fps
        return max(1, int(math.ceil(available / max(step, 1.0))))
    return default_auto_count(available, config.profile)


def validate_config(probe: VideoProbe, config: SamplingConfig) -> None:
    _, _, available = frame_range(probe, config)
    requested = requested_count(probe, config)
    if requested > available:
        raise ValueError(f"requested frame count {requested} exceeds source total after trim {available}")
    if config.mode == "target_count" and requested < 1:
        raise ValueError("target frame count must be positive")


def estimate_sampling(probe: VideoProbe, config: SamplingConfig) -> dict[str, object]:
    validate_config(probe, config)
    start, end, available = frame_range(probe, config)
    requested = requested_count(probe, config)
    candidates = available if config.mode == "all_frames" else min(available, max(requested, int(math.ceil(requested * 2.5))))
    risk = ""
    if requested < 12:
        risk = "High reconstruction-failure risk: fewer than 12 views may not provide enough overlap."
    elif requested > max(120, int(available * 0.75)):
        risk = "High compute and redundancy: expect longer COLMAP matching, training, and increased VRAM use."
    elif config.mode == "all_frames":
        risk = "All frames keeps blur and near-duplicates; compute cost and redundancy can grow sharply."
    estimated_minutes = max(0.5, requested * requested / 1800.0 + requested * 0.08)
    estimated_vram_gib = 0.7 + requested * 0.012
    return {
        "estimated_candidate_count": candidates,
        "estimated_selected_count": requested,
        "estimated_minutes": round(estimated_minutes, 1),
        "estimated_vram_gib": round(estimated_vram_gib, 1),
        "in_frame": start,
        "out_frame": end,
        "trimmed_frame_count": available,
        "advisory": risk or "Time coverage and quality filtering are expected to be balanced.",
    }


def selection_config_hash(probe: VideoProbe, config: SamplingConfig) -> str:
    canonical = {
        "version": SAMPLING_VERSION,
        "probe": probe.to_dict(),
        "config": config.to_dict(),
    }
    return hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _normalized(values: np.ndarray) -> np.ndarray:
    if not len(values):
        return values
    low, high = np.percentile(values, (5, 95))
    if high - low < 1e-12:
        return np.ones_like(values) * 0.5
    return np.clip((values - low) / (high - low), 0.0, 1.0)


def classify_frames(frames: list[FrameScore]) -> None:
    sharp = np.asarray([item.sharpness for item in frames], dtype=np.float64)
    differences = np.asarray([item.difference for item in frames], dtype=np.float64)
    sharp_floor = max(1e-5, float(np.percentile(sharp, 12)) * 0.65)
    sharp_score, diff_score = _normalized(sharp), _normalized(differences)
    for position, item in enumerate(frames):
        exposure_score = max(0.0, 1.0 - abs(item.exposure - 0.5) * 2.0 - item.clipped_fraction)
        item.quality = float(0.45 * sharp_score[position] + 0.25 * exposure_score + 0.20 * diff_score[position] + 0.10 * min(item.motion * 8.0, 1.0))
        if item.sharpness < sharp_floor:
            item.acceptable, item.rejection_reason = False, "severe blur"
        elif item.exposure < 0.045 or item.exposure > 0.955 or item.clipped_fraction > 0.72:
            item.acceptable, item.rejection_reason = False, "severe exposure"
        elif position > 0 and item.difference < 0.006:
            item.acceptable, item.rejection_reason = False, "near-duplicate"


def _best_by_time_bins(pool: list[FrameScore], count: int, total_frames: int, selected: list[FrameScore] | None = None) -> list[FrameScore]:
    if count <= 0 or not pool:
        return []
    chosen = list(selected or [])
    chosen_indices = {item.index for item in chosen}
    for bin_index in range(count):
        start = bin_index * total_frames / count
        end = (bin_index + 1) * total_frames / count
        options = [item for item in pool if item.index not in chosen_indices and start <= item.index < end]
        if not options:
            continue
        def rank(item: FrameScore) -> tuple[float, float, int]:
            novelty = min((float(np.mean(np.abs(item.descriptor - prior.descriptor))) for prior in chosen), default=item.difference)
            center_distance = abs(item.index - (start + end) * 0.5) / max(end - start, 1.0)
            return (item.quality + 0.25 * novelty - 0.04 * center_distance, item.difference, -item.index)
        best = max(options, key=rank)
        chosen.append(best); chosen_indices.add(best.index)
    return chosen


def _fill_for_coverage(chosen: list[FrameScore], pool: list[FrameScore], count: int, total_frames: int) -> list[FrameScore]:
    chosen_indices = {item.index for item in chosen}
    while len(chosen) < count:
        remaining = [item for item in pool if item.index not in chosen_indices]
        if not remaining:
            break
        def rank(item: FrameScore) -> tuple[float, float, int]:
            temporal = min((abs(item.index - prior.index) / max(total_frames - 1, 1) for prior in chosen), default=1.0)
            visual = min((float(np.mean(np.abs(item.descriptor - prior.descriptor))) for prior in chosen), default=item.difference)
            return (0.50 * temporal + 0.30 * visual + 0.20 * item.quality, item.quality, -item.index)
        best = max(remaining, key=rank)
        chosen.append(best); chosen_indices.add(best.index)
    return chosen


def select_frames(frames: list[FrameScore], probe: VideoProbe, config: SamplingConfig) -> tuple[list[int], list[int], int, int, list[str]]:
    """Return selected/candidate indices and counts using deterministic coverage."""
    validate_config(probe, config)
    classify_frames(frames)
    warnings: list[str] = []
    if config.mode == "all_frames":
        indices = [item.index for item in frames]
        return indices, indices, probe.total_frames, len(indices), ["All Frames includes blurred and duplicate frames by request."]

    requested = requested_count(probe, config)
    if config.mode == "auto" and frames:
        median_motion = float(np.median([item.motion for item in frames]))
        scene_change = float(np.percentile([item.difference for item in frames], 80))
        complexity_factor = float(np.clip(0.82 + median_motion * 2.0 + scene_change * 1.5, 0.8, 1.25))
        requested = min(probe.total_frames, max(3, int(round(requested * complexity_factor))))

    acceptable = [item for item in frames if item.acceptable]
    candidate_goal = min(probe.total_frames, max(requested, int(math.ceil(requested * 2.5))))
    candidates = _best_by_time_bins(acceptable, candidate_goal, probe.total_frames)
    candidates = _fill_for_coverage(candidates, acceptable, candidate_goal, probe.total_frames)
    candidates = sorted(candidates, key=lambda item: item.index)

    if config.mode == "interval":
        step = max(1, int(round(config.interval_value if config.interval_unit == "frames" else config.interval_value * probe.fps)))
        anchors = list(range(0, probe.total_frames, step))
        chosen: list[FrameScore] = []
        used: set[int] = set()
        radius = max(1, step // 2)
        for anchor in anchors:
            options = [item for item in candidates if item.index not in used and abs(item.index - anchor) <= radius]
            if options:
                best = max(options, key=lambda item: (item.quality - abs(item.index - anchor) / max(step, 1) * 0.1, -item.index))
                chosen.append(best); used.add(best.index)
    else:
        chosen = _best_by_time_bins(candidates, requested, probe.total_frames)
        chosen = _fill_for_coverage(chosen, candidates, requested, probe.total_frames)

    selected = sorted(item.index for item in chosen)
    candidate_indices = [item.index for item in candidates]
    if len(selected) < requested:
        reasons: dict[str, int] = {}
        for item in frames:
            if not item.acceptable:
                reasons[item.rejection_reason or "quality"] = reasons.get(item.rejection_reason or "quality", 0) + 1
        rendered = ", ".join(f"{name}: {count}" for name, count in sorted(reasons.items())) or "insufficient acceptable coverage"
        warnings.append(f"Selected {len(selected)} of requested {requested}; severe frames were not silently restored ({rendered}).")
    return selected, candidate_indices, candidate_goal, requested, warnings


def _read_exact(stream, size: int) -> bytes:
    chunks: list[bytes] = []
    remaining = size
    while remaining:
        chunk = stream.read(remaining)
        if not chunk:
            break
        chunks.append(chunk); remaining -= len(chunk)
    return b"".join(chunks)


def analyze_video(
    source: str | Path,
    probe: VideoProbe,
    config: SamplingConfig,
    ffmpeg: str,
    analysis_dir: str | Path,
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, object]:
    """Decode every source frame at analysis resolution and select keyframes."""
    validate_config(probe, config)
    range_start, range_end, range_count = frame_range(probe, config)
    root = Path(analysis_dir).resolve(); root.mkdir(parents=True, exist_ok=True)
    for old in root.glob("thumb_*.jpg"):
        old.unlink(missing_ok=True)
    analysis_width = min(192, probe.width)
    analysis_height = max(2, int(round(analysis_width * probe.height / probe.width / 2.0)) * 2)
    command = [ffmpeg, "-v", "error", "-i", str(Path(source).resolve()), "-map", "0:v:0", "-vf", f"scale={analysis_width}:{analysis_height}", "-pix_fmt", "rgb24", "-f", "rawvideo", "-"]
    process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if process.stdout is None or process.stderr is None:
        raise RuntimeError("could not open FFmpeg analysis pipes")
    frame_bytes = analysis_width * analysis_height * 3
    timeline_indices = set(np.linspace(range_start, range_end, min(range_count, 240), dtype=np.int64).tolist())
    frames: list[FrameScore] = []
    previous_gray: np.ndarray | None = None
    previous_descriptor: np.ndarray | None = None
    index = 0
    try:
        while True:
            if cancelled and cancelled():
                process.terminate(); raise InterruptedError("video analysis cancelled")
            payload = _read_exact(process.stdout, frame_bytes)
            if not payload:
                break
            if len(payload) != frame_bytes:
                raise RuntimeError("FFmpeg returned a truncated analysis frame")
            rgb = np.frombuffer(payload, dtype=np.uint8).reshape(analysis_height, analysis_width, 3)
            source_index = index
            index += 1
            if source_index < range_start or source_index > range_end:
                continue
            gray = (rgb[..., 0].astype(np.float32) * 0.299 + rgb[..., 1] * 0.587 + rgb[..., 2] * 0.114) / 255.0
            laplacian = -4.0 * gray[1:-1, 1:-1] + gray[:-2, 1:-1] + gray[2:, 1:-1] + gray[1:-1, :-2] + gray[1:-1, 2:]
            sharpness = float(np.var(laplacian))
            exposure = float(np.mean(gray))
            clipped = float(np.mean((gray < 0.02) | (gray > 0.98)))
            difference = 1.0 if previous_gray is None else float(np.mean(np.abs(gray - previous_gray)))
            descriptor_image = Image.fromarray((gray * 255).astype(np.uint8), mode="L").resize((16, 9), Image.Resampling.BILINEAR)
            descriptor = np.asarray(descriptor_image, dtype=np.float32).reshape(-1) / 255.0
            motion = difference if previous_descriptor is None else float(np.mean(np.abs(descriptor - previous_descriptor)))
            thumbnail = None
            if source_index in timeline_indices:
                thumbnail_path = root / f"thumb_{source_index:06d}.jpg"
                Image.fromarray(rgb, mode="RGB").save(thumbnail_path, quality=82)
                thumbnail = str(thumbnail_path)
            frames.append(FrameScore(source_index - range_start, source_index / probe.fps, sharpness, exposure, clipped, difference, motion, descriptor, thumbnail_path=thumbnail))
            previous_gray, previous_descriptor = gray, descriptor
    finally:
        if process.poll() is None:
            process.stdout.close(); process.wait(timeout=30)
    stderr = process.stderr.read().decode(errors="replace")
    if process.returncode:
        raise RuntimeError(f"FFmpeg analysis failed: {stderr[-1000:]}")
    if index != probe.total_frames:
        raise RuntimeError(f"decoded frame count {index} does not match probed source total {probe.total_frames}")

    range_probe = VideoProbe(range_count, range_count / probe.fps, probe.fps, probe.width, probe.height)
    range_config = SamplingConfig(
        mode=config.mode,
        requested_frame_count=config.requested_frame_count,
        interval_value=config.interval_value,
        interval_unit=config.interval_unit,
        profile=config.profile,
        manual_override=config.manual_override,
    )
    selected, candidates, candidate_goal, effective_requested, warnings = select_frames(frames, range_probe, range_config)
    selected_set, candidate_set = set(selected), set(candidates)
    rejected = [item.index for item in frames if item.index not in selected_set]
    timeline = [item.record(selected_set, candidate_set) for item in frames if item.thumbnail_path]
    for item in timeline:
        item["index"] = int(item["index"]) + range_start
    selected = [value + range_start for value in selected]
    candidates = [value + range_start for value in candidates]
    rejected = [value + range_start for value in rejected]
    estimate = estimate_sampling(probe, config)
    if len(selected) < 12:
        warnings.append("Final frame count is below 12; reconstruction may fail from insufficient overlap.")
    return {
        **probe.to_dict(),
        "source_total_frames": probe.total_frames,
        "in_frame": range_start,
        "out_frame": range_end,
        "trimmed_frame_count": range_count,
        "sampling_mode": config.mode,
        "requested_frame_count": effective_requested,
        "candidate_frame_count": len(candidates),
        "candidate_pool_limit": candidate_goal,
        "selected_frame_count": len(selected),
        "selected_frame_indices": selected,
        "rejected_frame_indices": rejected,
        "selection_config_hash": selection_config_hash(probe, config),
        "sampling_version": SAMPLING_VERSION,
        "manual_override": config.manual_override,
        "profile_label": "Custom" if config.manual_override else config.profile.title(),
        "timeline": timeline,
        "warnings": warnings,
        **estimate,
        "analysis_status": "complete",
    }


def extract_selected_frames(source: str | Path, selected_indices: Iterable[int], total_frames: int, ffmpeg: str, destination: str | Path) -> list[Path]:
    selected = sorted(set(int(value) for value in selected_indices))
    if not selected:
        return []
    if selected[0] < 0 or selected[-1] >= total_frames:
        raise ValueError("selected frame index is outside the source video")
    output = Path(destination).resolve(); output.mkdir(parents=True, exist_ok=True)
    for old in (*output.glob("frame_*.png"), *output.glob("selected_*.png")):
        old.unlink(missing_ok=True)
    command = [ffmpeg, "-v", "error", "-y", "-i", str(Path(source).resolve()), "-map", "0:v:0"]
    if selected != list(range(total_frames)):
        filter_path = output.parent / "selection.filter"
        expression = "+".join(f"eq(n\\,{index})" for index in selected)
        filter_path.write_text(f"select={expression}\n", encoding="utf-8")
        command.extend(["-filter_script:v", str(filter_path)])
    command.extend(["-fps_mode", "vfr", "-start_number", "0", str(output / "selected_%06d.png")])
    completed = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True, text=True, check=False)
    if completed.returncode:
        raise RuntimeError(f"FFmpeg selected-frame extraction failed: {completed.stderr[-1000:]}")
    extracted = sorted(output.glob("selected_*.png"))
    if len(extracted) != len(selected):
        raise RuntimeError(f"FFmpeg extracted {len(extracted)} frames, expected {len(selected)}")
    result: list[Path] = []
    for temporary, source_index in zip(extracted, selected, strict=True):
        target = output / f"frame_{source_index:06d}.png"
        temporary.replace(target); result.append(target)
    return result
