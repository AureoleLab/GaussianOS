"""Pydantic v2 definitions for the file based worker protocol.

The protocol deliberately contains no Python object or pickle transport.  A
request and result can therefore be validated without importing the algorithm
implementation that produced it.
"""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any, ClassVar, Literal, Self
from uuid import UUID, uuid4

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    field_validator,
    model_validator,
)


CONTRACT_VERSION = "1.0.0"
ContractVersion = Literal["1.0.0"]
SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")
COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
IDENTIFIER_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]{0,127}$")
VERSION_PATTERN = re.compile(r"^[0-9A-Za-z][0-9A-Za-z._+-]{0,63}$")
MOVING_VERSION_NAMES = frozenset({"dev", "head", "latest", "main", "master", "nightly"})


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _validate_identifier(value: str, label: str) -> str:
    if not IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(
            f"{label} must be a lowercase stable identifier containing only "
            "letters, digits, '.', '_' or '-'"
        )
    return value


def _validate_exact_version(value: str, label: str) -> str:
    if (
        not VERSION_PATTERN.fullmatch(value)
        or value.casefold() in MOVING_VERSION_NAMES
        or "*" in value
    ):
        raise ValueError(f"{label} must be a pinned tag or opaque version")
    return value


def _validate_json_value(value: Any, label: str) -> Any:
    """Reject values that JSON cannot faithfully carry, including NaN/Inf."""

    try:
        json.dumps(value, allow_nan=False, separators=(",", ":"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} must contain finite JSON values only") from exc
    return value


class ContractModel(BaseModel):
    """Strict base class for every serialized contract model."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        strict=True,
        str_strip_whitespace=True,
        use_enum_values=False,
    )

    schema_version: ContractVersion = CONTRACT_VERSION


class ExecutionProfile(StrEnum):
    PRODUCTION = "production"
    RESEARCH = "research"


class PluginDistribution(StrEnum):
    BUILTIN = "builtin"
    THIRD_PARTY = "third_party"


class StageKind(StrEnum):
    INGEST = "ingest"
    FRAME_QC = "frame_qc"
    LEGACY_IMPORT = "legacy_import"
    RECONSTRUCTION = "reconstruction"
    TRAINING = "training"
    PREVIEW = "preview"
    EXPORT = "export"
    COMPATIBILITY = "compatibility"
    PROBE = "probe"


class StageStatus(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ErrorCode(StrEnum):
    INVALID_REQUEST = "invalid_request"
    POLICY_DENIED = "policy_denied"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    WORKER_CRASHED = "worker_crashed"
    CUDA_OOM = "cuda_oom"
    DEPENDENCY_MISSING = "dependency_missing"
    INVALID_RESULT = "invalid_result"
    OUTPUT_VALIDATION_FAILED = "output_validation_failed"
    ARTIFACT_COMMIT_FAILED = "artifact_commit_failed"
    INTERNAL_ERROR = "internal_error"


class WorkerEntrypoint(BaseModel):
    """A shell-free command executed in a dedicated subprocess.

    ``{python}`` is the only command placeholder interpreted by the host.  The
    host appends ``--request-json`` and ``--result-json`` arguments.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    command: tuple[str, ...] = Field(min_length=1)
    protocol: Literal["file-json-v1"] = "file-json-v1"
    environment: dict[str, str] = Field(default_factory=dict)

    @field_validator("command")
    @classmethod
    def command_items_are_safe(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if any(not part or "\x00" in part for part in value):
            raise ValueError("entrypoint command items must be non-empty and NUL-free")
        if value.count("{python}") > 1:
            raise ValueError("entrypoint may contain {python} at most once")
        return value

    @field_validator("environment")
    @classmethod
    def environment_is_plain_text(cls, value: dict[str, str]) -> dict[str, str]:
        for key, item in value.items():
            if not key or "=" in key or "\x00" in key or "\x00" in item:
                raise ValueError("invalid environment key or value")
        return value


class CheckpointAsset(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    asset_id: str
    sha256: str
    license: str = Field(min_length=1, max_length=128)
    source_url: HttpUrl | None = None

    @field_validator("asset_id")
    @classmethod
    def asset_id_is_stable(cls, value: str) -> str:
        return _validate_identifier(value, "asset_id")

    @field_validator("sha256")
    @classmethod
    def sha256_is_lower_hex(cls, value: str) -> str:
        if not SHA256_PATTERN.fullmatch(value):
            raise ValueError("sha256 must contain exactly 64 lowercase hex characters")
        return value


class DependencyLock(BaseModel):
    """Exact provenance for a third-party project bundled behind a worker."""

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    dependency_id: str
    version: str
    upstream_repository: HttpUrl
    upstream_commit: str
    code_license: str = Field(min_length=1, max_length=128)

    @field_validator("dependency_id")
    @classmethod
    def dependency_id_is_stable(cls, value: str) -> str:
        return _validate_identifier(value, "dependency_id")

    @field_validator("version")
    @classmethod
    def version_is_exact(cls, value: str) -> str:
        return _validate_exact_version(value, "dependency version")

    @field_validator("upstream_commit")
    @classmethod
    def commit_is_exact(cls, value: str) -> str:
        if not COMMIT_PATTERN.fullmatch(value):
            raise ValueError("dependency commit must be a full lowercase git SHA")
        return value


class PluginManifest(ContractModel):
    """Immutable identity, provenance, licensing and launch metadata."""

    plugin_id: str
    display_name: str = Field(min_length=1, max_length=160)
    plugin_version: str
    distribution: PluginDistribution
    stage_kinds: tuple[StageKind, ...] = Field(min_length=1)
    supported_profiles: tuple[ExecutionProfile, ...] = Field(min_length=1)
    research_only: bool = False
    entrypoint: WorkerEntrypoint
    supported_request_versions: tuple[ContractVersion, ...] = (CONTRACT_VERSION,)
    supported_result_versions: tuple[ContractVersion, ...] = (CONTRACT_VERSION,)
    code_license: str = Field(min_length=1, max_length=128)
    upstream_repository: HttpUrl | None = None
    upstream_commit: str | None = None
    checkpoint_assets: tuple[CheckpointAsset, ...] = ()
    dependency_locks: tuple[DependencyLock, ...] = ()

    @field_validator("plugin_id")
    @classmethod
    def plugin_id_is_stable(cls, value: str) -> str:
        return _validate_identifier(value, "plugin_id")

    @field_validator("plugin_version")
    @classmethod
    def version_is_exact(cls, value: str) -> str:
        return _validate_exact_version(value, "plugin_version")

    @field_validator("upstream_commit")
    @classmethod
    def commit_is_exact(cls, value: str | None) -> str | None:
        if value is not None and not COMMIT_PATTERN.fullmatch(value):
            raise ValueError("upstream_commit must be a full 40-character lowercase git SHA")
        return value

    @model_validator(mode="after")
    def provenance_and_profile_invariants(self) -> Self:
        if len(set(self.stage_kinds)) != len(self.stage_kinds):
            raise ValueError("stage_kinds cannot contain duplicates")
        if len(set(self.supported_profiles)) != len(self.supported_profiles):
            raise ValueError("supported_profiles cannot contain duplicates")
        if len(set(self.supported_request_versions)) != len(
            self.supported_request_versions
        ) or len(set(self.supported_result_versions)) != len(
            self.supported_result_versions
        ):
            raise ValueError("supported contract version lists cannot contain duplicates")
        asset_ids = [asset.asset_id for asset in self.checkpoint_assets]
        if len(asset_ids) != len(set(asset_ids)):
            raise ValueError("checkpoint asset_id values must be unique")
        dependency_ids = [item.dependency_id for item in self.dependency_locks]
        if len(dependency_ids) != len(set(dependency_ids)):
            raise ValueError("dependency_id values must be unique")
        if self.distribution is PluginDistribution.THIRD_PARTY:
            if self.upstream_repository is None or self.upstream_commit is None:
                raise ValueError(
                    "third-party plugins require upstream_repository and an exact upstream_commit"
                )
        if self.research_only:
            if ExecutionProfile.PRODUCTION in self.supported_profiles:
                raise ValueError("research-only plugins cannot advertise production support")
            if ExecutionProfile.RESEARCH not in self.supported_profiles:
                raise ValueError("research-only plugins must support the research profile")
        return self


class ArtifactReference(ContractModel):
    artifact_id: str
    artifact_type: str
    location: str = Field(min_length=1)
    manifest_sha256: str

    @field_validator("artifact_id", "artifact_type")
    @classmethod
    def identifiers_are_stable(cls, value: str, info: Any) -> str:
        return _validate_identifier(value, info.field_name)

    @field_validator("manifest_sha256")
    @classmethod
    def manifest_hash_is_valid(cls, value: str) -> str:
        if not SHA256_PATTERN.fullmatch(value):
            raise ValueError("manifest_sha256 must be lowercase SHA-256")
        return value


class StageRequest(ContractModel):
    request_id: UUID = Field(default_factory=uuid4)
    run_id: str
    stage_id: str
    stage_kind: StageKind
    plugin_id: str
    plugin_version: str
    profile: ExecutionProfile
    config: dict[str, Any] = Field(default_factory=dict)
    inputs: tuple[ArtifactReference, ...] = ()
    attempt_id: str | None = None
    attempt_dir: str | None = None
    cancellation_file: str | None = None
    deadline_utc: datetime | None = None

    @field_validator("run_id", "stage_id", "plugin_id")
    @classmethod
    def identifiers_are_stable(cls, value: str, info: Any) -> str:
        return _validate_identifier(value, info.field_name)

    @field_validator("plugin_version")
    @classmethod
    def version_is_exact(cls, value: str) -> str:
        return _validate_exact_version(value, "plugin_version")

    @field_validator("attempt_id")
    @classmethod
    def attempt_id_is_stable(cls, value: str | None) -> str | None:
        if value is not None:
            return _validate_identifier(value, "attempt_id")
        return value

    @field_validator("config")
    @classmethod
    def config_is_json(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_json_value(value, "config")

    @field_validator("deadline_utc")
    @classmethod
    def deadline_has_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("deadline_utc must be timezone-aware")
        return value

    @model_validator(mode="after")
    def runtime_paths_are_all_or_none(self) -> Self:
        runtime_values = (self.attempt_id, self.attempt_dir, self.cancellation_file)
        if any(item is None for item in runtime_values) and any(
            item is not None for item in runtime_values
        ):
            raise ValueError(
                "attempt_id, attempt_dir and cancellation_file must be supplied together"
            )
        input_ids = [item.artifact_id for item in self.inputs]
        if len(input_ids) != len(set(input_ids)):
            raise ValueError("input artifact_id values must be unique")
        return self


class ArtifactFile(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    relative_path: str
    sha256: str
    size_bytes: int = Field(ge=0)
    media_type: str = Field(min_length=1, max_length=160)

    @field_validator("relative_path")
    @classmethod
    def path_is_relative_and_portable(cls, value: str) -> str:
        path = PurePosixPath(value)
        if (
            not value
            or value == "."
            or "\\" in value
            or path.is_absolute()
            or any(part in {"", ".", ".."} for part in value.split("/"))
            or value == "artifact.manifest.json"
        ):
            raise ValueError("relative_path must be a safe POSIX path inside the artifact")
        return value

    @field_validator("sha256")
    @classmethod
    def hash_is_valid(cls, value: str) -> str:
        if not SHA256_PATTERN.fullmatch(value):
            raise ValueError("sha256 must be lowercase SHA-256")
        return value


class ArtifactManifest(ContractModel):
    artifact_id: str
    artifact_type: str
    format_version: str = Field(min_length=1, max_length=64)
    producer_plugin_id: str
    producer_plugin_version: str
    source_request_id: UUID
    source_attempt_id: str
    files: tuple[ArtifactFile, ...] = Field(min_length=1)
    created_at: datetime = Field(default_factory=utc_now)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator(
        "artifact_id", "artifact_type", "producer_plugin_id", "source_attempt_id"
    )
    @classmethod
    def identifiers_are_stable(cls, value: str, info: Any) -> str:
        return _validate_identifier(value, info.field_name)

    @field_validator("producer_plugin_version")
    @classmethod
    def version_is_exact(cls, value: str) -> str:
        return _validate_exact_version(value, "producer_plugin_version")

    @field_validator("metadata")
    @classmethod
    def metadata_is_json(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_json_value(value, "metadata")

    @field_validator("created_at")
    @classmethod
    def created_at_has_timezone(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("created_at must be timezone-aware")
        return value

    @model_validator(mode="after")
    def file_paths_are_unique(self) -> Self:
        paths = [item.relative_path for item in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("artifact file paths must be unique")
        return self


class QualityCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    check_id: str
    passed: bool
    required: bool = True
    message: str = ""
    metrics: dict[str, float] = Field(default_factory=dict)

    @field_validator("check_id")
    @classmethod
    def check_id_is_stable(cls, value: str) -> str:
        return _validate_identifier(value, "check_id")

    @field_validator("metrics")
    @classmethod
    def metrics_are_finite(cls, value: dict[str, float]) -> dict[str, float]:
        if any(not math.isfinite(item) for item in value.values()):
            raise ValueError("quality metrics must be finite")
        return value


class QualityReport(ContractModel):
    report_id: UUID = Field(default_factory=uuid4)
    passed: bool
    checks: tuple[QualityCheck, ...]
    metrics: dict[str, float] = Field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    @field_validator("metrics")
    @classmethod
    def metrics_are_finite(cls, value: dict[str, float]) -> dict[str, float]:
        if any(not math.isfinite(item) for item in value.values()):
            raise ValueError("quality metrics must be finite")
        return value

    @model_validator(mode="after")
    def gate_matches_required_checks(self) -> Self:
        check_ids = [item.check_id for item in self.checks]
        if len(check_ids) != len(set(check_ids)):
            raise ValueError("quality check_id values must be unique")
        expected = all(item.passed for item in self.checks if item.required)
        if self.passed is not expected:
            raise ValueError("passed must equal the result of all required checks")
        return self


class StageError(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)

    code: ErrorCode
    message: str = Field(min_length=1, max_length=4000)
    retryable: bool = False
    details: dict[str, Any] = Field(default_factory=dict)

    @field_validator("details")
    @classmethod
    def details_are_json(cls, value: dict[str, Any]) -> dict[str, Any]:
        return _validate_json_value(value, "error details")


class StageResult(ContractModel):
    request_id: UUID
    run_id: str
    stage_id: str
    plugin_id: str
    plugin_version: str
    status: StageStatus
    started_at: datetime
    finished_at: datetime
    artifacts: tuple[ArtifactManifest, ...] = ()
    quality_report: QualityReport | None = None
    error: StageError | None = None

    _terminal_statuses: ClassVar[set[StageStatus]] = {
        StageStatus.SUCCEEDED,
        StageStatus.FAILED,
        StageStatus.CANCELLED,
    }

    @field_validator("run_id", "stage_id", "plugin_id")
    @classmethod
    def identifiers_are_stable(cls, value: str, info: Any) -> str:
        return _validate_identifier(value, info.field_name)

    @field_validator("plugin_version")
    @classmethod
    def version_is_exact(cls, value: str) -> str:
        return _validate_exact_version(value, "plugin_version")

    @field_validator("started_at", "finished_at")
    @classmethod
    def timestamps_have_timezone(cls, value: datetime, info: Any) -> datetime:
        if value.tzinfo is None:
            raise ValueError(f"{info.field_name} must be timezone-aware")
        return value

    @model_validator(mode="after")
    def result_invariants(self) -> Self:
        if self.finished_at < self.started_at:
            raise ValueError("finished_at cannot precede started_at")
        artifact_ids = [artifact.artifact_id for artifact in self.artifacts]
        if len(artifact_ids) != len(set(artifact_ids)):
            raise ValueError("result artifact_id values must be unique")

        if self.status is StageStatus.SUCCEEDED:
            if self.error is not None:
                raise ValueError("a succeeded result cannot contain an error")
            if not self.artifacts:
                raise ValueError("a succeeded result must declare at least one artifact")
            if self.quality_report is None or not self.quality_report.passed:
                raise ValueError("a succeeded result requires a passing quality report")
        else:
            if self.error is None:
                raise ValueError("failed and cancelled results require an error")
            if self.artifacts:
                raise ValueError("non-success results cannot publish artifacts")
            if self.status is StageStatus.CANCELLED and self.error.code is not ErrorCode.CANCELLED:
                raise ValueError("cancelled results must use the cancelled error code")
        return self


def model_json_schema_bundle() -> dict[str, dict[str, Any]]:
    """Return the five public JSON Schemas requested by Worker Contract v1."""

    return {
        model.__name__: model.model_json_schema(mode="serialization")
        for model in (
            PluginManifest,
            StageRequest,
            StageResult,
            ArtifactManifest,
            QualityReport,
        )
    }
