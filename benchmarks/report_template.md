# P1 benchmark run report

Status values are `PASS`, `FAILED`, `BLOCKED`, or `NOT_RUN`.  Do not replace a
non-numeric status with zero.

## Run identity

| Field | Value |
|---|---|
| Experiment id | |
| Attempt id | |
| Status | |
| Dataset id | `sha256:152be2c9901a8652daa032ab5c35a65aaf3aa83fc1deb1a1afa41a2a2a3ab33d` |
| Scene id | |
| Profile | production / research / reference |
| Reconstruction plugin / commit | |
| Trainer plugin / commit | |
| Checkpoint file / SHA-256 / license | |
| Config SHA-256 | |
| StageRequest SHA-256 | |
| StageResult SHA-256 | |
| GPU / driver / CUDA / PyTorch | |
| Start / end UTC | |
| Failure code and message | |

## Reconstruction metrics

| Metric | Value | Unit / exact convention | Evidence artifact |
|---|---:|---|---|
| Frozen train frames | | count | dataset manifest |
| Registered frames | | count | reconstruction model |
| Registered frame ratio | | registered / frozen train | |
| Mean reprojection error | | pixels; state COLMAP field/query | |
| Median reprojection error | | pixels | |
| Mean track length | | observations per 3D point | |
| Median track length | | observations per 3D point | |
| Camera median translation step | | normalized scene units | |
| Camera maximum step / median | | ratio | |
| Camera p95 turn | | degrees | |
| Camera maximum turn | | degrees | |
| Discontinuity count | | state thresholds | |
| Reconstruction wall time | | seconds | worker telemetry |
| Reconstruction peak VRAM | | MiB | GPU telemetry |

## Gaussian and holdout metrics

| Metric | Value | Unit / exact convention | Evidence artifact |
|---|---:|---|---|
| PSNR | | dB; state color space/crop/mask | rendered holdouts |
| SSIM | | state implementation/version/window | rendered holdouts |
| LPIPS | | state network/version/checkpoint hash | rendered holdouts |
| Gaussian count | | count | validated SceneBundle |
| Training wall time | | seconds | worker telemetry |
| Training peak VRAM | | MiB | GPU telemetry |
| SceneBundle size | | bytes | artifact manifest |
| Gaussian PLY size | | bytes | artifact manifest |
| Export wall time | | seconds | worker telemetry |

Include a per-holdout table with camera id, ground-truth hash, render hash,
PSNR, SSIM, and LPIPS.  Aggregate only after verifying every expected holdout is
present exactly once.

## Compatibility consumers

| Consumer | Exact version / commit | Status | Load time | Render or summary hash | stdout/stderr artifact |
|---|---|---|---:|---|---|
| ExportKit self-loader | repository commit | | | | |
| Brush | `v0.3.0` / `3edecbb2...` | | | | |
| SplatTransform | `v3.0.0` / `daf63383...` | | | | |

Successful process exit alone is insufficient.  The consumer must report the
expected Gaussian count and produce either a deterministic summary or a fixed
camera render.  Record NaN/Inf and rejected-property diagnostics.

## Fixed-camera visual review

Use byte-identical camera poses for candidate, legacy COLMAP+Brush, and Postshot
reference renders.  Save a contact sheet and populate
`manual_visual_scorecard.csv`.  Scores use:

- Artifact severity (floaters, noise, edge swelling, near-field tearing): 1 is
  absent/best; 5 is severe/worst.
- Detail, color, and overall: 1 is worst; 5 is best.

Reviewer notes must identify image regions and may not infer causes that were
not diagnosed.

## Comparison and decision

| Comparison | Quality delta | Runtime / VRAM delta | Compatibility delta | Confidence / missing evidence |
|---|---|---|---|---|
| Candidate vs legacy COLMAP+Brush | | | | |
| Candidate vs Postshot reference | | | | |

State whether the run changes the reconstruction default, trainer default, or
fallback decision.  A blocked or incomplete run cannot establish a winner.
