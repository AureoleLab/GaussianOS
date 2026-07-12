from __future__ import annotations

import pytest

from benchmarks.protocol import frame_split


def test_holdout_split_is_fixed_and_sparse() -> None:
    splits = [frame_split(index, holdout_stride=8, holdout_offset=4) for index in range(20)]
    assert [index for index, split in enumerate(splits) if split == "holdout"] == [4, 12]


def test_invalid_holdout_offset_is_rejected() -> None:
    with pytest.raises(ValueError, match="holdout_offset"):
        frame_split(0, holdout_stride=8, holdout_offset=8)
