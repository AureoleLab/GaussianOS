"""Validated in-memory tensor payloads for SceneBundle v1."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import numpy.typing as npt


class TensorValidationError(ValueError):
    """Raised when a SceneBundle tensor violates its shape or numeric contract."""


def _array(
    name: str,
    value: npt.NDArray[np.generic],
    dtype: np.dtype[object] | str,
    *,
    ndim: int,
    trailing_shape: tuple[int, ...],
) -> npt.NDArray[np.generic]:
    if not isinstance(value, np.ndarray):
        raise TensorValidationError(f"{name} must be a numpy.ndarray")
    expected_dtype = np.dtype(dtype)
    if value.dtype != expected_dtype:
        raise TensorValidationError(
            f"{name} must have dtype {expected_dtype.name}, got {value.dtype.name}"
        )
    actual_trailing = tuple(value.shape[-len(trailing_shape) :]) if trailing_shape else ()
    if value.ndim != ndim or actual_trailing != trailing_shape:
        rendered_shape = ",".join(map(str, trailing_shape))
        expected_shape = f"[N,{rendered_shape}]" if rendered_shape else "[N]"
        raise TensorValidationError(
            f"{name} must have shape {expected_shape}, got {list(value.shape)}"
        )
    return np.ascontiguousarray(value)


def _finite(name: str, value: npt.NDArray[np.generic]) -> None:
    if not np.isfinite(value).all():
        raise TensorValidationError(f"{name} contains NaN or Inf")


@dataclass(frozen=True, slots=True)
class CameraTensors:
    """OpenCV cam2world cameras; image_sizes columns are width, height."""

    camtoworlds: npt.NDArray[np.float32]
    intrinsics: npt.NDArray[np.float32]
    image_sizes: npt.NDArray[np.int32]
    camera_ids: npt.NDArray[np.int64]

    def __post_init__(self) -> None:
        camtoworlds = _array(
            "camtoworlds", self.camtoworlds, np.float32, ndim=3, trailing_shape=(4, 4)
        )
        intrinsics = _array(
            "intrinsics", self.intrinsics, np.float32, ndim=3, trailing_shape=(3, 3)
        )
        image_sizes = _array(
            "image_sizes", self.image_sizes, np.int32, ndim=2, trailing_shape=(2,)
        )
        camera_ids = _array(
            "camera_ids", self.camera_ids, np.int64, ndim=1, trailing_shape=()
        )

        count = camtoworlds.shape[0]
        if count == 0:
            raise TensorValidationError("camera payload must contain at least one camera")
        if not (
            intrinsics.shape[0]
            == image_sizes.shape[0]
            == camera_ids.shape[0]
            == count
        ):
            raise TensorValidationError("all camera tensors must have the same first dimension")
        _finite("camtoworlds", camtoworlds)
        _finite("intrinsics", intrinsics)

        affine_rows = camtoworlds[:, 3, :]
        expected_affine_row = np.array([0.0, 0.0, 0.0, 1.0], dtype=np.float32)
        if not np.allclose(affine_rows, expected_affine_row, atol=1e-6, rtol=0.0):
            raise TensorValidationError("camtoworlds bottom rows must equal [0,0,0,1]")
        rotations = camtoworlds[:, :3, :3].astype(np.float64)
        identity = np.eye(3, dtype=np.float64)
        gram = np.matmul(np.swapaxes(rotations, 1, 2), rotations)
        if not np.allclose(gram, identity, atol=1e-4, rtol=1e-4):
            raise TensorValidationError("camtoworlds rotations must be orthonormal")
        determinants = np.linalg.det(rotations)
        if not np.allclose(determinants, 1.0, atol=1e-4, rtol=1e-4):
            raise TensorValidationError("camtoworlds rotations must have determinant +1")

        expected_intrinsics_row = np.array([0.0, 0.0, 1.0], dtype=np.float32)
        if not np.allclose(
            intrinsics[:, 2, :], expected_intrinsics_row, atol=1e-6, rtol=0.0
        ):
            raise TensorValidationError("intrinsics bottom rows must equal [0,0,1]")
        if np.any(intrinsics[:, 0, 0] <= 0.0) or np.any(intrinsics[:, 1, 1] <= 0.0):
            raise TensorValidationError("camera focal lengths fx and fy must be positive")
        if np.any(image_sizes <= 0):
            raise TensorValidationError("camera image width and height must be positive")
        if np.unique(camera_ids).size != count:
            raise TensorValidationError("camera_ids must be unique")

        object.__setattr__(self, "camtoworlds", camtoworlds)
        object.__setattr__(self, "intrinsics", intrinsics)
        object.__setattr__(self, "image_sizes", image_sizes)
        object.__setattr__(self, "camera_ids", camera_ids)

    def to_safetensors(self) -> dict[str, npt.NDArray[np.generic]]:
        return {
            "camera_ids": self.camera_ids,
            "camtoworlds": self.camtoworlds,
            "image_sizes": self.image_sizes,
            "intrinsics": self.intrinsics,
        }

    @classmethod
    def from_safetensors(
        cls, tensors: dict[str, npt.NDArray[np.generic]]
    ) -> "CameraTensors":
        expected = {"camera_ids", "camtoworlds", "image_sizes", "intrinsics"}
        if set(tensors) != expected:
            raise TensorValidationError(
                f"camera safetensors names must be {sorted(expected)}, got {sorted(tensors)}"
            )
        return cls(
            camtoworlds=tensors["camtoworlds"],
            intrinsics=tensors["intrinsics"],
            image_sizes=tensors["image_sizes"],
            camera_ids=tensors["camera_ids"],
        )


@dataclass(frozen=True, slots=True)
class GaussianTensors:
    """Canonical Gaussian payload, before opacity/scale activation."""

    means: npt.NDArray[np.float32]
    log_scales: npt.NDArray[np.float32]
    quats_wxyz: npt.NDArray[np.float32]
    opacity_logits: npt.NDArray[np.float32]
    sh_coeffs: npt.NDArray[np.float32]

    def __post_init__(self) -> None:
        means = _array("means", self.means, np.float32, ndim=2, trailing_shape=(3,))
        log_scales = _array(
            "log_scales", self.log_scales, np.float32, ndim=2, trailing_shape=(3,)
        )
        quats_wxyz = _array(
            "quats_wxyz", self.quats_wxyz, np.float32, ndim=2, trailing_shape=(4,)
        )
        opacity_logits = _array(
            "opacity_logits",
            self.opacity_logits,
            np.float32,
            ndim=2,
            trailing_shape=(1,),
        )
        if not isinstance(self.sh_coeffs, np.ndarray):
            raise TensorValidationError("sh_coeffs must be a numpy.ndarray")
        if self.sh_coeffs.dtype != np.dtype(np.float32):
            raise TensorValidationError(
                f"sh_coeffs must have dtype float32, got {self.sh_coeffs.dtype.name}"
            )
        if self.sh_coeffs.ndim != 3 or self.sh_coeffs.shape[2] != 3:
            raise TensorValidationError(
                f"sh_coeffs must have shape [N,K,3], got {list(self.sh_coeffs.shape)}"
            )
        sh_coeffs = np.ascontiguousarray(self.sh_coeffs)

        count = means.shape[0]
        if count == 0:
            raise TensorValidationError("Gaussian payload must contain at least one Gaussian")
        if not (
            log_scales.shape[0]
            == quats_wxyz.shape[0]
            == opacity_logits.shape[0]
            == sh_coeffs.shape[0]
            == count
        ):
            raise TensorValidationError("all Gaussian tensors must have the same first dimension")
        coefficient_count = sh_coeffs.shape[1]
        degree = int(round(coefficient_count**0.5)) - 1
        if degree < 0 or degree > 3 or (degree + 1) ** 2 != coefficient_count:
            raise TensorValidationError(
                "sh_coeffs K must equal (degree+1)^2 for a degree in [0,3]"
            )

        for name, tensor in (
            ("means", means),
            ("log_scales", log_scales),
            ("quats_wxyz", quats_wxyz),
            ("opacity_logits", opacity_logits),
            ("sh_coeffs", sh_coeffs),
        ):
            _finite(name, tensor)

        quaternion_norms = np.linalg.norm(quats_wxyz.astype(np.float64), axis=1)
        if not np.allclose(quaternion_norms, 1.0, atol=1e-4, rtol=1e-4):
            raise TensorValidationError("quats_wxyz must contain unit quaternions")
        if np.any(np.abs(quats_wxyz) > 1.0001):
            raise TensorValidationError("unit quaternion components must be within [-1,1]")

        activated_scales = np.exp(log_scales.astype(np.float64))
        float32 = np.finfo(np.float32)
        if (
            not np.isfinite(activated_scales).all()
            or np.any(activated_scales < float32.tiny)
            or np.any(activated_scales > float32.max)
        ):
            raise TensorValidationError(
                "exp(log_scales) must be finite, positive, normal float32 values"
            )

        logits64 = opacity_logits.astype(np.float64)
        activated_opacity = np.empty_like(logits64)
        positive = logits64 >= 0.0
        activated_opacity[positive] = 1.0 / (1.0 + np.exp(-logits64[positive]))
        negative_exp = np.exp(logits64[~positive])
        activated_opacity[~positive] = negative_exp / (1.0 + negative_exp)
        activated_opacity_float32 = activated_opacity.astype(np.float32)
        if (
            not np.isfinite(activated_opacity_float32).all()
            or np.any(activated_opacity_float32 <= 0.0)
            or np.any(activated_opacity_float32 >= 1.0)
        ):
            raise TensorValidationError(
                "float32 sigmoid(opacity_logits) must remain strictly within (0,1)"
            )

        object.__setattr__(self, "means", means)
        object.__setattr__(self, "log_scales", log_scales)
        object.__setattr__(self, "quats_wxyz", quats_wxyz)
        object.__setattr__(self, "opacity_logits", opacity_logits)
        object.__setattr__(self, "sh_coeffs", sh_coeffs)

    @property
    def sh_degree(self) -> int:
        return int(round(self.sh_coeffs.shape[1] ** 0.5)) - 1

    def to_safetensors(self) -> dict[str, npt.NDArray[np.generic]]:
        return {
            "log_scales": self.log_scales,
            "means": self.means,
            "opacity_logits": self.opacity_logits,
            "quats_wxyz": self.quats_wxyz,
            "sh_coeffs": self.sh_coeffs,
        }

    @classmethod
    def from_safetensors(
        cls, tensors: dict[str, npt.NDArray[np.generic]]
    ) -> "GaussianTensors":
        expected = {
            "log_scales",
            "means",
            "opacity_logits",
            "quats_wxyz",
            "sh_coeffs",
        }
        if set(tensors) != expected:
            raise TensorValidationError(
                f"Gaussian safetensors names must be {sorted(expected)}, got {sorted(tensors)}"
            )
        return cls(
            means=tensors["means"],
            log_scales=tensors["log_scales"],
            quats_wxyz=tensors["quats_wxyz"],
            opacity_logits=tensors["opacity_logits"],
            sh_coeffs=tensors["sh_coeffs"],
        )


@dataclass(frozen=True, slots=True)
class PointCloudTensors:
    positions: npt.NDArray[np.float32]
    colors_rgb: npt.NDArray[np.uint8] | None = None
    normals: npt.NDArray[np.float32] | None = None

    def __post_init__(self) -> None:
        positions = _array(
            "positions", self.positions, np.float32, ndim=2, trailing_shape=(3,)
        )
        if positions.shape[0] == 0:
            raise TensorValidationError("point cloud must contain at least one point")
        _finite("positions", positions)
        object.__setattr__(self, "positions", positions)

        if self.colors_rgb is not None:
            colors = _array(
                "colors_rgb", self.colors_rgb, np.uint8, ndim=2, trailing_shape=(3,)
            )
            if colors.shape[0] != positions.shape[0]:
                raise TensorValidationError("colors_rgb count must match positions")
            object.__setattr__(self, "colors_rgb", colors)

        if self.normals is not None:
            normals = _array(
                "normals", self.normals, np.float32, ndim=2, trailing_shape=(3,)
            )
            if normals.shape[0] != positions.shape[0]:
                raise TensorValidationError("normals count must match positions")
            _finite("normals", normals)
            object.__setattr__(self, "normals", normals)
