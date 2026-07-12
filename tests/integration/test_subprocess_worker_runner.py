from __future__ import annotations

import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from packages.artifact_store import ArtifactStore
from packages.licensing import ProfilePolicy, ProfilePolicyRegistry
from packages.pipeline import CancellationToken, SubprocessWorkerRunner
from packages.plugin_sdk import (
    ErrorCode,
    ExecutionProfile,
    PluginManifest,
    StageKind,
    StageRequest,
    StageStatus,
)


ROOT = Path(__file__).resolve().parents[2]


class SubprocessWorkerRunnerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.store = ArtifactStore(Path(self.temporary.name) / "store")
        policy = ProfilePolicy(
            profile=ExecutionProfile.PRODUCTION,
            allow_plugins=frozenset({"probe.contract"}),
            deny_plugins=frozenset(),
            allow_research_only=False,
            allowed_code_licenses=frozenset({"Apache-2.0"}),
            allowed_checkpoint_licenses=frozenset({"Apache-2.0"}),
        )
        registry = ProfilePolicyRegistry({ExecutionProfile.PRODUCTION: policy})
        manifest_path = ROOT / "workers" / "contract_probe" / "plugin.json"
        self.manifest = PluginManifest.model_validate_json(
            manifest_path.read_text(encoding="utf-8")
        )
        self.runner = SubprocessWorkerRunner(
            self.store,
            registry,
            worker_cwd=ROOT,
            poll_interval_seconds=0.01,
            cancellation_grace_seconds=0.1,
        )

    def request(self, **config: object) -> StageRequest:
        return StageRequest(
            run_id="integration-run",
            stage_id="probe-stage",
            stage_kind=StageKind.PROBE,
            plugin_id=self.manifest.plugin_id,
            plugin_version=self.manifest.plugin_version,
            profile=ExecutionProfile.PRODUCTION,
            config=dict(config),
        )

    def test_success_validates_and_atomically_commits_artifact(self) -> None:
        outcome = self.runner.run(
            self.request(payload="verified"), self.manifest, timeout_seconds=5
        )
        self.assertEqual(outcome.result.status, StageStatus.SUCCEEDED)
        self.assertEqual(outcome.return_code, 0)
        self.assertEqual(len(outcome.committed_artifacts), 1)
        record = outcome.committed_artifacts[0]
        self.assertEqual((record.path / "payload.txt").read_text(), "verified")
        restored = self.store.read_manifest(record.artifact_id)
        self.assertEqual(restored.artifact_id, record.artifact_id)
        self.assertIsNotNone(outcome.attempt_archive)
        self.assertTrue(outcome.attempt_archive.is_dir())
        self.assertFalse(any(self.store.attempts_root.rglob("attempt-*")))

    def test_bad_hash_never_publishes_artifact(self) -> None:
        outcome = self.runner.run(
            self.request(mode="bad_hash"), self.manifest, timeout_seconds=5
        )
        self.assertEqual(outcome.result.status, StageStatus.FAILED)
        self.assertEqual(outcome.result.error.code, ErrorCode.OUTPUT_VALIDATION_FAILED)
        self.assertFalse(any(self.store.artifacts_root.iterdir()))
        self.assertTrue((outcome.attempt_archive / "outputs").is_dir())

    def test_undeclared_output_never_publishes_artifact(self) -> None:
        outcome = self.runner.run(
            self.request(mode="undeclared_file"), self.manifest, timeout_seconds=5
        )
        self.assertEqual(outcome.result.error.code, ErrorCode.OUTPUT_VALIDATION_FAILED)
        self.assertFalse(any(self.store.artifacts_root.iterdir()))

    def test_worker_crash_is_contained_and_coded(self) -> None:
        outcome = self.runner.run(
            self.request(mode="crash"), self.manifest, timeout_seconds=5
        )
        self.assertEqual(outcome.result.error.code, ErrorCode.WORKER_CRASHED)
        self.assertNotEqual(outcome.return_code, 0)
        self.assertFalse(any(self.store.artifacts_root.iterdir()))

    def test_cuda_oom_is_reported_without_host_failure(self) -> None:
        outcome = self.runner.run(
            self.request(mode="cuda_oom"), self.manifest, timeout_seconds=5
        )
        self.assertEqual(outcome.result.error.code, ErrorCode.CUDA_OOM)
        self.assertFalse(any(self.store.artifacts_root.iterdir()))

    def test_timeout_cancels_then_terminates_worker(self) -> None:
        outcome = self.runner.run(
            self.request(delay_seconds=3.0), self.manifest, timeout_seconds=0.1
        )
        self.assertEqual(outcome.result.status, StageStatus.FAILED)
        self.assertEqual(outcome.result.error.code, ErrorCode.TIMEOUT)
        self.assertFalse(any(self.store.artifacts_root.iterdir()))

    def test_explicit_cancellation_is_distinct_from_timeout(self) -> None:
        token = CancellationToken()
        timer = threading.Timer(0.1, token.cancel, args=("test cancellation",))
        timer.start()
        self.addCleanup(timer.cancel)
        outcome = self.runner.run(
            self.request(delay_seconds=3.0),
            self.manifest,
            timeout_seconds=5,
            cancellation_token=token,
        )
        timer.join(timeout=1)
        self.assertEqual(outcome.result.status, StageStatus.CANCELLED)
        self.assertEqual(outcome.result.error.code, ErrorCode.CANCELLED)
        self.assertFalse(any(self.store.artifacts_root.iterdir()))

    def test_pre_cancelled_request_never_creates_an_attempt(self) -> None:
        token = CancellationToken()
        token.cancel("cancel before launch")
        outcome = self.runner.run(
            self.request(delay_seconds=3.0),
            self.manifest,
            timeout_seconds=5,
            cancellation_token=token,
        )
        self.assertEqual(outcome.result.status, StageStatus.CANCELLED)
        self.assertEqual(outcome.result.error.code, ErrorCode.CANCELLED)
        self.assertFalse(any(self.store.attempts_root.rglob("attempt-*")))

    def test_expired_request_deadline_never_launches_worker(self) -> None:
        request = self.request().model_copy(
            update={"deadline_utc": datetime.now(timezone.utc) - timedelta(seconds=1)}
        )
        outcome = self.runner.run(request, self.manifest, timeout_seconds=5)
        self.assertEqual(outcome.result.error.code, ErrorCode.TIMEOUT)
        self.assertFalse(any(self.store.attempts_root.rglob("attempt-*")))

    def test_invalid_json_result_is_rejected(self) -> None:
        outcome = self.runner.run(
            self.request(mode="invalid_json"), self.manifest, timeout_seconds=5
        )
        self.assertEqual(outcome.result.error.code, ErrorCode.INVALID_RESULT)
        self.assertFalse(any(self.store.artifacts_root.iterdir()))

    def test_worker_reported_failure_preserves_explicit_error_code(self) -> None:
        outcome = self.runner.run(
            self.request(mode="reported_failure"), self.manifest, timeout_seconds=5
        )
        self.assertEqual(outcome.result.status, StageStatus.FAILED)
        self.assertEqual(outcome.result.error.code, ErrorCode.DEPENDENCY_MISSING)
        self.assertEqual(outcome.return_code, 10)


if __name__ == "__main__":
    unittest.main()
