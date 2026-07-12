"""Stable, dependency-light contracts shared by the host and workers.

Algorithm workers may depend on this package.  The orchestration process must
never import a worker package directly; it exchanges these models as JSON.
"""

from .contracts import (
    CONTRACT_VERSION,
    ArtifactFile,
    ArtifactManifest,
    ArtifactReference,
    CheckpointAsset,
    DependencyLock,
    ErrorCode,
    ExecutionProfile,
    PluginDistribution,
    PluginManifest,
    QualityCheck,
    QualityReport,
    StageError,
    StageKind,
    StageRequest,
    StageResult,
    StageStatus,
    WorkerEntrypoint,
    model_json_schema_bundle,
)

__all__ = [
    "ArtifactFile",
    "ArtifactManifest",
    "ArtifactReference",
    "CheckpointAsset",
    "CONTRACT_VERSION",
    "DependencyLock",
    "ErrorCode",
    "ExecutionProfile",
    "PluginDistribution",
    "PluginManifest",
    "QualityCheck",
    "QualityReport",
    "StageError",
    "StageKind",
    "StageRequest",
    "StageResult",
    "StageStatus",
    "WorkerEntrypoint",
    "model_json_schema_bundle",
]
