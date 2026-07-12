from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from packages.quality import parse_model_analyzer, read_images_txt


def test_colmap_world_to_camera_is_converted_to_cam2world(tmp_path: Path) -> None:
    images = tmp_path / "images.txt"
    images.write_text(
        "# image list\n"
        "2 1 0 0 0 3 0 0 7 frame_000002.png\n"
        "\n"
        "1 1 0 0 0 1 2 3 7 frame_000001.png\n"
        "0 0 -1\n",
        encoding="utf-8",
    )
    poses = read_images_txt(images)
    assert [pose.image_name for pose in poses] == ["frame_000001.png", "frame_000002.png"]
    np.testing.assert_allclose(poses[0].cam2world[:3, 3], [-1, -2, -3])
    np.testing.assert_allclose(poses[0].cam2world[:3, :3], np.eye(3))


def test_model_analyzer_metrics_are_strictly_parsed() -> None:
    metrics = parse_model_analyzer(
        "Registered frames: 39\nRegistered images: 39\nPoints: 30077\n"
        "Observations: 144298\nMean track length: 4.797619\n"
        "Mean observations per image: 3699.948718\nMean reprojection error: 0.644962px\n"
    )
    assert metrics.registered_images == 39
    assert metrics.mean_reprojection_error_px == pytest.approx(0.644962)


def test_model_analyzer_missing_metric_is_rejected() -> None:
    with pytest.raises(ValueError, match="registered_frames"):
        parse_model_analyzer("Points: 1")
