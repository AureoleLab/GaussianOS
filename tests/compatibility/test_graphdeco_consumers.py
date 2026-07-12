"""Real consumer tests for exported graphdeco-gs-v1 files.

These tests name the actual consumer used. External CLIs are opt-in so the
default unit suite remains hermetic.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from importlib.metadata import version

import numpy as np
import pytest

from packages.contracts import SphericalHarmonicsSpec
from packages.exportkit import read_gaussian_ply, write_gaussian_ply
from packages.scene_bundle import GaussianTensors


SPLAT_TRANSFORM_NPM_SPEC = "@playcanvas/splat-transform@3.0.0"
BRUSH_VERSION = "brush-cli 0.3.0"


def _sample_gaussians() -> GaussianTensors:
    coefficient_count = 16
    return GaussianTensors(
        means=np.array([[0.0, 0.0, 1.0], [1.0, -2.0, 3.0]], dtype=np.float32),
        log_scales=np.array([[-2.0, -2.1, -2.2], [-1.0, -1.1, -1.2]], dtype=np.float32),
        quats_wxyz=np.array(
            [[1.0, 0.0, 0.0, 0.0], [0.0, 0.0, 1.0, 0.0]], dtype=np.float32
        ),
        opacity_logits=np.array([[0.0], [2.0]], dtype=np.float32),
        sh_coeffs=(
            np.arange(2 * coefficient_count * 3, dtype=np.float32).reshape(
                2, coefficient_count, 3
            )
            / np.float32(100.0)
        ),
    )


@pytest.fixture
def gaussian_ply(tmp_path):
    path = tmp_path / "consumer-test.graphdeco-gs-v1.ply"
    write_gaussian_ply(
        path,
        _sample_gaussians(),
        SphericalHarmonicsSpec(degree=3),
        color_space="linear_srgb",
    )
    return path


def test_exportkit_strict_loader_consumer(gaussian_ply):
    loaded = read_gaussian_ply(gaussian_ply)
    assert loaded.means.shape == (2, 3)
    assert loaded.sh_coeffs.shape == (2, 16, 3)


def test_plyfile_1_1_3_independent_consumer(gaussian_ply):
    plyfile = pytest.importorskip("plyfile")
    assert version("plyfile") == "1.1.3"
    loaded = plyfile.PlyData.read(gaussian_ply)
    assert loaded.text is False
    assert loaded.byte_order == "<"
    assert loaded["vertex"].count == 2
    names = [item.name for item in loaded["vertex"].properties]
    assert names[:9] == [
        "x",
        "y",
        "z",
        "nx",
        "ny",
        "nz",
        "f_dc_0",
        "f_dc_1",
        "f_dc_2",
    ]
    assert names[-8:] == [
        "opacity",
        "scale_0",
        "scale_1",
        "scale_2",
        "rot_0",
        "rot_1",
        "rot_2",
        "rot_3",
    ]
    assert np.isfinite(loaded["vertex"].data.view(np.float32)).all()


def test_gsply_0_4_6_independent_gaussian_consumer(gaussian_ply):
    gsply = pytest.importorskip("gsply", minversion="0.4.6")
    assert version("gsply") == "0.4.6"
    loaded = gsply.plyread(gaussian_ply)
    source = _sample_gaussians()
    assert loaded.means.shape == (2, 3)
    assert loaded.scales.shape == (2, 3)
    assert loaded.quats.shape == (2, 4)
    assert loaded.opacities.shape[0] == 2
    assert loaded.get_sh_degree() == 3
    assert np.isfinite(loaded.means).all()
    np.testing.assert_array_equal(loaded.sh0, source.sh_coeffs[:, 0, :])
    np.testing.assert_array_equal(loaded.shN, source.sh_coeffs[:, 1:, :])


def test_splat_transform_3_0_0_cli_consumer(gaussian_ply):
    if os.environ.get("GAUSSIAN_FACTORY_RUN_EXTERNAL_COMPAT") != "1":
        pytest.skip("set GAUSSIAN_FACTORY_RUN_EXTERNAL_COMPAT=1 for npm CLI validation")
    npx = shutil.which("npx.cmd") or shutil.which("npx")
    if npx is None:
        pytest.skip("Node npx is unavailable")
    result = subprocess.run(
        [
            npx,
            "--yes",
            f"--package={SPLAT_TRANSFORM_NPM_SPEC}",
            "splat-transform",
            str(gaussian_ply),
            "--info",
            "json",
            "null",
        ],
        check=False,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=180,
    )
    combined = result.stdout + "\n" + result.stderr
    assert result.returncode == 0, combined
    assert "splat-transform v3.0.0 (daf6338)" in combined.lower(), combined
    assert "2 gaussians" in combined.lower(), combined
    assert "3 sh bands" in combined.lower(), combined


def test_brush_0_3_0_cli_consumer_with_negative_control(gaussian_ply, tmp_path):
    if os.environ.get("GAUSSIAN_FACTORY_RUN_EXTERNAL_COMPAT") != "1":
        pytest.skip("set GAUSSIAN_FACTORY_RUN_EXTERNAL_COMPAT=1 for Brush validation")
    configured = os.environ.get("GAUSSIAN_FACTORY_BRUSH_EXE")
    if not configured:
        pytest.skip("set GAUSSIAN_FACTORY_BRUSH_EXE to the pinned Brush executable")
    executable = os.path.abspath(configured)
    if not os.path.isfile(executable):
        pytest.skip("configured Brush executable is unavailable")
    version_result = subprocess.run(
        [executable, "--version"], capture_output=True, text=True, errors="replace", timeout=30
    )
    assert version_result.returncode == 0
    assert BRUSH_VERSION in (version_result.stdout + version_result.stderr)

    valid = subprocess.run(
        [executable, str(gaussian_ply), "--total-steps", "0"],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=60,
    )
    assert valid.returncode == 0, valid.stdout + valid.stderr

    malformed = tmp_path / "malformed.ply"
    malformed.write_bytes(b"not a ply")
    invalid = subprocess.run(
        [executable, str(malformed), "--total-steps", "0"],
        capture_output=True,
        text=True,
        errors="replace",
        timeout=60,
    )
    assert invalid.returncode != 0, "Brush negative control unexpectedly loaded"
