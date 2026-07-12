"""Fail-closed execution profile and license gates.

Production authorization is based on a host-owned allow-list as well as the
worker's manifest.  A research worker cannot opt itself into production merely
by changing a field in its own manifest.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Mapping, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from packages.plugin_sdk import (
    ExecutionProfile,
    PluginDistribution,
    PluginManifest,
)


class PluginRequirement(BaseModel):
    """Optional host-owned constraints for a particular allowed plugin."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    allowed_versions: tuple[str, ...] = ()
    allowed_upstream_commits: tuple[str, ...] = ()
    required_code_license: str | None = None
    required_checkpoint_licenses: dict[str, str] = Field(default_factory=dict)
    required_checkpoint_sha256: dict[str, str] = Field(default_factory=dict)
    required_dependency_commits: dict[str, str] = Field(default_factory=dict)

    @field_validator("allowed_versions")
    @classmethod
    def versions_are_explicit(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        forbidden = {"dev", "head", "latest", "main", "master", "nightly"}
        if any(
            not item
            or item.casefold() in forbidden
            or any(character in item for character in "*<>=^~,")
            for item in value
        ):
            raise ValueError("allowed_versions must contain exact versions only")
        return value

    @field_validator("allowed_upstream_commits")
    @classmethod
    def upstream_commits_are_exact(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for commit in value:
            if len(commit) != 40 or any(
                character not in "0123456789abcdef" for character in commit
            ):
                raise ValueError("allowed commits must be full lowercase git SHAs")
        return value

    @field_validator("required_checkpoint_sha256")
    @classmethod
    def checkpoint_hashes_are_exact(cls, value: dict[str, str]) -> dict[str, str]:
        for digest in value.values():
            if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
                raise ValueError("required checkpoint hashes must be lowercase SHA-256")
        return value

    @field_validator("required_dependency_commits")
    @classmethod
    def dependency_commits_are_exact(cls, value: dict[str, str]) -> dict[str, str]:
        for commit in value.values():
            if len(commit) != 40 or any(character not in "0123456789abcdef" for character in commit):
                raise ValueError("required dependency commits must be full lowercase git SHAs")
        return value


class ProfilePolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    schema_version: Literal["1.0.0"] = "1.0.0"
    profile: ExecutionProfile
    allow_plugins: frozenset[str]
    deny_plugins: frozenset[str] = frozenset()
    allow_research_only: bool = False
    allowed_code_licenses: frozenset[str]
    allowed_checkpoint_licenses: frozenset[str]
    require_exact_third_party_provenance: bool = True
    require_profile_lock_for_third_party: bool = True
    plugin_requirements: dict[str, PluginRequirement] = Field(default_factory=dict)

    @field_validator("allow_plugins", "allowed_code_licenses", "allowed_checkpoint_licenses")
    @classmethod
    def required_sets_cannot_contain_wildcards(
        cls, value: frozenset[str]
    ) -> frozenset[str]:
        if not value or any(not item or item == "*" for item in value):
            raise ValueError("policy sets must be non-empty, explicit and wildcard-free")
        return value

    @field_validator("deny_plugins")
    @classmethod
    def deny_set_cannot_contain_wildcards(
        cls, value: frozenset[str]
    ) -> frozenset[str]:
        if any(not item or item == "*" for item in value):
            raise ValueError("deny_plugins must be explicit and wildcard-free")
        return value

    @model_validator(mode="after")
    def policy_is_consistent(self) -> Self:
        overlap = self.allow_plugins & self.deny_plugins
        if overlap:
            raise ValueError(f"plugins cannot be both allowed and denied: {sorted(overlap)}")
        unknown_requirements = set(self.plugin_requirements) - set(self.allow_plugins)
        if unknown_requirements:
            raise ValueError(
                "plugin_requirements reference plugins outside allow_plugins: "
                f"{sorted(unknown_requirements)}"
            )
        if self.profile is ExecutionProfile.PRODUCTION and self.allow_research_only:
            raise ValueError("the production profile can never allow research-only plugins")
        return self


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    allowed: bool
    profile: ExecutionProfile
    plugin_id: str
    reasons: tuple[str, ...]


class PolicyError(PermissionError):
    def __init__(self, decision: PolicyDecision) -> None:
        self.decision = decision
        super().__init__("; ".join(decision.reasons))


def evaluate_plugin_policy(
    manifest: PluginManifest,
    policy: ProfilePolicy,
    requested_profile: ExecutionProfile,
) -> PolicyDecision:
    reasons: list[str] = []

    if requested_profile is not policy.profile:
        reasons.append(
            f"loaded policy is for {policy.profile.value}, not {requested_profile.value}"
        )
    if manifest.plugin_id not in policy.allow_plugins:
        reasons.append(f"plugin {manifest.plugin_id!r} is not on the profile allow-list")
    if manifest.plugin_id in policy.deny_plugins:
        reasons.append(f"plugin {manifest.plugin_id!r} is explicitly denied")
    if requested_profile not in manifest.supported_profiles:
        reasons.append("plugin manifest does not advertise the requested profile")
    if manifest.research_only and not policy.allow_research_only:
        reasons.append("research-only plugins are forbidden by this profile")
    if manifest.code_license not in policy.allowed_code_licenses:
        reasons.append(f"code license {manifest.code_license!r} is not allowed")

    for checkpoint in manifest.checkpoint_assets:
        if checkpoint.license not in policy.allowed_checkpoint_licenses:
            reasons.append(
                f"checkpoint {checkpoint.asset_id!r} license "
                f"{checkpoint.license!r} is not allowed"
            )
    for dependency in manifest.dependency_locks:
        if dependency.code_license not in policy.allowed_code_licenses:
            reasons.append(
                f"dependency {dependency.dependency_id!r} code license "
                f"{dependency.code_license!r} is not allowed"
            )

    if (
        policy.require_exact_third_party_provenance
        and manifest.distribution is PluginDistribution.THIRD_PARTY
        and (manifest.upstream_repository is None or manifest.upstream_commit is None)
    ):
        # PluginManifest already enforces this.  Keep the host policy check as a
        # defense-in-depth invariant should a later contract loosen validation.
        reasons.append("third-party plugin provenance is not exactly pinned")

    requirement = policy.plugin_requirements.get(manifest.plugin_id)
    if (
        policy.require_profile_lock_for_third_party
        and manifest.distribution is PluginDistribution.THIRD_PARTY
        and (
            requirement is None
            or not requirement.allowed_versions
            or not requirement.allowed_upstream_commits
        )
    ):
        reasons.append("third-party plugin has no exact host-owned version/commit lock")
    if requirement is not None:
        if (
            requirement.allowed_versions
            and manifest.plugin_version not in requirement.allowed_versions
        ):
            reasons.append(
                f"plugin version {manifest.plugin_version!r} is not locked by the profile"
            )
        if requirement.allowed_upstream_commits and (
            manifest.upstream_commit not in requirement.allowed_upstream_commits
        ):
            reasons.append("upstream commit is not locked by the profile")
        if (
            requirement.required_code_license is not None
            and manifest.code_license != requirement.required_code_license
        ):
            reasons.append("plugin code license does not match the profile requirement")

        assets = {asset.asset_id: asset for asset in manifest.checkpoint_assets}
        for asset_id, required_license in requirement.required_checkpoint_licenses.items():
            asset = assets.get(asset_id)
            if asset is None:
                reasons.append(f"required checkpoint {asset_id!r} is missing")
            elif asset.license != required_license:
                reasons.append(
                    f"checkpoint {asset_id!r} must use license {required_license!r}"
                )
        for asset_id, required_hash in requirement.required_checkpoint_sha256.items():
            asset = assets.get(asset_id)
            if asset is None:
                reasons.append(f"required checkpoint {asset_id!r} is missing")
            elif asset.sha256 != required_hash:
                reasons.append(f"checkpoint {asset_id!r} SHA-256 is not locked by the profile")
        dependencies = {
            dependency.dependency_id: dependency for dependency in manifest.dependency_locks
        }
        for dependency_id, required_commit in requirement.required_dependency_commits.items():
            dependency = dependencies.get(dependency_id)
            if dependency is None:
                reasons.append(f"required dependency {dependency_id!r} is missing")
            elif dependency.upstream_commit != required_commit:
                reasons.append(
                    f"dependency {dependency_id!r} commit is not locked by the profile"
                )

    return PolicyDecision(
        allowed=not reasons,
        profile=requested_profile,
        plugin_id=manifest.plugin_id,
        reasons=tuple(reasons),
    )


def enforce_plugin_policy(
    manifest: PluginManifest,
    policy: ProfilePolicy,
    requested_profile: ExecutionProfile,
) -> PolicyDecision:
    decision = evaluate_plugin_policy(manifest, policy, requested_profile)
    if not decision.allowed:
        raise PolicyError(decision)
    return decision


def load_profile_policy(path: str | Path) -> ProfilePolicy:
    source = Path(path)
    try:
        payload = source.read_text(encoding="utf-8")
        return ProfilePolicy.model_validate_json(payload)
    except (OSError, ValueError) as exc:
        raise ValueError(f"cannot load profile policy {source}: {exc}") from exc


class ProfilePolicyRegistry:
    """A fail-closed registry: missing profiles never fall back to another one."""

    def __init__(self, policies: Mapping[ExecutionProfile, ProfilePolicy]) -> None:
        self._policies = dict(policies)
        for profile, policy in self._policies.items():
            if profile is not policy.profile:
                raise ValueError("registry key and policy profile differ")

    @classmethod
    def from_directory(cls, directory: str | Path) -> "ProfilePolicyRegistry":
        root = Path(directory)
        policies: dict[ExecutionProfile, ProfilePolicy] = {}
        for profile in ExecutionProfile:
            candidate = root / f"{profile.value}.json"
            if candidate.is_file():
                policy = load_profile_policy(candidate)
                if policy.profile in policies:
                    raise ValueError(f"duplicate policy for {policy.profile.value}")
                policies[policy.profile] = policy
        return cls(policies)

    def get(self, profile: ExecutionProfile) -> ProfilePolicy:
        try:
            return self._policies[profile]
        except KeyError as exc:
            raise KeyError(f"no policy configured for profile {profile.value!r}") from exc

    def enforce(self, manifest: PluginManifest, profile: ExecutionProfile) -> PolicyDecision:
        return enforce_plugin_policy(manifest, self.get(profile), profile)
