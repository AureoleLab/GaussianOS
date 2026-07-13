from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFilter

from apps.desktop.project_store import ProjectStore, StageState
from apps.desktop.pipeline import PipelineController
from apps.desktop.sampling import (
    FrameScore,
    SamplingConfig,
    VideoProbe,
    analyze_video,
    extract_selected_frames,
    probe_video,
    select_frames,
)
from apps.desktop.video_import import VideoImportSession


def _scores(count: int = 150) -> list[FrameScore]:
    result = []
    for index in range(count):
        descriptor = np.asarray(
            [np.sin(index * 0.071 + offset) * 0.4 + 0.5 for offset in np.linspace(0, 2, 144)],
            dtype=np.float32,
        )
        result.append(FrameScore(index, index / 30.0, 1.0 + (index % 7) * 0.02, 0.5, 0.0, 0.08 + (index % 5) * 0.005, 0.04, descriptor))
    return result


@pytest.mark.parametrize("target", [15, 30, 60, 150])
def test_target_count_selects_requested_count_from_150_with_candidate_pool(target: int) -> None:
    probe = VideoProbe(150, 5.0, 30.0, 1920, 1080)
    selected, candidates, goal, requested, warnings = select_frames(
        _scores(), probe, SamplingConfig(mode="target_count", requested_frame_count=target, manual_override=True)
    )
    assert requested == target
    assert len(selected) == target
    assert len(candidates) == min(150, int(np.ceil(target * 2.5)))
    assert goal == min(150, int(np.ceil(target * 2.5)))
    assert not warnings


def test_all_sampling_modes_and_time_coverage_are_deterministic() -> None:
    probe = VideoProbe(150, 5.0, 30.0, 1920, 1080)
    target = SamplingConfig(mode="target_count", requested_frame_count=30, manual_override=True)
    first = select_frames(_scores(), probe, target)[0]
    second = select_frames(_scores(), probe, target)[0]
    assert first == second
    assert first[0] < 6 and first[-1] > 143
    assert max(np.diff(first)) <= 10

    auto = select_frames(_scores(), probe, SamplingConfig(mode="auto", profile="balanced"))[0]
    interval = select_frames(_scores(), probe, SamplingConfig(mode="interval", interval_value=10, interval_unit="frames", manual_override=True))[0]
    interval_seconds = select_frames(_scores(), probe, SamplingConfig(mode="interval", interval_value=0.5, interval_unit="seconds", manual_override=True))[0]
    all_frames = select_frames(_scores(), probe, SamplingConfig(mode="all_frames", manual_override=True))[0]
    assert 24 <= len(auto) <= 38
    assert len(interval) == 15
    assert len(interval_seconds) == 10
    assert all_frames == list(range(150))


def test_blur_and_duplicate_frames_are_rejected_without_silent_quality_fill() -> None:
    frames = _scores()
    for item in frames[30:]:
        item.sharpness = 1e-8
    frames[12].difference = 0.0001
    probe = VideoProbe(150, 5.0, 30.0, 1920, 1080)
    selected, _, _, requested, warnings = select_frames(
        frames, probe, SamplingConfig(mode="target_count", requested_frame_count=60, manual_override=True)
    )
    assert requested == 60
    assert len(selected) < requested
    assert all(index < 30 for index in selected)
    assert 12 not in selected
    assert any("silently restored" in warning for warning in warnings)


def test_requested_count_cannot_exceed_source_total() -> None:
    with pytest.raises(ValueError, match="exceeds source total"):
        select_frames(
            _scores(), VideoProbe(150, 5.0, 30.0, 1920, 1080),
            SamplingConfig(mode="target_count", requested_frame_count=151, manual_override=True),
        )


def test_sampling_configuration_survives_project_store_restart(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "projects")
    project = store.create("sampling", tmp_path / "work")
    project.sampling = {
        "source_total_frames": 150,
        "sampling_mode": "target_count",
        "requested_frame_count": 60,
        "candidate_frame_count": 150,
        "selected_frame_count": 58,
        "selected_frame_indices": list(range(58)),
        "rejected_frame_indices": list(range(58, 150)),
        "selection_config_hash": "a" * 64,
    }
    store.save(project)
    restored = ProjectStore(tmp_path / "projects").load(project.project_id)
    assert restored.sampling == project.sampling


def test_controller_custom_sampling_persists_and_rejects_more_than_source(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "projects")
    project = store.create("controller sampling", tmp_path / "work")
    project.input_kind = "video"; project.input_path = str(tmp_path / "source.mp4"); project.status = "ready"
    project.sampling = {
        "source_total_frames": 150, "duration_seconds": 5.0, "fps": 30.0,
        "width": 1920, "height": 1080, "sampling_mode": "auto",
        "requested_frame_count": 30, "selection_config_hash": "0" * 64,
    }
    store.save(project)
    controller = PipelineController(store, tmp_path / "artifacts")
    updated = controller.set_sampling_config(project.project_id, "target_count", 60, 1.0, "seconds")
    assert updated.sampling["profile_label"] == "Custom"
    assert updated.sampling["requested_frame_count"] == 60
    assert updated.sampling["candidate_frame_count"] == 150
    restored = ProjectStore(tmp_path / "projects").load(project.project_id)
    assert restored.sampling["selection_config_hash"] == updated.sampling["selection_config_hash"]
    with pytest.raises(ValueError, match="exceeds source total"):
        controller.set_sampling_config(project.project_id, "target_count", 151, 1.0, "seconds")


def test_sampling_change_marks_every_downstream_artifact_stale(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "projects")
    project = store.create("stale", tmp_path / "work")
    project.input_kind = "video"; project.input_path = str(tmp_path / "source.mp4"); project.status = "succeeded"
    project.sampling = {
        "source_total_frames": 154, "duration_seconds": 2.57, "fps": 60.0,
        "width": 1920, "height": 1080, "sampling_mode": "target_count",
        "requested_frame_count": 60, "interval_value": 1.0, "interval_unit": "seconds",
        "manual_override": True,
    }
    for name in ("ingest", "colmap", "train", "validate", "export"):
        project.stages[name] = StageState(status="succeeded", artifact_paths=[str(tmp_path / name)])
    store.save(project)
    controller = PipelineController(store, tmp_path / "artifacts")
    updated = controller.set_sampling_config(project.project_id, "target_count", 45, 1.0, "seconds", 5, 120)
    assert updated.sampling["camera_mapping_stale"] is True
    assert updated.sampling["trimmed_frame_count"] == 116
    assert all(state.status == "stale" for state in updated.stages.values())
    assert updated.stages["export"].artifact_paths == [str(tmp_path / "export")]


def test_profile_change_preserves_trimmed_range(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path / "projects")
    project = store.create("trim profile", tmp_path / "work")
    project.input_kind = "video"; project.input_path = str(tmp_path / "source.mp4"); project.status = "ready"
    project.sampling = {
        "source_total_frames": 154, "duration_seconds": 2.57, "fps": 60.0,
        "width": 1920, "height": 1080, "sampling_mode": "auto",
        "requested_frame_count": 24, "interval_value": 1.0, "interval_unit": "seconds",
        "manual_override": False, "in_frame": 10, "out_frame": 109,
    }
    store.save(project)
    updated = PipelineController(store, tmp_path / "artifacts").set_profile(project.project_id, "quality")
    assert updated.sampling["in_frame"] == 10
    assert updated.sampling["out_frame"] == 109
    assert updated.sampling["trimmed_frame_count"] == 100



@pytest.fixture(scope="module")
def synthetic_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("FFmpeg is required for the real 150-frame sampling test")
    root = tmp_path_factory.mktemp("sampling-video")
    frames = root / "frames"; frames.mkdir()
    previous: Image.Image | None = None
    for index in range(150):
        image = Image.new("RGB", (96, 64), (8 + index % 30, 18, 35))
        draw = ImageDraw.Draw(image)
        draw.rectangle((index % 70, 12, index % 70 + 20, 44), fill=(40, 120 + index % 100, 230))
        draw.text((4, 3), f"{index:03d}", fill="white")
        if index in {44, 45, 46}:
            image = image.filter(ImageFilter.GaussianBlur(5))
        if index in {80, 81} and previous is not None:
            image = previous.copy()
        image.save(frames / f"{index:06d}.png")
        previous = image
    video = root / "sample.mp4"
    completed = subprocess.run(
        [ffmpeg, "-v", "error", "-y", "-framerate", "30", "-i", str(frames / "%06d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p", str(video)],
        capture_output=True,
        check=False,
    )
    if completed.returncode:
        pytest.skip(f"test FFmpeg cannot encode H.264: {completed.stderr.decode(errors='replace')}")
    return video


def test_real_150_frame_video_probe_analysis_and_colmap_directory_count(synthetic_video: Path, tmp_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    probe = probe_video(synthetic_video, ffprobe)
    assert probe.total_frames == 150
    assert probe.fps == pytest.approx(30.0)
    result = analyze_video(
        synthetic_video,
        probe,
        SamplingConfig(mode="target_count", requested_frame_count=30, manual_override=True),
        ffmpeg,
        tmp_path / "analysis",
    )
    selected = result["selected_frame_indices"]
    extracted = extract_selected_frames(synthetic_video, selected, probe.total_frames, ffmpeg, tmp_path / "colmap-input")
    assert len(selected) == result["selected_frame_count"]
    assert len(extracted) == result["selected_frame_count"]
    assert len(list((tmp_path / "colmap-input").glob("frame_*.png"))) == result["selected_frame_count"]
    assert [int(path.stem.rsplit("_", 1)[1]) for path in extracted] == selected
    assert result["candidate_frame_count"] >= result["selected_frame_count"] * 2


def test_trimmed_target_uses_source_indices_and_exact_count(synthetic_video: Path, tmp_path: Path) -> None:
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    probe = probe_video(synthetic_video, ffprobe)
    result = analyze_video(
        synthetic_video,
        probe,
        SamplingConfig(mode="target_count", requested_frame_count=60, in_frame=10, out_frame=129),
        ffmpeg,
        tmp_path / "trimmed-analysis",
    )
    assert result["source_total_frames"] == 150
    assert result["trimmed_frame_count"] == 120
    assert result["selected_frame_count"] == 60
    assert min(result["selected_frame_indices"]) >= 10
    assert max(result["selected_frame_indices"]) <= 129
    assert all(10 <= item["index"] <= 129 for item in result["timeline"])


def test_transient_import_cancel_removes_analysis_without_project_state(
    synthetic_video: Path, tmp_path: Path,
) -> None:
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    session = VideoImportSession(synthetic_video, ffmpeg, ffprobe)
    root = session.analysis_dir.parent
    snapshot = session.configure("target_count", 60, 1.0, "seconds", 0, 149, "quality")
    assert snapshot["source_total_frames"] == 150
    assert snapshot["requested_frame_count"] == 60
    assert snapshot["analysis_status"] == "pending"
    session.cancel()
    assert not root.exists()
    assert list(tmp_path.glob("*.json")) == []


def test_generate_commits_analyzed_draft_and_trim_state(
    synthetic_video: Path, tmp_path: Path,
) -> None:
    ffmpeg = shutil.which("ffmpeg") or "ffmpeg"
    ffprobe = shutil.which("ffprobe") or "ffprobe"
    probe = probe_video(synthetic_video, ffprobe)
    analyzed = analyze_video(
        synthetic_video,
        probe,
        SamplingConfig(mode="target_count", requested_frame_count=15, in_frame=5, out_frame=104),
        ffmpeg,
        tmp_path / "draft-analysis",
    )
    store = ProjectStore(tmp_path / "projects")
    project = store.create("draft", tmp_path / "workspace")
    controller = PipelineController(store, tmp_path / "artifacts")
    committed = controller.commit_video_import(project.project_id, synthetic_video, "quality", analyzed)
    restored = store.load(project.project_id)
    assert committed.status == "ready"
    assert restored.profile == "quality"
    assert restored.sampling["in_frame"] == 5
    assert restored.sampling["out_frame"] == 104
    assert restored.sampling["selected_frame_count"] == 15
    assert all(Path(item["thumbnail_path"]).parent == tmp_path / "workspace" / "inputs" / "analysis" for item in restored.sampling["timeline"])
