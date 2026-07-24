from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import pytest

from apps.desktop.pipeline import (
    PipelineController,
    RuntimePaths,
    WorkerStageError,
)
from apps.desktop.project_session import ProjectSession
from apps.desktop.project_store import ProjectStore
from apps.desktop.sampling import discover_ffprobe
from apps.desktop.video_import import VideoImportSession
from packages.native_paths import native_tool_path
from packages.plugin_sdk import ExecutionProfile, StageKind, StageRequest
from workers.recon_colmap import __main__ as colmap_worker


@pytest.fixture(scope="module")
def short_video(tmp_path_factory: pytest.TempPathFactory) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        pytest.skip("FFmpeg is unavailable")
    output = tmp_path_factory.mktemp("short-video") / "short.mp4"
    completed = subprocess.run(
        [
            ffmpeg,
            "-v",
            "error",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "testsrc2=size=160x96:rate=12:duration=1",
            "-pix_fmt",
            "yuv420p",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if completed.returncode:
        pytest.skip(f"FFmpeg could not create the short fixture: {completed.stderr}")
    return output


def test_native_tool_path_supports_windows_long_paths(tmp_path: Path) -> None:
    candidate = tmp_path / ("long-" * 30) / "database.db"
    adapted = native_tool_path(candidate)

    if os.name == "nt":
        assert adapted.startswith("\\\\?\\")
        assert adapted.endswith("database.db")
    else:
        assert adapted == str(candidate.resolve())


def test_colmap_worker_adapts_attempt_paths_before_native_execution(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    executable = tmp_path / "colmap.exe"
    executable.write_bytes(b"test executable")
    executable_hash = hashlib.sha256(executable.read_bytes()).hexdigest()
    images = tmp_path / "images"
    images.mkdir()
    for index in range(3):
        (images / f"{index}.png").write_bytes(b"image")
    attempt = tmp_path / ("deep-attempt-" * 12)
    attempt.mkdir()
    request = StageRequest(
        run_id="run-long-path",
        stage_id="colmap",
        stage_kind=StageKind.RECONSTRUCTION,
        plugin_id="recon.colmap",
        plugin_version="3.13.0",
        profile=ExecutionProfile.PRODUCTION,
        config={
            "config_version": "recon-colmap/v1",
            "colmap_executable": str(executable),
            "colmap_executable_sha256": executable_hash,
            "images_path": str(images),
            "expected_image_count": 3,
            "camera_model": "SIMPLE_RADIAL",
            "use_gpu": False,
            "minimum_registered_ratio": 0.9,
            "maximum_reprojection_error_px": 2.0,
            "maximum_step_over_median": 4.0,
        },
        attempt_id="attempt-long-path",
        attempt_dir=str(attempt),
        cancellation_file=str(attempt / "cancel.json"),
    )
    monkeypatch.setattr(
        colmap_worker, "EXPECTED_WINDOWS_CUDA_EXE_SHA256", executable_hash
    )
    captured: list[list[str]] = []

    def capture(command: list[str], _log_path: Path):
        captured.append(command)
        raise RuntimeError("intentional command capture")

    monkeypatch.setattr(colmap_worker, "_run_command", capture)
    colmap_worker._run(
        request, attempt / "result.worker.json", datetime.now(timezone.utc)
    )

    command = captured[0]
    database = command[command.index("--database_path") + 1]
    image_path = command[command.index("--image_path") + 1]
    assert database == native_tool_path(
        attempt / "work" / "colmap" / "database.db"
    )
    assert image_path == native_tool_path(images)
    if os.name == "nt":
        assert database.startswith("\\\\?\\")


def test_short_video_ingest_keeps_run_paths_and_identity_consistent(
    short_video: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    runtime = RuntimePaths.discover()
    import_session = VideoImportSession(
        short_video,
        runtime.ffmpeg,
        discover_ffprobe(runtime.ffmpeg),
        profile="preview",
    )
    try:
        import_session.configure(
            "target_count",
            6,
            1.0,
            "seconds",
            0,
            import_session.probe.total_frames - 1,
            "preview",
        )
        analyzed = import_session.analyze()
        assert analyzed["analysis_status"] == "complete"
        assert analyzed["selected_frame_count"] == 6

        store = ProjectStore(tmp_path / "metadata")
        library = tmp_path / ("long-library-" * 8)
        project = store.create("video-a", library)
        other = store.create("video-b", library)
        controller = PipelineController(store, tmp_path / "legacy-artifacts", runtime)
        committed = controller.commit_video_import(
            project.project_id,
            short_video,
            "preview",
            import_session.snapshot(),
        )
    finally:
        import_session.cancel()

    project_paths = store.paths(committed)
    other_paths = store.paths(other)
    thumbnails = [
        Path(record["thumbnail_path"])
        for record in committed.sampling["timeline"]
        if record.get("thumbnail_path")
    ]
    assert thumbnails
    assert all(path.is_file() and project_paths.contains(path) for path in thumbnails)
    assert not any(other_paths.contains(path) for path in thumbnails)

    session = ProjectSession()
    session.switch(committed.project_id)
    generation = session.switch(committed.project_id)
    run_id = controller.new_run_id(committed.project_id)
    session.begin_run(committed.project_id, run_id)
    observed_frames: list[Path] = []

    def stop_after_ingest(project, images, _token, _event):
        observed_frames.append(images)
        raise WorkerStageError(
            "intentional stop after real ingest",
            {
                "worker_stage": "colmap",
                "worker_return_code": 10,
                "worker_error_code": "worker_crashed",
            },
        )

    monkeypatch.setattr(controller, "_reconstruct", stop_after_ingest)
    events: list[tuple[str, str, dict[str, object]]] = []
    completed = controller.run(
        committed.project_id,
        lambda kind, message, payload: events.append((kind, message, payload)),
        run_id=run_id,
        generation=generation,
    )

    run_paths = store.paths(completed).run(run_id)
    assert completed.status == "failed"
    assert observed_frames == [run_paths.frames]
    assert len(list(run_paths.frames.glob("frame_*.png"))) == 6
    assert project_paths.contains(run_paths.frames)
    assert not other_paths.contains(run_paths.frames)
    assert committed.sampling["selection_config_hash"] == analyzed[
        "selection_config_hash"
    ]

    progress = next(
        payload
        for kind, message, payload in events
        if kind == "progress" and message == "ingest completed"
    )
    assert session.accepts(progress)
    assert progress["project_id"] == committed.project_id
    assert progress["run_id"] == run_id
    assert progress["generation"] == generation
    assert progress["stage"] == "ingest"
    assert store.load(committed.project_id).run_id == run_id

    error_log = run_paths.logs / "pipeline-error.json"
    payload = json.loads(error_log.read_text(encoding="utf-8"))
    assert payload["project_id"] == committed.project_id
    assert payload["run_id"] == run_id
    assert payload["generation"] == generation
    assert payload["worker_stage"] == "colmap"
    assert "stop_after_ingest" in payload["traceback"]
