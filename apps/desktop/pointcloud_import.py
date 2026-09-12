"""Shared desktop reader for canonical and native reconstruction point clouds."""
from __future__ import annotations
import re
from pathlib import Path
import numpy as np
from packages.exportkit import PlyFormatError, read_pointcloud_ply
from packages.scene_bundle import PointCloudTensors

_PLY_SCALAR_DTYPES = {
    "char": "i1", "int8": "i1", "uchar": "u1", "uint8": "u1",
    "short": "<i2", "int16": "<i2", "ushort": "<u2", "uint16": "<u2",
    "int": "<i4", "int32": "<i4", "uint": "<u4", "uint32": "<u4",
    "float": "<f4", "float32": "<f4", "double": "<f8", "float64": "<f8",
}


def read_compatible_pointcloud(path: Path) -> PointCloudTensors:
    """Read ExportKit or a scalar binary little-endian point PLY.

    Compatibility PLYs are accepted here rather than in ExportKit because
    they do not carry the interchange-format comments required by that API.
    """
    try:
        return read_pointcloud_ply(path)
    except PlyFormatError:
        payload = path.read_bytes()
        match = re.search(br"end_header\r?\n", payload[: 1024 * 1024])
        if match is None:
            raise ValueError("unsupported standard point-cloud PLY layout")
        try:
            lines = payload[:match.end()].decode("ascii").splitlines()
        except UnicodeDecodeError as exc:
            raise ValueError("point-cloud PLY header must be ASCII") from exc
        if not lines or lines[0] != "ply" or "format binary_little_endian 1.0" not in lines:
            raise ValueError("only binary little-endian point-cloud PLY is supported")
        vertex_count: int | None = None
        properties: list[tuple[str, str]] = []
        in_vertices = False
        for line in lines:
            fields = line.split()
            if len(fields) == 3 and fields[:2] == ["element", "vertex"]:
                vertex_count = int(fields[2]); in_vertices = True
            elif fields[:1] == ["element"]:
                in_vertices = False
            elif in_vertices and fields[:1] == ["property"]:
                if len(fields) != 3 or fields[1] not in _PLY_SCALAR_DTYPES:
                    raise ValueError("unsupported point-cloud PLY vertex property")
                properties.append((fields[2], _PLY_SCALAR_DTYPES[fields[1]]))
        names = [name for name, _ in properties]
        if vertex_count is None or vertex_count <= 0 or not all(name in names for name in ("x", "y", "z")):
            raise ValueError("point-cloud PLY is missing scalar xyz vertices")
        dtype = np.dtype(properties)
        expected = vertex_count * dtype.itemsize
        body = payload[match.end():]
        if len(body) != expected:
            raise ValueError("point-cloud PLY payload size does not match its header")
        vertices = np.frombuffer(body, dtype=dtype, count=vertex_count)
        positions = np.column_stack([vertices[name] for name in ("x", "y", "z")]).astype(np.float32)
        colors = None
        if all(name in names for name in ("red", "green", "blue")):
            colors = np.column_stack([vertices[name] for name in ("red", "green", "blue")]).astype(np.uint8)
        return PointCloudTensors(positions=positions, colors_rgb=colors)
