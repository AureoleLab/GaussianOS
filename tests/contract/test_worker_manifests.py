from pathlib import Path

from packages.licensing import ProfilePolicyRegistry, evaluate_plugin_policy
from packages.plugin_sdk import ExecutionProfile, PluginManifest


ROOT = Path(__file__).resolve().parents[2]


def _manifests() -> dict[str, PluginManifest]:
    values = {}
    for path in sorted((ROOT / "workers").glob("*/plugin.json")):
        manifest = PluginManifest.model_validate_json(path.read_text(encoding="utf-8"))
        assert manifest.plugin_id not in values
        values[manifest.plugin_id] = manifest
    return values


def test_every_p1_worker_manifest_is_strictly_valid() -> None:
    manifests = _manifests()
    assert {
        "ingest.ffmpeg",
        "frame_qc.builtin",
        "legacy_import.builtin",
        "recon.colmap",
        "recon.mapanything",
        "recon.gluemap",
        "recon.vggt_omega",
        "train.gsplat",
        "train.fastergs",
        "train.improvedgs",
        "preview.brush",
        "export.formats",
    } <= set(manifests)


def test_production_policy_cannot_invoke_research_candidates() -> None:
    registry = ProfilePolicyRegistry.from_directory(ROOT / "configs" / "profiles")
    policy = registry.get(ExecutionProfile.PRODUCTION)
    manifests = _manifests()
    for plugin_id in ("recon.gluemap", "recon.vggt_omega", "train.improvedgs"):
        decision = evaluate_plugin_policy(
            manifests[plugin_id], policy, ExecutionProfile.PRODUCTION
        )
        assert not decision.allowed
        assert any("research-only" in reason for reason in decision.reasons)


def test_locked_production_candidates_pass_host_policy() -> None:
    registry = ProfilePolicyRegistry.from_directory(ROOT / "configs" / "profiles")
    policy = registry.get(ExecutionProfile.PRODUCTION)
    manifests = _manifests()
    for plugin_id in (
        "ingest.ffmpeg",
        "recon.colmap",
        "recon.mapanything",
        "train.gsplat",
        "train.fastergs",
        "preview.brush",
    ):
        decision = evaluate_plugin_policy(manifests[plugin_id], policy, ExecutionProfile.PRODUCTION)
        assert decision.allowed, decision.reasons
