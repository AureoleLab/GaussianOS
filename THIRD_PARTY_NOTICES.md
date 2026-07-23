# Third-party notices

GaussianOS source code is Apache-2.0. Distributed dependencies retain their
own licenses and notices; this file is not a replacement for any license text
shipped by a dependency.

| Component | Approved production version | License |
|---|---:|---|
| PySide6 / Qt | 6.10.2 | LGPL-3.0-or-later / commercial |
| FFmpeg (approved build only) | n8.1.2 | LGPL-2.1-or-later |
| COLMAP | 3.13.0 | BSD-3-Clause |
| MapAnything Apache | v1.1.2 | Apache-2.0 |
| DINOv2 | locked commit 7764ea0 | Apache-2.0 |
| gsplat | v1.5.3 | Apache-2.0 |
| PyTorch | 2.9.1+cu130 | BSD-3-Clause |
| CPython | 3.10 / 3.12 | Python-2.0 |
| Git for Windows | 2.51.2.windows.1 | GPL-2.0-only and bundled component licenses |

The full provenance, hashes, and research-only exclusions are recorded in
`third_party/locks/` and `configs/profiles/production.json`. GPL FFmpeg builds,
`plyfile`, VGGT, GLUEMAP, and ImprovedGS are not production distribution
components.
