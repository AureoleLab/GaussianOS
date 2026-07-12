# P1 benchmark status — 2026-07-12

## Verdict

P1 is **NO-GO / not accepted**. The reconstruction default and interchange
formats are validated, but no Gaussian trainer completed, the MapAnything
fallback did not execute, and no legacy/Postshot reference was supplied.
Advancing to P2 would violate the P1 exit gate.

Dataset: `sha256:152be2c9901a8652daa032ab5c35a65aaf3aa83fc1deb1a1afa41a2a2a3ab33d`.
The three videos are independent scenes. FFmpeg sampled 114 immutable PNGs at
15 fps: 100 train and 14 holdout. QC was advisory and removed nothing.

## Train-only reconstruction benchmark

COLMAP 3.13.0, commit
`0b31f98133b470eae62811b557dc2bcff1e4f9a5`, ran through the subprocess
Worker. Only frozen train frames entered feature extraction, matching, mapping,
sparse points, and bundle adjustment. Every output file was size/SHA-256
validated before atomic artifact publication.

| Scene | Registered | Ratio | Points | Observations | Track length | Reprojection | Max step / median | p95 turn | Algorithm time | Point PLY |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 001 | 34/34 | 100% | 25,404 | 115,439 | 4.544 | 0.623 px | 2.101 | 7.719° | 27.25 s | 381,310 B |
| 002 | 29/29 | 100% | 20,399 | 224,171 | 10.989 | 0.595 px | 2.293 | 1.385° | 54.25 s | 306,235 B |
| 003 | 37/37 | 100% | 23,536 | 209,916 | 8.919 | 0.836 px | 2.069 | 2.363° | 44.12 s | 353,290 B |

Exact rows and artifact IDs are in `reconstruction_results.csv`. An earlier
all-frame run also registered 39/39, 33/33, and 42/42, but it is retained only
as a smoke test because it included holdouts.

## Gaussian trainer matrix

| Reconstruction | Trainer | PSNR | SSIM | LPIPS | Gaussians | Train time | Peak VRAM | Gaussian PLY | Status |
|---|---|---:|---:|---:|---:|---:|---:|---:|---|
| COLMAP | gsplat 1.5.3 | N/A | N/A | N/A | N/A | N/A | N/A | N/A | BLOCKED |
| COLMAP | Faster-GS | N/A | N/A | N/A | N/A | N/A | N/A | N/A | NOT RUN |
| MapAnything + BA | gsplat | N/A | N/A | N/A | N/A | N/A | N/A | N/A | BLOCKED |

The isolated environment has PyTorch 2.9.1+cu130, includes `sm_120`, and
executed a real CUDA tensor operation on the RTX 5090. gsplat 1.5.3 then failed
to build because CUDA 13.0 `nvcc.exe` and MSVC `cl.exe` are absent. No metric is
filled with zero or an estimate. Faster-GS is locked but uninstalled.
MapAnything's Apache checkpoint is locked to SHA-256
`fa06c0fdccefc5048e072c85935d5789b1e36b307f3859033c17f9dcb9fd5201`
but the 4.9 GB file was not downloaded or executed.

## Gaussian PLY compatibility

The synthetic, degree-3, binary-little-endian fixture passed the strict
round-trip and the following consumers:

| Consumer | Exact version | Semantic result |
|---|---|---|
| gsply | 0.4.6 | PASS; means/scales/quats/opacities/SH degree and coefficients |
| SplatTransform | 3.0.0 / `daf6338…` | PASS; reported 2 Gaussians and 3 SH bands |
| Brush | 0.3.0 / `3edecbb…` | PASS; valid file exit 0, malformed-file negative control rejected |
| ExportKit | workspace | PASS; strict self-loader and SceneBundle round-trip |
| plyfile | 1.1.3 | PASS; generic structural check only, not counted as a semantic GS consumer |

Brush's official Windows ZIP SHA-256 is
`b68e3e9cf052d51bf3ee30776fa5a364de7f2ba13b58443128ff797bb7bcfcd6`.
The test proves parsing, not human render quality. Compatibility evidence is in
`evidence/ply_consumer_compatibility.json`.

## Candidate and reference gaps

- Production reconstruction default: **COLMAP 3.13.0** (validated).
- Intended production trainer: **gsplat 1.5.3** (locked, not validated; no
  trainer winner can be declared).
- Intended automatic fallback: **MapAnything Apache + COLMAP BA** (locked, not
  validated).
- GLUEMAP, VGGT-Omega, and ImprovedGS cannot be invoked from production.
- No legacy COLMAP+Brush artifact/version or Postshot fixed-camera renders were
  supplied. Floaters, noise, edge swelling, near-field tearing, quality delta,
  runtime delta, and UX gap therefore remain N/A; the manual scorecard is blank
  by design.

## Remaining acceptance blockers

1. Install a CUDA 13 compiler toolkit and MSVC build tools in the gsplat Worker,
   build the exact commit, and execute all three scenes and holdouts.
2. Execute Faster-GS under the identical cameras and split.
3. Download/verify MapAnything Apache, implement its COLMAP BA bridge, and run
   the same scenes.
4. Produce trained Gaussian SceneBundles/PLYs and load each in Brush,
   SplatTransform, and ExportKit.
5. Supply legacy and Postshot references for fixed-camera visual scoring.
