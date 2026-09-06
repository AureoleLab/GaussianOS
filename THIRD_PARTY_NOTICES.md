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
| CPython | 3.10 / 3.12 / 3.13 | Python-2.0 |

The Public Beta ships the full Apache-2.0 MapAnything checkpoint, retaining
its DINOv2 encoder. It omits the redundant standalone DINOv2 pretraining
checkpoint: loading the full model gives byte-identical parameters and buffers.
Pinned source trees use content hashes and do not require a bundled Git client.
Historical alpha offline packages included Git for Windows under GPL-2.0-only
and its bundled component licenses; the current Beta does not.

Dependency license files remain alongside their installed modules and binaries.
Qt/PySide6 shared libraries remain separate replaceable files in Application.
GaussianOS does not restrict reverse engineering needed to debug modifications
to LGPL-covered libraries. Source and build instructions for GaussianOS are at
https://github.com/AureoleLab/GaussianOS; Qt/PySide6 corresponding source is at
https://download.qt.io/official_releases/QtForPython/pyside6/ and
https://download.qt.io/official_releases/qt/6.10/6.10.2/single/.

The full provenance, hashes, and research-only exclusions are recorded in
`third_party/locks/` and `configs/profiles/production.json`. GPL FFmpeg builds,
`plyfile`, VGGT, GLUEMAP, and ImprovedGS are not production distribution
components.
