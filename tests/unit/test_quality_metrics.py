from __future__ import annotations

import numpy as np
import pytest

from packages.quality import (
    camera_trajectory_continuity,
    peak_signal_to_noise_ratio,
    structural_similarity,
)


def test_identical_images_have_perfect_reference_scores() -> None:
    image = np.linspace(0.0, 1.0, 64, dtype=np.float32).reshape(8, 8)
    assert peak_signal_to_noise_ratio(image, image) == float("inf")
    assert structural_similarity(image, image) == pytest.approx(1.0)


def test_psnr_rejects_shape_mismatch() -> None:
    with pytest.raises(ValueError, match="shape mismatch"):
        peak_signal_to_noise_ratio(np.zeros((2, 2)), np.zeros((2, 3)))


def test_camera_continuity_reports_scale_normalized_jump() -> None:
    cameras = np.repeat(np.eye(4)[None, :, :], 4, axis=0)
    cameras[:, 0, 3] = [0.0, 1.0, 2.0, 12.0]
    result = camera_trajectory_continuity(cameras)
    assert result.median_step == pytest.approx(1.0)
    assert result.max_step_over_median == pytest.approx(10.0)
    assert result.max_turn_degrees == pytest.approx(0.0)
