"""Transient Easy/Pro video-import state for P2.7.

An import session deliberately has no ProjectStore or ArtifactStore reference.
It may probe and analyze a source, but only the explicit Generate transition is
allowed to hand its snapshot to the durable pipeline controller.
"""

from __future__ import annotations

import shutil
import tempfile
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any

from .sampling import (
    SamplingConfig,
    VideoProbe,
    analyze_video,
    estimate_sampling,
    probe_video,
    requested_count,
    selection_config_hash,
)


class VideoImportSession:
    def __init__(self, source: str | Path, ffmpeg: str, ffprobe: str, profile: str = "balanced") -> None:
        self.source = Path(source).resolve()
        self.ffmpeg = ffmpeg
        self.profile = profile
        self.probe: VideoProbe = probe_video(self.source, ffprobe)
        self._root = Path(tempfile.mkdtemp(prefix="gaussian-p27-import-"))
        self._cancelled = threading.Event()
        self._revision = 0
        self.sampling: dict[str, Any] = {}
        self.configure("auto", 0, 1.0, "seconds", 0, self.probe.total_frames - 1, profile)

    @property
    def analysis_dir(self) -> Path:
        return self._root / "analysis"

    @property
    def cancelled(self) -> bool:
        return self._cancelled.is_set()

    def configure(
        self,
        mode: str,
        requested: int,
        interval_value: float,
        interval_unit: str,
        in_frame: int,
        out_frame: int,
        profile: str | None = None,
    ) -> dict[str, Any]:
        if self.cancelled:
            raise RuntimeError("video import was cancelled")
        if profile is not None:
            self.profile = profile
        config = SamplingConfig(
            mode=mode,
            requested_frame_count=requested or None,
            interval_value=interval_value,
            interval_unit=interval_unit,
            profile=self.profile,
            manual_override=mode != "auto",
            in_frame=in_frame,
            out_frame=out_frame,
        )
        estimate = estimate_sampling(self.probe, config)
        self._revision += 1
        self.sampling = {
            **self.probe.to_dict(),
            "source_total_frames": self.probe.total_frames,
            "sampling_mode": mode,
            "requested_frame_count": requested_count(self.probe, config),
            "candidate_frame_count": estimate["estimated_candidate_count"],
            "selected_frame_count": 0,
            "selected_frame_indices": [],
            "rejected_frame_indices": [],
            "selection_config_hash": selection_config_hash(self.probe, config),
            "interval_value": interval_value,
            "interval_unit": interval_unit,
            "manual_override": mode != "auto",
            "profile_label": "Custom" if mode != "auto" else self.profile.title(),
            "timeline": [],
            "warnings": [],
            "analysis_status": "pending",
            "revision": self._revision,
            **estimate,
        }
        return self.snapshot()

    def analyze(self) -> dict[str, Any]:
        revision = self._revision
        snapshot = self.snapshot()
        config = SamplingConfig(
            mode=str(snapshot["sampling_mode"]),
            requested_frame_count=int(snapshot["requested_frame_count"]),
            interval_value=float(snapshot["interval_value"]),
            interval_unit=str(snapshot["interval_unit"]),
            profile=self.profile,
            manual_override=bool(snapshot["manual_override"]),
            in_frame=int(snapshot["in_frame"]),
            out_frame=int(snapshot["out_frame"]),
        )
        result = analyze_video(
            self.source,
            self.probe,
            config,
            self.ffmpeg,
            self.analysis_dir,
            cancelled=lambda: self.cancelled or revision != self._revision,
        )
        if revision != self._revision:
            raise InterruptedError("video import configuration changed")
        self.sampling.update(result)
        self.sampling["revision"] = revision
        return self.snapshot()

    def snapshot(self) -> dict[str, Any]:
        return deepcopy(self.sampling)

    def cancel(self) -> None:
        self._cancelled.set()
        shutil.rmtree(self._root, ignore_errors=True)

