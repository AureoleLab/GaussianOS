from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from packages.artifact_store import ArtifactConflictError, ArtifactStore
from packages.plugin_sdk import ArtifactFile, ArtifactManifest


class ArtifactStoreTransactionTests(unittest.TestCase):
    @staticmethod
    def _manifest(
        attempt, request_id, artifact_id: str, payload: bytes
    ) -> ArtifactManifest:
        return ArtifactManifest(
            artifact_id=artifact_id,
            artifact_type="probe",
            format_version="1.0.0",
            producer_plugin_id="probe.contract",
            producer_plugin_version="1.0.0",
            source_request_id=request_id,
            source_attempt_id=attempt.attempt_id,
            files=(
                ArtifactFile(
                    relative_path="payload.bin",
                    sha256=hashlib.sha256(payload).hexdigest(),
                    size_bytes=len(payload),
                    media_type="application/octet-stream",
                ),
            ),
        )

    def test_multi_artifact_conflict_rolls_back_every_publish(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = ArtifactStore(Path(temporary) / "store")
            request_id = uuid4()
            attempt = store.begin_attempt("run-1", "stage-1", str(request_id))
            manifests: list[ArtifactManifest] = []
            for artifact_id, payload in (
                ("artifact-one", b"one"),
                ("artifact-two", b"two"),
            ):
                output = store.artifact_output_path(attempt, artifact_id)
                output.mkdir()
                (output / "payload.bin").write_bytes(payload)
                manifests.append(
                    ArtifactManifest(
                        artifact_id=artifact_id,
                        artifact_type="probe",
                        format_version="1.0.0",
                        producer_plugin_id="probe.contract",
                        producer_plugin_version="1.0.0",
                        source_request_id=request_id,
                        source_attempt_id=attempt.attempt_id,
                        files=(
                            ArtifactFile(
                                relative_path="payload.bin",
                                sha256=hashlib.sha256(payload).hexdigest(),
                                size_bytes=len(payload),
                                media_type="application/octet-stream",
                            ),
                        ),
                    )
                )

            # Simulate a concurrent/existing destination for the second item.
            conflicting = store.artifacts_root / "artifact-two"
            conflicting.mkdir()
            (conflicting / "sentinel.txt").write_text("existing", encoding="utf-8")

            with self.assertRaises(ArtifactConflictError):
                store.commit(attempt, manifests)

            self.assertFalse((store.artifacts_root / "artifact-one").exists())
            self.assertTrue(
                store.artifact_output_path(attempt, "artifact-one").is_dir(),
                "first publish must be rolled back into the private attempt",
            )
            self.assertEqual((conflicting / "sentinel.txt").read_text(), "existing")

    def test_failed_replacement_keeps_the_old_committed_artifact_usable(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            store = ArtifactStore(Path(temporary) / "store")
            artifact_id = "stable-scene"

            old_request = uuid4()
            old_attempt = store.begin_attempt("run-old", "train", str(old_request))
            old_output = store.artifact_output_path(old_attempt, artifact_id)
            old_output.mkdir()
            (old_output / "payload.bin").write_bytes(b"old-valid")
            old_manifest = self._manifest(
                old_attempt, old_request, artifact_id, b"old-valid"
            )
            store.commit(old_attempt, [old_manifest])

            new_request = uuid4()
            new_attempt = store.begin_attempt("run-new", "train", str(new_request))
            new_output = store.artifact_output_path(new_attempt, artifact_id)
            new_output.mkdir()
            (new_output / "payload.bin").write_bytes(b"new-uncommitted")
            new_manifest = self._manifest(
                new_attempt, new_request, artifact_id, b"new-uncommitted"
            )

            with self.assertRaises(ArtifactConflictError):
                store.commit(new_attempt, [new_manifest])

            committed = store.artifacts_root / artifact_id
            self.assertEqual(
                (committed / "payload.bin").read_bytes(), b"old-valid"
            )
            self.assertEqual(
                store.read_manifest(artifact_id).files[0].sha256,
                hashlib.sha256(b"old-valid").hexdigest(),
            )
            self.assertTrue(new_output.is_dir())


if __name__ == "__main__":
    unittest.main()
