from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
from uuid import uuid4

from packages.artifact_store import ArtifactConflictError, ArtifactStore
from packages.plugin_sdk import ArtifactFile, ArtifactManifest


class ArtifactStoreTransactionTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
