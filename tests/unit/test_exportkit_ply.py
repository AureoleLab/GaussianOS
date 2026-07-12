from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from packages.contracts import SphericalHarmonicsSpec
from packages.exportkit import (
    PlyFormatError,
    read_gaussian_ply,
    read_gaussian_ply_document,
    read_pointcloud_ply,
    write_gaussian_ply,
    write_pointcloud_ply,
)


@pytest.mark.parametrize("degree", [0, 1, 2, 3])
def test_gaussian_binary_ply_round_trip(tmp_path, gaussian_factory, degree):
    source = gaussian_factory(degree)
    path = tmp_path / f"degree-{degree}.graphdeco-gs-v1.ply"
    write_gaussian_ply(
        path,
        source,
        SphericalHarmonicsSpec(degree=degree),
        color_space="linear_srgb",
    )
    payload = path.read_bytes()
    assert payload.startswith(b"ply\nformat binary_little_endian 1.0\n")

    restored = read_gaussian_ply(path)
    np.testing.assert_array_equal(restored.means, source.means)
    np.testing.assert_array_equal(restored.log_scales, source.log_scales)
    np.testing.assert_array_equal(restored.quats_wxyz, source.quats_wxyz)
    np.testing.assert_array_equal(restored.opacity_logits, source.opacity_logits)
    np.testing.assert_array_equal(restored.sh_coeffs, source.sh_coeffs)

    document = read_gaussian_ply_document(path)
    assert document.metadata.spherical_harmonics == SphericalHarmonicsSpec(degree=degree)
    assert document.metadata.quaternion_order == "wxyz"
    assert document.metadata.color_space == "linear_srgb"
    assert document.metadata.opacity_encoding == "logit"
    assert document.metadata.scale_encoding == "natural_log"


def test_gaussian_header_matches_checked_in_golden(tmp_path, gaussian_factory):
    path = tmp_path / "golden.graphdeco-gs-v1.ply"
    write_gaussian_ply(
        path,
        gaussian_factory(1),
        SphericalHarmonicsSpec(degree=1),
        color_space="linear_srgb",
    )
    payload = path.read_bytes()
    header = payload[: payload.index(b"end_header\n") + len(b"end_header\n")]
    golden_path = Path(__file__).parents[1] / "golden" / "graphdeco-gs-v1-degree1.header"
    assert header == golden_path.read_bytes()


def test_graphdeco_f_rest_is_channel_major(tmp_path, gaussian_factory):
    from plyfile import PlyData

    source = gaussian_factory(2)
    path = tmp_path / "layout.graphdeco-gs-v1.ply"
    write_gaussian_ply(
        path,
        source,
        SphericalHarmonicsSpec(degree=2),
        color_space="linear_srgb",
    )
    vertex = PlyData.read(path)["vertex"].data
    expected = np.transpose(source.sh_coeffs[:, 1:, :], (0, 2, 1)).reshape(
        source.means.shape[0], -1
    )
    for index in range(expected.shape[1]):
        np.testing.assert_array_equal(vertex[f"f_rest_{index}"], expected[:, index])


def test_pointcloud_binary_ply_round_trip(tmp_path, pointcloud):
    path = tmp_path / "sparse.pointcloud.ply"
    write_pointcloud_ply(path, pointcloud)
    restored = read_pointcloud_ply(path)
    np.testing.assert_array_equal(restored.positions, pointcloud.positions)
    np.testing.assert_array_equal(restored.normals, pointcloud.normals)
    np.testing.assert_array_equal(restored.colors_rgb, pointcloud.colors_rgb)


def test_ply_types_cannot_be_confused_by_filename(tmp_path, gaussian_factory, pointcloud):
    gaussian_path = tmp_path / "scene.graphdeco-gs-v1.ply"
    point_path = tmp_path / "scene.pointcloud.ply"
    write_gaussian_ply(
        gaussian_path,
        gaussian_factory(),
        SphericalHarmonicsSpec(degree=3),
        color_space="linear_srgb",
    )
    write_pointcloud_ply(point_path, pointcloud)

    with pytest.raises(PlyFormatError, match="filename must end"):
        read_pointcloud_ply(gaussian_path)
    with pytest.raises(PlyFormatError, match="filename must end"):
        read_gaussian_ply(point_path)


def test_gaussian_reader_rejects_big_endian_header(tmp_path, gaussian_factory):
    path = tmp_path / "wrong-endian.graphdeco-gs-v1.ply"
    write_gaussian_ply(
        path,
        gaussian_factory(),
        SphericalHarmonicsSpec(degree=3),
        color_space="linear_srgb",
    )
    payload = path.read_bytes().replace(
        b"format binary_little_endian 1.0", b"format binary_big_endian 1.0   ", 1
    )
    path.write_bytes(payload)
    with pytest.raises(PlyFormatError, match="binary_little_endian"):
        read_gaussian_ply(path)


def test_gaussian_reader_rejects_sh_count_mismatch(tmp_path, gaussian_factory):
    path = tmp_path / "wrong-sh.graphdeco-gs-v1.ply"
    write_gaussian_ply(
        path,
        gaussian_factory(2),
        SphericalHarmonicsSpec(degree=2),
        color_space="linear_srgb",
    )
    payload = path.read_bytes().replace(b"comment sh_degree 2", b"comment sh_degree 3", 1)
    path.write_bytes(payload)
    with pytest.raises(PlyFormatError, match="f_rest count"):
        read_gaussian_ply(path)


def test_gaussian_reader_rejects_nan_payload(tmp_path, gaussian_factory):
    path = tmp_path / "nan.graphdeco-gs-v1.ply"
    write_gaussian_ply(
        path,
        gaussian_factory(),
        SphericalHarmonicsSpec(degree=3),
        color_space="linear_srgb",
    )
    payload = bytearray(path.read_bytes())
    payload_start = payload.index(b"end_header\n") + len(b"end_header\n")
    payload[payload_start : payload_start + 4] = np.float32(np.nan).tobytes()
    path.write_bytes(payload)
    with pytest.raises(PlyFormatError, match="NaN or Inf"):
        read_gaussian_ply(path)


def test_gaussian_reader_rejects_non_unit_quaternion(tmp_path, gaussian_factory):
    path = tmp_path / "quat.graphdeco-gs-v1.ply"
    write_gaussian_ply(
        path,
        gaussian_factory(0),
        SphericalHarmonicsSpec(degree=0),
        color_space="linear_srgb",
    )
    payload = bytearray(path.read_bytes())
    payload_start = payload.index(b"end_header\n") + len(b"end_header\n")
    # degree 0 has 17 float32 properties; rot_0 is property index 13.
    rot0_offset = payload_start + 13 * 4
    payload[rot0_offset : rot0_offset + 4] = np.float32(2.0).tobytes()
    path.write_bytes(payload)
    with pytest.raises(PlyFormatError, match="unit quaternions"):
        read_gaussian_ply(path)
