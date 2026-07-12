from __future__ import annotations

import json
import unittest
from pathlib import Path

from packages.licensing import PolicyError, ProfilePolicyRegistry
from packages.plugin_sdk import ExecutionProfile, PluginManifest


ROOT = Path(__file__).resolve().parents[2]


def manifest_from_payload(**overrides: object) -> PluginManifest:
    payload: dict[str, object] = {
        "schema_version": "1.0.0",
        "plugin_id": "recon.mapanything",
        "display_name": "MapAnything",
        "plugin_version": "v1.1.2",
        "distribution": "third_party",
        "stage_kinds": ["reconstruction"],
        "supported_profiles": ["production", "research"],
        "research_only": False,
        "entrypoint": {
            "command": ["mapanything-worker"],
            "protocol": "file-json-v1",
            "environment": {},
        },
        "supported_request_versions": ["1.0.0"],
        "supported_result_versions": ["1.0.0"],
        "code_license": "Apache-2.0",
        "upstream_repository": "https://example.invalid/mapanything.git",
        "upstream_commit": "c845b8f4f6cde0c20aecd87573656c3f69f5b2b0",
        "checkpoint_assets": [
            {
                "asset_id": "mapanything-apache",
                "sha256": "fa06c0fdccefc5048e072c85935d5789b1e36b307f3859033c17f9dcb9fd5201",
                "license": "Apache-2.0",
                "source_url": "https://example.invalid/model.safetensors",
            },
            {
                "asset_id": "dinov2-vitg14",
                "sha256": "baf8467e50af277596bbbafa06887c177ee899ab46033649c383577d7e9309d3",
                "license": "Apache-2.0",
                "source_url": "https://example.invalid/dinov2_vitg14_pretrain.pth",
            }
        ],
        "dependency_locks": [
            {
                "dependency_id": "colmap-ba",
                "version": "3.13.0",
                "upstream_repository": "https://github.com/colmap/colmap",
                "upstream_commit": "0b31f98133b470eae62811b557dc2bcff1e4f9a5",
                "code_license": "BSD-3-Clause",
            },
            {
                "dependency_id": "dinov2",
                "version": "commit-2026-07-12",
                "upstream_repository": "https://github.com/facebookresearch/dinov2",
                "upstream_commit": "7764ea0f912e53c92e82eb78a2a1631e92725fc8",
                "code_license": "Apache-2.0",
            },
            {
                "dependency_id": "uniception",
                "version": "v0.1.7",
                "upstream_repository": "https://github.com/castacks/UniCeption",
                "upstream_commit": "802ebc1783d71bbaa9d139c88d87d062ad18ce62",
                "code_license": "BSD-3-Clause",
            },
            {
                "dependency_id": "open3d",
                "version": "v0.19.0",
                "upstream_repository": "https://github.com/isl-org/Open3D",
                "upstream_commit": "1e7b17438687a0b0c1e5a7187321ac7044afe275",
                "code_license": "MIT",
            },
            {
                "dependency_id": "pycolmap",
                "version": "3.13.0",
                "upstream_repository": "https://github.com/colmap/colmap",
                "upstream_commit": "0b31f98133b470eae62811b557dc2bcff1e4f9a5",
                "code_license": "BSD-3-Clause",
            }
        ],
    }
    payload.update(overrides)
    return PluginManifest.model_validate_json(json.dumps(payload))


class ProfilePolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.registry = ProfilePolicyRegistry.from_directory(ROOT / "configs" / "profiles")

    def test_mapanything_apache_checkpoint_is_allowed_in_production(self) -> None:
        decision = self.registry.enforce(
            manifest_from_payload(), ExecutionProfile.PRODUCTION
        )
        self.assertTrue(decision.allowed)

    def test_mapanything_non_apache_checkpoint_is_denied_in_production(self) -> None:
        manifest = manifest_from_payload(
            checkpoint_assets=[
                {
                    "asset_id": "mapanything-apache",
                    "sha256": "c" * 64,
                    "license": "LicenseRef-Research-Only",
                    "source_url": None,
                }
            ]
        )
        with self.assertRaises(PolicyError) as caught:
            self.registry.enforce(manifest, ExecutionProfile.PRODUCTION)
        self.assertIn("checkpoint", str(caught.exception))

    def test_production_denylist_blocks_research_plugin_even_if_manifest_lies(self) -> None:
        manifest = manifest_from_payload(
            plugin_id="recon.gluemap",
            display_name="GLUEMAP",
            distribution="builtin",
            upstream_repository=None,
            upstream_commit=None,
            checkpoint_assets=[],
            dependency_locks=[],
            supported_profiles=["production"],
            research_only=False,
        )
        with self.assertRaises(PolicyError) as caught:
            self.registry.enforce(manifest, ExecutionProfile.PRODUCTION)
        self.assertIn("explicitly denied", str(caught.exception))

    def test_research_profile_can_run_locked_research_only_plugin(self) -> None:
        manifest = manifest_from_payload(
            plugin_id="train.improvedgs",
            display_name="ImprovedGS",
            plugin_version="commit-2026-06-05",
            upstream_repository="https://github.com/XiaoBin2001/Improved-GS",
            upstream_commit="20b5db343a87c2f9fb4b70c6e39ff1f042a8a47a",
            stage_kinds=["training"],
            supported_profiles=["research"],
            research_only=True,
            code_license="LicenseRef-ImprovedGS-NonCommercial-Research",
            checkpoint_assets=[],
            dependency_locks=[],
        )
        decision = self.registry.enforce(manifest, ExecutionProfile.RESEARCH)
        self.assertTrue(decision.allowed)

    def test_research_profile_keeps_unclosed_gluemap_disabled(self) -> None:
        manifest = manifest_from_payload(
            plugin_id="recon.gluemap",
            display_name="GLUEMAP",
            plugin_version="0.1.0+commit-2026-06-22",
            upstream_repository="https://github.com/colmap/gluemap",
            upstream_commit="adc9e4bb5f41014d3f7c157a879edc278588c829",
            supported_profiles=["research"],
            research_only=True,
            code_license="BSD-3-Clause",
            checkpoint_assets=[],
            dependency_locks=[],
        )
        with self.assertRaises(PolicyError):
            self.registry.enforce(manifest, ExecutionProfile.RESEARCH)

    def test_checkpoint_hash_must_match_host_owned_lock(self) -> None:
        manifest = manifest_from_payload(
            checkpoint_assets=[
                {
                    "asset_id": "mapanything-apache",
                    "sha256": "d" * 64,
                    "license": "Apache-2.0",
                    "source_url": None,
                }
            ]
        )
        with self.assertRaises(PolicyError) as caught:
            self.registry.enforce(manifest, ExecutionProfile.PRODUCTION)
        self.assertIn("SHA-256", str(caught.exception))

    def test_unlocked_plugin_version_is_denied(self) -> None:
        manifest = manifest_from_payload(plugin_version="v1.1.1")
        with self.assertRaises(PolicyError) as caught:
            self.registry.enforce(manifest, ExecutionProfile.PRODUCTION)
        self.assertIn("version", str(caught.exception))

    def test_fastergs_requires_locked_nerficg_dependency(self) -> None:
        manifest = manifest_from_payload(
            plugin_id="train.fastergs",
            display_name="Faster-GS",
            plugin_version="commit-2026-07-11",
            stage_kinds=["training"],
            upstream_repository="https://github.com/nerficg-project/faster-gaussian-splatting",
            upstream_commit="ae2bf807314401c83fc18ba577981c91112058f9",
            checkpoint_assets=[],
            dependency_locks=[],
        )
        with self.assertRaises(PolicyError) as caught:
            self.registry.enforce(manifest, ExecutionProfile.PRODUCTION)
        self.assertIn("nerficg-framework", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
