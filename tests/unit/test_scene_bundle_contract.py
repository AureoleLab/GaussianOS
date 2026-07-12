from __future__ import annotations

import json
from pathlib import Path

import jsonschema
import pytest
from pydantic import ValidationError

from packages.contracts import (
    NormalizationTransform,
    PluginProvenance,
    SceneBundleManifest,
    scene_bundle_json_schema,
)


def test_manifest_records_canonical_conventions_and_provenance(manifest_factory):
    manifest = manifest_factory(3)
    serialized = manifest.model_dump(mode="json")

    assert serialized["schema_version"] == "scene-bundle/v1"
    assert serialized["coordinate_system"] == {
        "handedness": "right_handed",
        "camera_transform": "cam2world",
        "x_axis": "right",
        "y_axis": "down",
        "z_axis": "forward",
    }
    assert serialized["camera_convention"] == "opencv_cam2world"
    assert serialized["quaternion_order"] == "wxyz"
    assert serialized["spherical_harmonics"]["degree"] == 3
    assert serialized["reconstruction_plugin"]["upstream_commit"] == "1" * 40
    assert serialized["trainer_plugin"]["config_sha256"] == "4" * 64
    assert serialized["trainer_plugin"]["weight_sha256"] == []
    assert serialized["trainer_plugin"]["code_license"] == "Apache-2.0"
    assert serialized["trainer_plugin"]["checkpoint_license"] == "NO_CHECKPOINT"


def test_manifest_rejects_extra_fields_and_inconsistent_units(manifest_factory):
    payload = manifest_factory().model_dump(mode="json")
    payload["unexpected"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        SceneBundleManifest.model_validate(payload)

    payload.pop("unexpected")
    payload["world_unit"] = "meters"
    with pytest.raises(ValidationError, match="metric scale"):
        SceneBundleManifest.model_validate(payload)


def test_manifest_does_not_coerce_numeric_or_boolean_strings(manifest_factory):
    payload = manifest_factory().model_dump(mode="json")
    payload["spherical_harmonics"]["degree"] = "3"
    payload["has_metric_scale"] = "false"
    with pytest.raises(ValidationError):
        SceneBundleManifest.model_validate(payload)


def test_normalization_transform_must_be_affine_and_invertible():
    with pytest.raises(ValidationError, match="affine bottom row"):
        NormalizationTransform(
            source_to_scene=(
                (1.0, 0.0, 0.0, 0.0),
                (0.0, 1.0, 0.0, 0.0),
                (0.0, 0.0, 1.0, 0.0),
                (0.0, 0.0, 1.0, 1.0),
            )
        )

    with pytest.raises(ValidationError, match="invertible"):
        NormalizationTransform(
            source_to_scene=(
                (1.0, 0.0, 0.0, 0.0),
                (1.0, 0.0, 0.0, 0.0),
                (0.0, 0.0, 1.0, 0.0),
                (0.0, 0.0, 0.0, 1.0),
            )
        )


def test_checkpoint_hash_requires_checkpoint_license():
    with pytest.raises(ValidationError, match="must name a license"):
        PluginProvenance(
            plugin_id="mapanything",
            plugin_version="1",
            upstream_commit="a" * 40,
            config_sha256="b" * 64,
            weight_sha256=("c" * 64,),
            code_license="Apache-2.0",
            checkpoint_license="NO_CHECKPOINT",
        )


def test_checked_in_json_schema_is_canonical():
    schema_path = (
        Path(__file__).parents[2]
        / "packages"
        / "contracts"
        / "schemas"
        / "scene-bundle-v1.schema.json"
    )
    checked_in = json.loads(schema_path.read_text(encoding="utf-8"))
    assert checked_in == scene_bundle_json_schema()
    jsonschema.Draft202012Validator.check_schema(checked_in)


def test_json_schema_validates_serialized_manifest(manifest_factory):
    schema = scene_bundle_json_schema()
    validator = jsonschema.Draft202012Validator(schema)
    payload = manifest_factory().model_dump(mode="json")
    validator.validate(payload)

    payload["camera_convention"] = "colmap_world2cam"
    with pytest.raises(jsonschema.ValidationError):
        validator.validate(payload)
