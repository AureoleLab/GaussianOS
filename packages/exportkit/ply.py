"""Strict binary little-endian PLY codecs for points and Graphdeco Gaussians."""

from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, Iterable

import numpy as np

from packages.contracts import SphericalHarmonicsSpec
from packages.scene_bundle import GaussianTensors, PointCloudTensors


POINTCLOUD_SUFFIX = ".pointcloud.ply"
GAUSSIAN_SUFFIX = ".graphdeco-gs-v1.ply"
MAX_PLY_HEADER_BYTES = 1024 * 1024


class PlyFormatError(ValueError):
    """Raised when a file does not conform to one of ExportKit's PLY contracts."""


@dataclass(frozen=True, slots=True)
class GaussianPlyMetadata:
    spherical_harmonics: SphericalHarmonicsSpec
    quaternion_order: str
    color_space: str
    opacity_encoding: str
    scale_encoding: str


@dataclass(frozen=True, slots=True)
class GaussianPlyDocument:
    metadata: GaussianPlyMetadata
    gaussians: GaussianTensors


@dataclass(frozen=True, slots=True)
class _PlyProperty:
    scalar_type: str
    name: str


@dataclass(frozen=True, slots=True)
class _PlyHeader:
    vertex_count: int
    properties: tuple[_PlyProperty, ...]
    comments: tuple[str, ...]


_PLY_DTYPES: dict[str, str] = {
    "char": "i1",
    "int8": "i1",
    "uchar": "u1",
    "uint8": "u1",
    "short": "<i2",
    "int16": "<i2",
    "ushort": "<u2",
    "uint16": "<u2",
    "int": "<i4",
    "int32": "<i4",
    "uint": "<u4",
    "uint32": "<u4",
    "float": "<f4",
    "float32": "<f4",
    "double": "<f8",
    "float64": "<f8",
}


def _require_suffix(path: Path, suffix: str) -> None:
    if not path.name.lower().endswith(suffix):
        raise PlyFormatError(f"filename must end with {suffix}: {path.name}")


def _read_header(stream: BinaryIO) -> _PlyHeader:
    lines: list[str] = []
    total = 0
    while True:
        raw = stream.readline(MAX_PLY_HEADER_BYTES + 1)
        if not raw:
            raise PlyFormatError("truncated PLY header")
        total += len(raw)
        if total > MAX_PLY_HEADER_BYTES:
            raise PlyFormatError("PLY header exceeds safety limit")
        try:
            line = raw.rstrip(b"\r\n").decode("ascii")
        except UnicodeDecodeError as exc:
            raise PlyFormatError("PLY header must be ASCII") from exc
        lines.append(line)
        if line == "end_header":
            break

    if not lines or lines[0] != "ply":
        raise PlyFormatError("missing PLY magic")
    if len(lines) < 3 or lines[1] != "format binary_little_endian 1.0":
        raise PlyFormatError("only binary_little_endian PLY 1.0 is supported")

    comments: list[str] = []
    properties: list[_PlyProperty] = []
    vertex_count: int | None = None
    current_element: str | None = None
    for line in lines[2:-1]:
        if line.startswith("comment "):
            comments.append(line[len("comment ") :])
            continue
        if line.startswith("obj_info "):
            continue
        tokens = line.split()
        if len(tokens) == 3 and tokens[0] == "element":
            if current_element is not None:
                raise PlyFormatError("only a single vertex element is supported")
            current_element = tokens[1]
            if current_element != "vertex":
                raise PlyFormatError("only the vertex element is supported")
            try:
                vertex_count = int(tokens[2])
            except ValueError as exc:
                raise PlyFormatError("vertex count must be an integer") from exc
            if vertex_count <= 0:
                raise PlyFormatError("vertex count must be positive")
            continue
        if tokens and tokens[0] == "property":
            if current_element != "vertex":
                raise PlyFormatError("property declared outside vertex element")
            if len(tokens) != 3 or tokens[1] == "list":
                raise PlyFormatError("only scalar vertex properties are supported")
            if tokens[1] not in _PLY_DTYPES:
                raise PlyFormatError(f"unsupported PLY scalar type: {tokens[1]}")
            properties.append(_PlyProperty(tokens[1], tokens[2]))
            continue
        raise PlyFormatError(f"unsupported PLY header directive: {line}")

    if vertex_count is None:
        raise PlyFormatError("missing vertex element")
    names = [item.name for item in properties]
    if not names or len(names) != len(set(names)):
        raise PlyFormatError("PLY vertex properties must be present and unique")
    return _PlyHeader(vertex_count, tuple(properties), tuple(comments))


def _read_vertices(stream: BinaryIO, header: _PlyHeader) -> np.ndarray:
    dtype = np.dtype(
        [(item.name, _PLY_DTYPES[item.scalar_type]) for item in header.properties]
    )
    expected_size = header.vertex_count * dtype.itemsize
    payload_start = stream.tell()
    stream.seek(0, os.SEEK_END)
    remaining_size = stream.tell() - payload_start
    stream.seek(payload_start, os.SEEK_SET)
    if remaining_size != expected_size:
        relation = "truncated" if remaining_size < expected_size else "has trailing bytes"
        raise PlyFormatError(
            f"PLY payload {relation}: expected {expected_size} bytes, got {remaining_size}"
        )
    payload = stream.read(expected_size)
    if len(payload) != expected_size:
        raise PlyFormatError(
            f"truncated PLY payload: expected {expected_size} bytes, got {len(payload)}"
        )
    return np.frombuffer(payload, dtype=dtype, count=header.vertex_count)


def _comment_value(comments: Iterable[str], key: str) -> str:
    prefix = f"{key} "
    values = [item[len(prefix) :] for item in comments if item.startswith(prefix)]
    if len(values) != 1:
        raise PlyFormatError(f"expected exactly one '{key}' PLY comment")
    return values[0]


def _atomic_write(
    destination: Path,
    header_lines: list[str],
    vertices: np.ndarray,
    *,
    overwrite: bool,
) -> Path:
    if destination.exists() and not overwrite:
        raise FileExistsError(f"PLY destination already exists: {destination}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.attempt-", dir=str(destination.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(("\n".join(header_lines) + "\n").encode("ascii"))
            stream.write(vertices.tobytes(order="C"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, destination)
    except Exception:
        temporary.unlink(missing_ok=True)
        raise
    return destination


def write_pointcloud_ply(
    destination: str | os.PathLike[str],
    pointcloud: PointCloudTensors,
    *,
    overwrite: bool = False,
) -> Path:
    """Write an unambiguous ordinary point cloud PLY."""

    path = Path(destination).absolute()
    _require_suffix(path, POINTCLOUD_SUFFIX)
    fields: list[tuple[str, str]] = [(axis, "<f4") for axis in ("x", "y", "z")]
    if pointcloud.normals is not None:
        fields.extend((axis, "<f4") for axis in ("nx", "ny", "nz"))
    if pointcloud.colors_rgb is not None:
        fields.extend((channel, "u1") for channel in ("red", "green", "blue"))
    vertices = np.empty(pointcloud.positions.shape[0], dtype=np.dtype(fields))
    for index, axis in enumerate(("x", "y", "z")):
        vertices[axis] = pointcloud.positions[:, index]
    if pointcloud.normals is not None:
        for index, axis in enumerate(("nx", "ny", "nz")):
            vertices[axis] = pointcloud.normals[:, index]
    if pointcloud.colors_rgb is not None:
        for index, channel in enumerate(("red", "green", "blue")):
            vertices[channel] = pointcloud.colors_rgb[:, index]

    header = [
        "ply",
        "format binary_little_endian 1.0",
        "comment gaussian_factory_format pointcloud-v1",
        f"comment color_space {'srgb' if pointcloud.colors_rgb is not None else 'none'}",
        f"element vertex {vertices.shape[0]}",
    ]
    header.extend(
        f"property {'uchar' if np.dtype(dtype).kind == 'u' else 'float'} {name}"
        for name, dtype in fields
    )
    header.append("end_header")
    return _atomic_write(path, header, vertices, overwrite=overwrite)


def read_pointcloud_ply(source: str | os.PathLike[str]) -> PointCloudTensors:
    """Read only ExportKit pointcloud-v1, never a Gaussian PLY by accident."""

    path = Path(source).absolute()
    _require_suffix(path, POINTCLOUD_SUFFIX)
    with path.open("rb") as stream:
        header = _read_header(stream)
        if _comment_value(header.comments, "gaussian_factory_format") != "pointcloud-v1":
            raise PlyFormatError("not an ExportKit pointcloud-v1 PLY")
        declared_color_space = _comment_value(header.comments, "color_space")
        names = [item.name for item in header.properties]
        allowed_orders = [
            ["x", "y", "z"],
            ["x", "y", "z", "nx", "ny", "nz"],
            ["x", "y", "z", "red", "green", "blue"],
            ["x", "y", "z", "nx", "ny", "nz", "red", "green", "blue"],
        ]
        if names not in allowed_orders:
            raise PlyFormatError("invalid pointcloud-v1 property layout")
        has_colors = "red" in names
        if declared_color_space != ("srgb" if has_colors else "none"):
            raise PlyFormatError("pointcloud color_space does not match its properties")
        by_name = {item.name: item.scalar_type for item in header.properties}
        for name in ("x", "y", "z", "nx", "ny", "nz"):
            if name in by_name and by_name[name] not in {"float", "float32"}:
                raise PlyFormatError(f"{name} must be float32")
        for name in ("red", "green", "blue"):
            if name in by_name and by_name[name] not in {"uchar", "uint8"}:
                raise PlyFormatError(f"{name} must be uint8")
        vertices = _read_vertices(stream, header)

    positions = np.column_stack([vertices[name] for name in ("x", "y", "z")]).astype(
        np.float32, copy=False
    )
    normals = None
    if "nx" in names:
        normals = np.column_stack(
            [vertices[name] for name in ("nx", "ny", "nz")]
        ).astype(np.float32, copy=False)
    colors = None
    if "red" in names:
        colors = np.column_stack(
            [vertices[name] for name in ("red", "green", "blue")]
        ).astype(np.uint8, copy=False)
    return PointCloudTensors(positions=positions, normals=normals, colors_rgb=colors)


def _gaussian_properties(sh_degree: int) -> list[str]:
    rest_count = 3 * (((sh_degree + 1) ** 2) - 1)
    return [
        "x",
        "y",
        "z",
        "nx",
        "ny",
        "nz",
        "f_dc_0",
        "f_dc_1",
        "f_dc_2",
        *(f"f_rest_{index}" for index in range(rest_count)),
        "opacity",
        "scale_0",
        "scale_1",
        "scale_2",
        "rot_0",
        "rot_1",
        "rot_2",
        "rot_3",
    ]


def write_gaussian_ply(
    destination: str | os.PathLike[str],
    gaussians: GaussianTensors,
    sh_spec: SphericalHarmonicsSpec,
    *,
    color_space: str,
    overwrite: bool = False,
) -> Path:
    """Write graphdeco-gs-v1 using channel-major f_rest and wxyz rotations."""

    path = Path(destination).absolute()
    _require_suffix(path, GAUSSIAN_SUFFIX)
    if gaussians.sh_degree != sh_spec.degree:
        raise PlyFormatError("Gaussian SH degree does not match the supplied SH spec")
    if color_space not in {"linear_srgb", "srgb"}:
        raise PlyFormatError("color_space must be linear_srgb or srgb")

    properties = _gaussian_properties(sh_spec.degree)
    vertices = np.empty(
        gaussians.means.shape[0],
        dtype=np.dtype([(name, "<f4") for name in properties]),
    )
    for index, axis in enumerate(("x", "y", "z")):
        vertices[axis] = gaussians.means[:, index]
    for axis in ("nx", "ny", "nz"):
        vertices[axis] = 0.0
    for channel, name in enumerate(("f_dc_0", "f_dc_1", "f_dc_2")):
        vertices[name] = gaussians.sh_coeffs[:, 0, channel]

    rest = gaussians.sh_coeffs[:, 1:, :]
    # Graphdeco save/load flattens [RGB, remaining SH] in channel-major order.
    flattened_rest = np.transpose(rest, (0, 2, 1)).reshape(rest.shape[0], -1)
    for index in range(flattened_rest.shape[1]):
        vertices[f"f_rest_{index}"] = flattened_rest[:, index]
    vertices["opacity"] = gaussians.opacity_logits[:, 0]
    for index in range(3):
        vertices[f"scale_{index}"] = gaussians.log_scales[:, index]
    for index in range(4):
        vertices[f"rot_{index}"] = gaussians.quats_wxyz[:, index]

    header = [
        "ply",
        "format binary_little_endian 1.0",
        "comment gaussian_factory_format graphdeco-gs-v1",
        f"comment sh_degree {sh_spec.degree}",
        f"comment sh_basis {sh_spec.basis}",
        f"comment sh_ordering {sh_spec.ordering}",
        "comment sh_channel_order rgb",
        "comment f_rest_layout channel_major",
        "comment quaternion_order wxyz",
        "comment opacity_encoding logit",
        "comment scale_encoding natural_log",
        f"comment color_space {color_space}",
        f"element vertex {vertices.shape[0]}",
        *(f"property float {name}" for name in properties),
        "end_header",
    ]
    return _atomic_write(path, header, vertices, overwrite=overwrite)


def read_gaussian_ply_document(
    source: str | os.PathLike[str],
) -> GaussianPlyDocument:
    """Read graphdeco-gs-v1 values together with its semantic metadata."""

    path = Path(source).absolute()
    _require_suffix(path, GAUSSIAN_SUFFIX)
    with path.open("rb") as stream:
        header = _read_header(stream)
        expected_comments = {
            "gaussian_factory_format": "graphdeco-gs-v1",
            "sh_basis": "graphdeco_real_sh",
            "sh_ordering": "degree_major_m_neg_to_pos",
            "sh_channel_order": "rgb",
            "f_rest_layout": "channel_major",
            "quaternion_order": "wxyz",
            "opacity_encoding": "logit",
            "scale_encoding": "natural_log",
        }
        for key, expected in expected_comments.items():
            if _comment_value(header.comments, key) != expected:
                raise PlyFormatError(f"invalid {key} declaration")
        color_space = _comment_value(header.comments, "color_space")
        if color_space not in {"linear_srgb", "srgb"}:
            raise PlyFormatError("invalid color_space declaration")
        try:
            sh_degree = int(_comment_value(header.comments, "sh_degree"))
        except ValueError as exc:
            raise PlyFormatError("sh_degree comment must be an integer") from exc
        if sh_degree < 0 or sh_degree > 3:
            raise PlyFormatError("sh_degree must be in [0,3]")
        metadata = GaussianPlyMetadata(
            spherical_harmonics=SphericalHarmonicsSpec(degree=sh_degree),
            quaternion_order=_comment_value(header.comments, "quaternion_order"),
            color_space=color_space,
            opacity_encoding=_comment_value(header.comments, "opacity_encoding"),
            scale_encoding=_comment_value(header.comments, "scale_encoding"),
        )

        names = [item.name for item in header.properties]
        if names != _gaussian_properties(sh_degree):
            raise PlyFormatError(
                "Gaussian property layout or f_rest count does not match sh_degree"
            )
        if any(item.scalar_type not in {"float", "float32"} for item in header.properties):
            raise PlyFormatError("all graphdeco-gs-v1 properties must be float32")
        vertices = _read_vertices(stream, header)

    means = np.column_stack([vertices[name] for name in ("x", "y", "z")]).astype(
        np.float32, copy=False
    )
    normal_values = np.column_stack(
        [vertices[name] for name in ("nx", "ny", "nz")]
    )
    if not np.isfinite(normal_values).all():
        raise PlyFormatError("normal placeholders contain NaN or Inf")
    if np.any(normal_values != 0.0):
        raise PlyFormatError("graphdeco-gs-v1 normal placeholders must be zero")

    coefficient_count = (sh_degree + 1) ** 2
    sh_coeffs = np.empty((header.vertex_count, coefficient_count, 3), dtype=np.float32)
    for channel, name in enumerate(("f_dc_0", "f_dc_1", "f_dc_2")):
        sh_coeffs[:, 0, channel] = vertices[name]
    rest_count = 3 * (coefficient_count - 1)
    if rest_count:
        flattened_rest = np.column_stack(
            [vertices[f"f_rest_{index}"] for index in range(rest_count)]
        ).astype(np.float32, copy=False)
        sh_coeffs[:, 1:, :] = np.transpose(
            flattened_rest.reshape(header.vertex_count, 3, coefficient_count - 1),
            (0, 2, 1),
        )

    opacity_logits = np.asarray(vertices["opacity"], dtype=np.float32).reshape(-1, 1)
    log_scales = np.column_stack(
        [vertices[f"scale_{index}"] for index in range(3)]
    ).astype(np.float32, copy=False)
    quats_wxyz = np.column_stack(
        [vertices[f"rot_{index}"] for index in range(4)]
    ).astype(np.float32, copy=False)
    try:
        gaussians = GaussianTensors(
            means=means,
            log_scales=log_scales,
            quats_wxyz=quats_wxyz,
            opacity_logits=opacity_logits,
            sh_coeffs=sh_coeffs,
        )
    except ValueError as exc:
        raise PlyFormatError(f"invalid Gaussian values: {exc}") from exc
    return GaussianPlyDocument(metadata=metadata, gaussians=gaussians)


def read_gaussian_ply(source: str | os.PathLike[str]) -> GaussianTensors:
    """Read and fully validate ExportKit graphdeco-gs-v1 tensors."""

    return read_gaussian_ply_document(source).gaussians
