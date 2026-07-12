"""Versioned, strict contracts for the SceneBundle v1 interchange format."""

from __future__ import annotations

import math
from pathlib import PurePosixPath
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictFloat,
    StrictInt,
    StringConstraints,
    model_validator,
)


SCENE_BUNDLE_SCHEMA_VERSION = "scene-bundle/v1"

Sha256 = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-f]{64}$", min_length=64, max_length=64),
]
GitCommit = Annotated[
    str,
    StringConstraints(pattern=r"^[0-9a-f]{40}$", min_length=40, max_length=40),
]
NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
FiniteFloat = Annotated[StrictFloat, Field(allow_inf_nan=False)]
Vec4 = tuple[FiniteFloat, FiniteFloat, FiniteFloat, FiniteFloat]
Matrix4x4 = tuple[Vec4, Vec4, Vec4, Vec4]


class StrictContract(BaseModel):
    """Common settings for externally persisted contracts."""

    model_config = ConfigDict(extra="forbid", frozen=True, validate_default=True)


class CoordinateSystemSpec(StrictContract):
    """The one coordinate system accepted by SceneBundle v1."""

    handedness: Literal["right_handed"] = "right_handed"
    camera_transform: Literal["cam2world"] = "cam2world"
    x_axis: Literal["right"] = "right"
    y_axis: Literal["down"] = "down"
    z_axis: Literal["forward"] = "forward"


IDENTITY_4X4: Matrix4x4 = (
    (1.0, 0.0, 0.0, 0.0),
    (0.0, 1.0, 0.0, 0.0),
    (0.0, 0.0, 1.0, 0.0),
    (0.0, 0.0, 0.0, 1.0),
)


class NormalizationTransform(StrictContract):
    """Affine transform from the source world into the stored SceneBundle world."""

    source_to_scene: Matrix4x4 = IDENTITY_4X4

    @model_validator(mode="after")
    def validate_affine_invertible(self) -> "NormalizationTransform":
        matrix = self.source_to_scene
        if tuple(matrix[3]) != (0.0, 0.0, 0.0, 1.0):
            raise ValueError("normalization transform must have affine bottom row [0,0,0,1]")

        a, b, c = matrix[0][:3], matrix[1][:3], matrix[2][:3]
        determinant = (
            a[0] * (b[1] * c[2] - b[2] * c[1])
            - a[1] * (b[0] * c[2] - b[2] * c[0])
            + a[2] * (b[0] * c[1] - b[1] * c[0])
        )
        if not math.isfinite(determinant) or abs(determinant) <= 1e-15:
            raise ValueError("normalization transform must be invertible")
        return self


class SphericalHarmonicsSpec(StrictContract):
    """Real SH layout used by Graphdeco-compatible Gaussian payloads."""

    degree: Annotated[StrictInt, Field(ge=0, le=3)]
    basis: Literal["graphdeco_real_sh"] = "graphdeco_real_sh"
    ordering: Literal["degree_major_m_neg_to_pos"] = "degree_major_m_neg_to_pos"
    channel_order: Literal["rgb"] = "rgb"

    @property
    def coefficient_count(self) -> int:
        return (self.degree + 1) ** 2


class InputFileHash(StrictContract):
    logical_path: NonEmptyString
    sha256: Sha256

    @model_validator(mode="after")
    def validate_logical_path(self) -> "InputFileHash":
        path = PurePosixPath(self.logical_path)
        if (
            path.is_absolute()
            or ".." in path.parts
            or "\\" in self.logical_path
            or "\x00" in self.logical_path
        ):
            raise ValueError("logical_path must be a safe relative POSIX path")
        return self


class PluginProvenance(StrictContract):
    """Reproducibility and licensing facts for one algorithm plugin."""

    plugin_id: NonEmptyString
    plugin_version: NonEmptyString
    upstream_commit: GitCommit
    config_sha256: Sha256
    weight_sha256: tuple[Sha256, ...]
    code_license: NonEmptyString
    checkpoint_license: NonEmptyString

    @model_validator(mode="after")
    def validate_checkpoint_declaration(self) -> "PluginProvenance":
        sentinel = self.checkpoint_license.upper() == "NO_CHECKPOINT"
        if self.weight_sha256 and sentinel:
            raise ValueError("checkpoint_license must name a license when weights are present")
        if not self.weight_sha256 and not sentinel:
            raise ValueError(
                "checkpoint_license must be NO_CHECKPOINT when weight_sha256 is empty"
            )
        return self


class TensorSpec(StrictContract):
    dtype: Literal["float32", "float64", "int32", "int64", "uint8"]
    shape: tuple[Annotated[StrictInt, Field(ge=0)], ...]


class TensorArtifactReference(StrictContract):
    relative_path: NonEmptyString
    sha256: Sha256
    byte_size: Annotated[StrictInt, Field(ge=0)]
    tensors: Annotated[dict[NonEmptyString, TensorSpec], Field(min_length=1)]

    @model_validator(mode="after")
    def validate_relative_path(self) -> "TensorArtifactReference":
        path = PurePosixPath(self.relative_path)
        if (
            path.is_absolute()
            or ".." in path.parts
            or "\\" in self.relative_path
            or "\x00" in self.relative_path
        ):
            raise ValueError("artifact relative_path must be safe and relative")
        return self


class ScenePayloadIndex(StrictContract):
    cameras: TensorArtifactReference | None = None
    gaussians: TensorArtifactReference | None = None


class SceneBundleManifest(StrictContract):
    """Authoritative metadata for one SceneBundle v1 directory."""

    model_config = ConfigDict(
        json_schema_extra={
            "$id": "https://gaussian-factory.local/schemas/scene-bundle-v1.schema.json",
            "$schema": "https://json-schema.org/draft/2020-12/schema",
        }
    )

    schema_version: Literal["scene-bundle/v1"] = SCENE_BUNDLE_SCHEMA_VERSION
    coordinate_system: CoordinateSystemSpec = Field(default_factory=CoordinateSystemSpec)
    camera_convention: Literal["opencv_cam2world"] = "opencv_cam2world"
    world_unit: Literal["meters", "centimeters", "millimeters", "scene_units"]
    has_metric_scale: StrictBool
    normalization_transform: NormalizationTransform = Field(
        default_factory=NormalizationTransform
    )
    spherical_harmonics: SphericalHarmonicsSpec
    quaternion_order: Literal["wxyz"] = "wxyz"
    color_space: Literal["linear_srgb", "srgb"]
    input_files: Annotated[tuple[InputFileHash, ...], Field(min_length=1)]
    reconstruction_plugin: PluginProvenance
    trainer_plugin: PluginProvenance
    payloads: ScenePayloadIndex = Field(default_factory=ScenePayloadIndex)

    @model_validator(mode="after")
    def validate_manifest_consistency(self) -> "SceneBundleManifest":
        if self.has_metric_scale == (self.world_unit == "scene_units"):
            raise ValueError(
                "metric scale requires a metric world_unit; non-metric scale requires scene_units"
            )
        logical_paths = [item.logical_path for item in self.input_files]
        if len(set(logical_paths)) != len(logical_paths):
            raise ValueError("input_files contains duplicate logical_path values")
        return self


def scene_bundle_json_schema() -> dict[str, object]:
    """Return the canonical Pydantic-generated JSON Schema for SceneBundle v1."""

    return SceneBundleManifest.model_json_schema(
        mode="validation",
        ref_template="#/$defs/{model}",
    )
