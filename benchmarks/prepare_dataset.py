"""Command-line wrapper for the frozen P1 benchmark input protocol."""

from __future__ import annotations

import argparse
from pathlib import Path

from benchmarks.protocol import prepare_dataset


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("input_root", type=Path)
    parser.add_argument("output_root", type=Path)
    parser.add_argument("--fps", type=float, default=15.0)
    parser.add_argument("--holdout-stride", type=int, default=8)
    parser.add_argument("--holdout-offset", type=int, default=4)
    args = parser.parse_args()
    manifest = prepare_dataset(
        args.input_root,
        args.output_root,
        frames_per_second=args.fps,
        holdout_stride=args.holdout_stride,
        holdout_offset=args.holdout_offset,
    )
    print(manifest.model_dump_json(indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
