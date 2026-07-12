"""Small, dependency-light reference metrics for P1 validation.

These functions are reference implementations, not replacements for the
version-locked benchmark renderer or LPIPS model.  Keeping them here makes the
metric conventions testable before a CUDA training environment is available.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np


def _same_float_images(reference: np.ndarray, candidate: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    reference = np.asarray(reference, dtype=np.float64)
    candidate = np.asarray(candidate, dtype=np.float64)
    if reference.shape != candidate.shape:
        raise ValueError(f"image shape mismatch: {reference.shape} != {candidate.shape}")
    if reference.ndim not in (2, 3):
        raise ValueError("images must be HxW or HxWxC")
    if not np.isfinite(reference).all() or not np.isfinite(candidate).all():
        raise ValueError("images contain NaN or Inf")
    return reference, candidate


def peak_signal_to_noise_ratio(
    reference: np.ndarray,
    candidate: np.ndarray,
    *,
    data_range: float = 1.0,
) -> float:
    """Return PSNR in dB for identically shaped linear arrays."""

    reference, candidate = _same_float_images(reference, candidate)
    if not np.isfinite(data_range) or data_range <= 0:
        raise ValueError("data_range must be finite and positive")
    mse = float(np.mean(np.square(reference - candidate)))
    if mse == 0:
        return float("inf")
    return float(10.0 * np.log10((data_range * data_range) / mse))


def structural_similarity(
    reference: np.ndarray,
    candidate: np.ndarray,
    *,
    data_range: float = 1.0,
) -> float:
    """Return global SSIM using the standard luminance/contrast constants.

    The P1 benchmark records this implementation as ``gf-global-ssim-v1``.
    It deliberately does not masquerade as the windowed implementation used by
    scikit-image or a paper-specific evaluation script.
    """

    reference, candidate = _same_float_images(reference, candidate)
    if not np.isfinite(data_range) or data_range <= 0:
        raise ValueError("data_range must be finite and positive")
    c1 = (0.01 * data_range) ** 2
    c2 = (0.03 * data_range) ** 2
    mean_ref = float(np.mean(reference))
    mean_candidate = float(np.mean(candidate))
    var_ref = float(np.mean(np.square(reference - mean_ref)))
    var_candidate = float(np.mean(np.square(candidate - mean_candidate)))
    covariance = float(np.mean((reference - mean_ref) * (candidate - mean_candidate)))
    numerator = (2 * mean_ref * mean_candidate + c1) * (2 * covariance + c2)
    denominator = (mean_ref**2 + mean_candidate**2 + c1) * (var_ref + var_candidate + c2)
    return float(numerator / denominator)


@dataclass(frozen=True)
class CameraContinuity:
    """Scale-normalized trajectory continuity diagnostics."""

    median_step: float
    max_step_over_median: float
    p95_turn_degrees: float
    max_turn_degrees: float


def camera_trajectory_continuity(cam2world: np.ndarray) -> CameraContinuity:
    """Measure translation jumps and angular turns in ordered OpenCV cameras."""

    matrices = np.asarray(cam2world, dtype=np.float64)
    if matrices.ndim != 3 or matrices.shape[1:] != (4, 4) or len(matrices) < 3:
        raise ValueError("cam2world must have shape [N,4,4] with N >= 3")
    if not np.isfinite(matrices).all():
        raise ValueError("camera matrices contain NaN or Inf")
    positions = matrices[:, :3, 3]
    steps = np.linalg.norm(np.diff(positions, axis=0), axis=1)
    nonzero = steps[steps > np.finfo(np.float64).eps]
    median_step = float(np.median(nonzero)) if nonzero.size else 0.0
    max_ratio = float(np.max(steps) / median_step) if median_step else float("inf")

    forward = matrices[:, :3, 2]
    norms = np.linalg.norm(forward, axis=1)
    if np.any(norms <= np.finfo(np.float64).eps):
        raise ValueError("camera forward axis has zero length")
    forward = forward / norms[:, None]
    cosine = np.sum(forward[:-1] * forward[1:], axis=1)
    turns = np.degrees(np.arccos(np.clip(cosine, -1.0, 1.0)))
    return CameraContinuity(
        median_step=median_step,
        max_step_over_median=max_ratio,
        p95_turn_degrees=float(np.percentile(turns, 95)),
        max_turn_degrees=float(np.max(turns)),
    )
