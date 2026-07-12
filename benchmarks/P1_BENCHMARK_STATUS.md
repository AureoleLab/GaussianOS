# P1 benchmark status — 2026-07-12

## Verdict

| Item | Status |
|---|---|
| gsplat | **PASS** |
| MapAnything fallback | **PASS** |
| Postshot comparison | **WAITING_FOR_REFERENCE** |
| P1 | **WAITING_FOR_REFERENCE** |
| P2 allowed | **NO** |

The production technical chain is now validated. P1 is not marked GO because
neither Postshot nor the old COLMAP+Brush output was supplied, so the required
fixed-camera parity and gap report cannot be completed without fabrication.

Dataset: `sha256:152be2c9901a8652daa032ab5c35a65aaf3aa83fc1deb1a1afa41a2a2a3ab33d`.
It contains 114 frozen frames: 100 train and 14 holdout across three videos.

## Production selection

- Default reconstruction: COLMAP 3.13.0, commit `0b31f981…`.
- Default trainer: gsplat 1.5.3, commit `937e299…`.
- Automatic fallback: MapAnything Apache v1.1.2, commit `c845b8f…`, then
  COLMAP 3.13.0 bundle adjustment.
- Faster-GS remains an unselected speed candidate. Research-only GLUEMAP,
  VGGT-Omega, and ImprovedGS remain blocked from production.

## COLMAP reconstruction baseline

| Scene | Registered | Points | Track length | Reprojection | Algorithm time |
|---|---:|---:|---:|---:|---:|
| 001 | 34/34 | 25,404 | 4.544 | 0.623 px | 27.25 s |
| 002 | 29/29 | 20,399 | 10.989 | 0.595 px | 54.25 s |
| 003 | 37/37 | 23,536 | 8.919 | 0.836 px | 44.12 s |

These are the existing immutable train-only results. An all-frame model was
used to provide fixed holdout camera poses for the gsplat technical training
test; holdout RGBs were excluded from optimization. Thus the reported image
metrics validate photometric generalization, but are not a blind unknown-pose
localization benchmark.

## gsplat 1.5.3 real training

The exact source loaded a compiled `gsplat/csrc.pyd` built with CUDA nvcc
13.0.48, MSVC 19.44.35228, `CUDA_HOME` set to the private CUDA 13 toolchain,
and `TORCH_CUDA_ARCH_LIST=12.0`. RTX 5090 forward and backward produced finite,
nonzero gradients for means, quaternions, scales, opacities, and colors.

All scenes used 7000 steps, factor-4 images, SH degree 3, the frozen
offset-4/stride-8 holdout split, deterministic seed 42, and real densification.
`SIMPLE_RADIAL` pixels were undistorted before optimization and exported camera
intrinsics match the training pixels.

| Scene | Train / holdout | Initial PSNR | PSNR | SSIM | LPIPS | Time | Peak VRAM | Gaussians | PLY size |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 001 | 34 / 5 | 15.55 | 26.51 dB | 0.8375 | 0.1382 | 99.32 s | 0.852 GiB | 560,563 | 139,021,497 B |
| 002 | 29 / 4 | 11.04 | 28.71 dB | 0.9091 | 0.1507 | 90.36 s | 0.312 GiB | 191,034 | 47,378,305 B |
| 003 | 37 / 5 | 14.64 | 30.35 dB | 0.9393 | 0.0493 | 101.26 s | 0.811 GiB | 531,151 | 131,727,321 B |

Evidence: `evidence/gsplat_training.json`. Candidate-only fixed-view inspection
is in `evidence/gsplat_visual_review.md`; scene 002 shows substantial skyline
tearing/ghosting, while 001 and 003 are materially cleaner.

## Trained Gaussian PLY consumers

Every formal large PLY was loaded by all of the following, with exact Gaussian
count and degree-3 SH checks where the consumer reports them:

| Consumer | Version | Scenes 001 / 002 / 003 |
|---|---|---|
| ExportKit strict loader | workspace | PASS / PASS / PASS |
| gsply | 0.4.6 | PASS / PASS / PASS |
| SplatTransform | 3.0.0 (`daf6338`) | PASS / PASS / PASS |
| Brush | 0.3.0 (`3edecbb…`) | PASS / PASS / PASS |

This proves loading, not interactive render quality. Full logs and PLY hashes
are in `evidence/trained_ply_consumers.json`.

## MapAnything fallback

The constructed hard case uses 12 real scene-001 train frames at 256×144 with
deterministic blur, contrast reduction, and alternating exposure. Direct
COLMAP produced zero matches and no model, so reprojection error and track
length before fallback are N/A rather than invented zeros.

| Stage | Registered | Reprojection | Track length | Cameras | Points |
|---|---:|---:|---:|---:|---:|
| Direct COLMAP | 0/12 | N/A | N/A | 0 | 0 |
| MapAnything export, before BA | 12/12 | 0.0 px* | 6.347227 | 12 | 7,989 |
| COLMAP BA output | 12/12 | 0.0 px* | 6.347227 | 12 | 7,989 |

BA was real: 101,416 residuals, 24,056 parameters, 5 iterations, convergence,
and cost `4.63955e-6 → 2.6784e-7` px. `model_analyzer` rounds these synthetic
projection residuals to `0.0`; the precise Ceres costs are retained. Canonical
OpenCV cam2world `CameraTensors` validation passed. A normal 39-frame scene
registered 39/39 and returned `POLICY_DENIED` before MapAnything loading.

Both MapAnything (`fa06c0…`, 4.914 GB) and its required DINOv2 ViT-g/14
backbone (`baf846…`, 4.546 GB) are SHA-256 and Apache-2.0 locked. Evidence:
`evidence/mapanything_fallback.json`.

## Reference gap

No Postshot or old COLMAP+Brush artifact, fixed-camera render, version, or
runtime record was found. Candidate files were not substituted. Import
instructions are under `benchmarks/references/`; the current state is
`WAITING_FOR_REFERENCE`.

Consequently these deltas remain N/A: Postshot/legacy PSNR, SSIM, LPIPS,
floaters, noise, edge swelling, near-field tearing, runtime, VRAM, Gaussian
count, export size, and operator/UX score. This is the only remaining P1
acceptance blocker; it also keeps P2 blocked.

## Tests

- Hermetic suite: 74 passed, 2 external compatibility checks skipped.
- External compatibility suite: 5 passed.
- Final combined run with external variables enabled: **76 passed in 4.40 s**.
