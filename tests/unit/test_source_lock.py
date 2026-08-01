from __future__ import annotations

from pathlib import Path

import pytest

from packages.source_lock import source_tree_sha256, verify_source_lock


def test_pruned_portable_source_uses_tree_hash_without_parent_git(tmp_path: Path) -> None:
    source = tmp_path / "portable source (中文)"
    source.mkdir()
    (source / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
    digest = source_tree_sha256(source)

    method = verify_source_lock(
        source,
        expected_commit="0" * 40,
        expected_tree_sha256=digest,
        label="fixture",
    )

    assert method == "tree_sha256"


def test_pruned_portable_source_rejects_tree_changes(tmp_path: Path) -> None:
    source = tmp_path / "source"
    source.mkdir()
    (source / "module.py").write_text("VALUE = 1\n", encoding="utf-8")

    with pytest.raises(RuntimeError, match="tree hash mismatch"):
        verify_source_lock(
            source,
            expected_commit="0" * 40,
            expected_tree_sha256="0" * 64,
            label="fixture",
        )
