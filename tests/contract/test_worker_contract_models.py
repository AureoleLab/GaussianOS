from __future__ import annotations

import math
import unittest
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import ValidationError
from jsonschema.validators import Draft202012Validator

from packages.plugin_sdk import (
    ArtifactFile,
    ArtifactManifest,
    ExecutionProfile,
    PluginDistribution,
    PluginManifest,
    QualityCheck,
    QualityReport,
    StageKind,
    StageRequest,
    StageResult,
    StageStatus,
    WorkerEntrypoint,
)
from packages.plugin_sdk.contracts import model_json_schema_bundle


ROOT = Path(__file__).resolve().parents[2]


class WorkerContractModelTests(unittest.TestCase):
    def test_public_schema_bundle_contains_five_versioned_contracts(self) -> None:
        schemas = model_json_schema_bundle()
        self.assertEqual(
            set(schemas),
            {
                "PluginManifest",
                "StageRequest",
                "StageResult",
                "ArtifactManifest",
                "QualityReport",
            },
        )
        for schema in schemas.values():
            self.assertIn("schema_version", schema["properties"])
            Draft202012Validator.check_schema(schema)

    def test_probe_manifest_round_trips_as_versioned_json(self) -> None:
        path = ROOT / "workers" / "contract_probe" / "plugin.json"
        manifest = PluginManifest.model_validate_json(path.read_text(encoding="utf-8"))
        restored = PluginManifest.model_validate_json(manifest.model_dump_json())
        self.assertEqual(restored, manifest)
        self.assertEqual(manifest.schema_version, "1.0.0")

    def test_unknown_contract_fields_are_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            StageRequest(
                run_id="run-1",
                stage_id="probe",
                stage_kind=StageKind.PROBE,
                plugin_id="probe.contract",
                plugin_version="1.0.0",
                profile=ExecutionProfile.PRODUCTION,
                unexpected=True,
            )

    def test_third_party_manifest_requires_full_commit_and_repository(self) -> None:
        with self.assertRaises(ValidationError):
            PluginManifest(
                plugin_id="recon.example",
                display_name="Example",
                plugin_version="1.2.3",
                distribution=PluginDistribution.THIRD_PARTY,
                stage_kinds=(StageKind.RECONSTRUCTION,),
                supported_profiles=(ExecutionProfile.PRODUCTION,),
                entrypoint=WorkerEntrypoint(command=("example",)),
                code_license="Apache-2.0",
            )

    def test_moving_version_names_are_not_exact_locks(self) -> None:
        with self.assertRaises(ValidationError):
            StageRequest(
                run_id="run-1",
                stage_id="probe",
                stage_kind=StageKind.PROBE,
                plugin_id="probe.contract",
                plugin_version="latest",
                profile=ExecutionProfile.PRODUCTION,
            )

    def test_research_only_manifest_cannot_advertise_production(self) -> None:
        with self.assertRaises(ValidationError):
            PluginManifest(
                plugin_id="recon.research",
                display_name="Research",
                plugin_version="1.0.0",
                distribution=PluginDistribution.BUILTIN,
                stage_kinds=(StageKind.RECONSTRUCTION,),
                supported_profiles=(ExecutionProfile.PRODUCTION, ExecutionProfile.RESEARCH),
                research_only=True,
                entrypoint=WorkerEntrypoint(command=("worker",)),
                code_license="LicenseRef-Research-Only",
            )

    def test_artifact_paths_and_quality_metrics_fail_closed(self) -> None:
        with self.assertRaises(ValidationError):
            ArtifactFile(
                relative_path="../escape.bin",
                sha256="0" * 64,
                size_bytes=0,
                media_type="application/octet-stream",
            )
        with self.assertRaises(ValidationError):
            QualityCheck(
                check_id="finite",
                passed=True,
                metrics={"bad": math.inf},
            )

    def test_success_requires_artifact_and_passing_quality_gate(self) -> None:
        now = datetime.now(timezone.utc)
        with self.assertRaises(ValidationError):
            StageResult(
                request_id=uuid4(),
                run_id="run-1",
                stage_id="probe",
                plugin_id="probe.contract",
                plugin_version="1.0.0",
                status=StageStatus.SUCCEEDED,
                started_at=now,
                finished_at=now,
            )

    def test_artifact_manifest_rejects_duplicate_paths(self) -> None:
        file = ArtifactFile(
            relative_path="payload.bin",
            sha256="0" * 64,
            size_bytes=0,
            media_type="application/octet-stream",
        )
        with self.assertRaises(ValidationError):
            ArtifactManifest(
                artifact_id="artifact-1",
                artifact_type="probe",
                format_version="1.0.0",
                producer_plugin_id="probe.contract",
                producer_plugin_version="1.0.0",
                source_request_id=uuid4(),
                source_attempt_id="attempt-1",
                files=(file, file),
            )


if __name__ == "__main__":
    unittest.main()
