# P1 license evidence index

Verified on 2026-07-12 from upstream-owned repositories and model pages.  This
file is an evidence index, not a substitute for retaining the complete license
notices when a dependency is distributed.  Exact machine-readable fields live
in `third_party/locks/p1_candidates.lock.json`.

The optional compatibility-test readers are separately isolated: `gsply`
0.4.6 is MIT at commit `363885c707d445ce5d925024e2ab536fc72c1b9d`;
`plyfile` 1.1.3 is GPL-3.0-only at commit
`071e2ba6a2246ffd74eecb7e2757bd6de25650ea` and is forbidden from the
production runtime and distribution. Exact wheel hashes are recorded in
`uv.lock` and the machine-readable third-party lock.

| Component | Profile | Locked ref / commit | Code license | Exact upstream evidence |
|---|---|---|---|---|
| FFmpeg | production | `n8.1.2` / `38b88335f99e76ed89ff3c93f877fdefce736c13` | LGPL-2.1-or-later for the approved default build; configure flags can change the effective license | [license explanation](https://github.com/FFmpeg/FFmpeg/blob/38b88335f99e76ed89ff3c93f877fdefce736c13/LICENSE.md), [LGPL text](https://github.com/FFmpeg/FFmpeg/blob/38b88335f99e76ed89ff3c93f877fdefce736c13/COPYING.LGPLv2.1) |
| COLMAP | production | `3.13.0` / `0b31f98133b470eae62811b557dc2bcff1e4f9a5` | BSD-3-Clause | [COPYING.txt](https://github.com/colmap/colmap/blob/0b31f98133b470eae62811b557dc2bcff1e4f9a5/COPYING.txt), [official release assets](https://github.com/colmap/colmap/releases/tag/3.13.0) |
| MapAnything | production fallback | `v1.1.2` / `c845b8f4f6cde0c20aecd87573656c3f69f5b2b0` | Apache-2.0 | [code license](https://github.com/facebookresearch/map-anything/blob/c845b8f4f6cde0c20aecd87573656c3f69f5b2b0/LICENSE), [official Apache model card](https://huggingface.co/facebook/map-anything-apache) |
| gsplat | production | `v1.5.3` / `937e29912570c372bed6747a5c9bf85fed877bae` | Apache-2.0 | [LICENSE](https://github.com/nerfstudio-project/gsplat/blob/937e29912570c372bed6747a5c9bf85fed877bae/LICENSE) |
| Faster-GS | production candidate | `main` / `ae2bf807314401c83fc18ba577981c91112058f9` | Apache-2.0 | [LICENSE](https://github.com/nerficg-project/faster-gaussian-splatting/blob/ae2bf807314401c83fc18ba577981c91112058f9/LICENSE), [official README](https://github.com/nerficg-project/faster-gaussian-splatting/tree/ae2bf807314401c83fc18ba577981c91112058f9) |
| NeRFICG framework | production support candidate | `main` / `c7437127af1681f565a57fcd9d7819fde1adc0a7` | MIT | [LICENSE](https://github.com/nerficg-project/nerficg/blob/c7437127af1681f565a57fcd9d7819fde1adc0a7/LICENSE) |
| Brush | production compatibility consumer | `v0.3.0` / `3edecbb2fe79d3e2c87eeab85b15e0b1dd10d486` | Apache-2.0 | [LICENSE](https://github.com/ArthurBrussee/brush/blob/3edecbb2fe79d3e2c87eeab85b15e0b1dd10d486/LICENSE), [PLY loader statement](https://github.com/ArthurBrussee/brush/tree/3edecbb2fe79d3e2c87eeab85b15e0b1dd10d486#viewer) |
| SplatTransform | production compatibility consumer | `v3.0.0` / `daf63383f32effe5cd63faa67ff030d39bfa543e` | MIT | [LICENSE](https://github.com/playcanvas/splat-transform/blob/daf63383f32effe5cd63faa67ff030d39bfa543e/LICENSE), [supported formats](https://github.com/playcanvas/splat-transform/tree/daf63383f32effe5cd63faa67ff030d39bfa543e#supported-formats) |
| GLUEMAP | **research-only** | `main` / `adc9e4bb5f41014d3f7c157a879edc278588c829` | BSD-3-Clause for GLUEMAP code only | [LICENSE](https://github.com/colmap/gluemap/blob/adc9e4bb5f41014d3f7c157a879edc278588c829/LICENSE), [dependency scope warning](https://github.com/colmap/gluemap/tree/adc9e4bb5f41014d3f7c157a879edc278588c829#license) |
| VGGT-Ω | **research-only** | `main` / `39a0cb8af88554f15ddcb5354cd52bde588fa014` | FAIR Noncommercial Research License | [code license](https://github.com/facebookresearch/vggt-omega/blob/39a0cb8af88554f15ddcb5354cd52bde588fa014/LICENSE), [official model card](https://huggingface.co/facebook/VGGT-Omega), [paper](https://arxiv.org/abs/2605.15195) |
| ImprovedGS | **research-only** | `main` / `20b5db343a87c2f9fb4b70c6e39ff1f042a8a47a` | ImprovedGS Non-Commercial Research License | [LICENSE.md](https://github.com/XiaoBin2001/Improved-GS/blob/20b5db343a87c2f9fb4b70c6e39ff1f042a8a47a/LICENSE.md), [official project page](https://xiaobin2001.github.io/improved-gs-web/) |

## Checkpoint evidence

| Model | Revision | Artifact | Size | SHA-256 | License / status |
|---|---|---|---:|---|---|
| MapAnything Apache | `00f9c245bbcb60522d1ed7f9e9d88462c6e3f38a` | `model.safetensors` | 4,914,062,480 | `fa06c0fdccefc5048e072c85935d5789b1e36b307f3859033c17f9dcb9fd5201` | Apache-2.0; hash exposed by the official Hugging Face tree API |
| VGGT-Ω 1B 512 | `05654241adc2f218dfb089c373a011f8a7040576` | `vggt_omega_1b_512.pt` | 4,576,706,117 | **unavailable** | CC-BY-NC-4.0, gated; official API returns a redacted LFS hash without accepted access |
| VGGT-Ω 1B 256 text | `05654241adc2f218dfb089c373a011f8a7040576` | `vggt_omega_1b_256_text.pt` | 5,399,490,950 | **unavailable** | CC-BY-NC-4.0, gated; official API returns a redacted LFS hash without accepted access |

GLUEMAP is not a single-checkpoint component.  Its official README requires Pi3,
SALAD, VGGSfM tracker, and Doppelgangers++ checkpoints.  Their exact revisions,
hashes, and licenses are not yet closed, so the GLUEMAP worker must remain
disabled even in the research profile until that audit is complete.

The P1 COLMAP Windows CUDA asset is
`colmap-x64-windows-cuda.zip` (258,390,514 bytes), SHA-256
`60f77bd8e9823e6d2b39082ee665f69c91900011d5321fc54a4dfebe3de110b7`.
That digest is both published by the official GitHub release API and matched by
the downloaded file.  COLMAP 4.1.0 was observed upstream but is future/unvalidated
and is not the P1 production lock.

## Local FFmpeg warning

The benchmark host has a third-party Gyan build sourced from FFmpeg short commit
`38e89fe502`.  Its configure line contains both `--enable-gpl` and
`--enable-version3`; upstream's own license explanation makes the resulting
binary GPLv3.  Its executable hash is recorded for benchmark reproducibility,
but it is not the approved production redistribution artifact.
