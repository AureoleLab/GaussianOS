# Public Beta release work — 2026-09-06

Status: **in progress; release authorized, but acceptance gates not yet met and no artifact published**.

## Authority and baseline

The user authorized autonomous audit, implementation, packaging, isolated
verification and release, with all existing features preserved and approximately
75 GB of free build disk as a hard constraint. Do not delete user data. No agents
were requested. The current task's `I:/GaussianOS-LF` directory is an incomplete
non-Git tree; the actual complete application is `I:/GaussianOS`.

- Original branch: `codex/portable-pipeline-distribution-diagnostics`.
- Original HEAD: `77bd048`, with 43 changed/new implementation and test files.
- Release branch: `codex/public-beta-20260906`.
- Preserved working baseline: `9fd6c83` (all existing application changes;
  `EXPORTUSER/`, `experiments/` and user projects excluded and preserved).
- Original snapshot: `build/public-beta/evidence/baseline-source.zip`, 401 files,
  8,964,534 bytes, SHA-256
  `bc41ce67cd665b5613cb4b1ffa98f7ed61d57817760718104f50f83c0d7e0d1c`.
- Snapshot inventory, original patch/status and disk inventory are beside it.
- Baseline regression: **249 passed, 2 external consumer checks skipped**, 40.29 s.
  Evidence: `build/public-beta/evidence/pytest-baseline.{xml,log}`.

## Initial findings

1. Current developer worker environments are venvs referring to absolute uv
   CPython homes under the developer account. The historical manifest instead
   expects full standalone interpreters at the environment root. Copying the
   current venv trees is not a valid portable build.
2. MapAnything retains an editable install pointing into `I:/GaussianOS`.
3. Several current developer Runtime paths are missing (FFmpeg tool layout,
   DINOv2 weights, portable Git); previous approved offline assets exist on J:.
   They must be verified, not assumed to be the current application baseline.
4. `scripts/verify_portable_e2e.py` imports the control plane from the checkout;
   it cannot by itself establish that the packaged EXE pipeline works.
5. The locked gsplat extension was compiled with `TORCH_CUDA_ARCH_LIST=12.0`.
   PyTorch itself contains sm_75/80/86/90/100/120; this does not establish gsplat
   extension compatibility on those GPUs.
6. The doctor currently checks VRAM but not driver or GPU compute capability.
7. Download installation has no complete online payload for several required
   components; Core-only installation cannot deliver the promised workflow.
8. Current worker environment cleanup does not fully isolate inherited Windows
   DLL discovery and application/Conda/CUDA PATH entries.

## Disk and environment

Initial free I: 77,560,659,968 bytes; after baseline audit 77,543,002,112.
No user data removed. Developer `.gaussian-factory`: 18,867,359,065 bytes
(includes projects, tools/build caches, runtime and models). Developer UI venv:
879,844,180 bytes. Historical offline Runtime on J:: 17,742,741,405 bytes and
does **not** include the newer LPIPS weights component.

Host: Windows 10 Pro 19045, RTX 5090, driver 591.44, 32,607 MiB VRAM.
Worker Python: 3.10.20 and 3.12.13; both Torch 2.9.1+cu130. GUI Python:
3.13.9/Conda-based uv venv, PySide6 6.10.2.

## Current checkpoint — 2026-09-12

Release remains **draft and not approved for Public Beta** until final installed
GUI, complete Pipeline/export and independent Windows package CI all pass.

- Published source branch currently ends at fc2d3d5. Later fixes are being
  verified before committing. Do not use main as the release baseline.
- 273 full regression tests passed with no skips, including pinned real Brush
  0.3.0 and splat-transform 3.0.0; evidence `pytest-regression-5.xml`.
- Frozen Acceptance-002 passed the ordinary video Pipeline, Viewer data,
  Timeline, external Scene Bundle and project reopen, plus full Runtime hashes.
- Real fallback registered 12/12 cameras after COLMAP reached only 75%, and
  completed BA and Gaussian training. Unicode/long-path native output initially
  failed; the isolated worker now enters the Unicode directory through Python
  and passes ASCII-relative paths to native COLMAP. Real packaged retry passed.
- Actual installed fallback Pipeline later produced 63,042 Gaussians, but its
  external export rejected native unbranded binary point PLY. Viewer/export
  now share the compatible reader; source re-export of that exact installed
  output passed (12 cameras, 65,095 points). Final frozen repeat remains pending.
- Rendered GUI testing exposed a separate distribution defect: PyInstaller
  collected Poppler ICU 78 from the build tool PATH, while Qt required different
  ICU entry points. Source UI imports and CLI Pipeline tests had not caught it.
  Build now uses uv-managed CPython 3.13.9, locked GUI dependencies and pinned
  packaging tools in a separate environment, with a clean native search PATH.
- Core build 7 passed all 340 native-library source/hash provenance checks and
  a real frozen Qt/WebEngine import. New GUI diagnostics require the requested
  shell, actual Viewer readiness and camera interaction, with JSON and PNG.
- New Core is 663,535,156 bytes. RC3 Core ZIP and embedded per-user installer are
  being generated under `build/public-beta/release-rc3`. Earlier RC1/RC2 packages
  contain the broken GUI dependency and must not be published.
- Installer upgrade inventory contains 181 obsolete native files from the
  previous audited Core. Exact matching hashes can be removed; changed files
  are preserved in Cache/CoreUpgradeBackup. Runtime and projects remain intact.
- The single full Runtime is at `I:/GaussianOS-Beta 安装验证/Runtime`; never create
  another 13 GB copy. Actual RC2 installer installed that root successfully.
  Original relocation root `I:/GaussianOS-Beta 验证` keeps earlier evidence.
- Base Runtime: 2,603,305,761 download / 4,244,787,870 installed bytes. Fallback:
  6,847,320,850 download / 8,922,116,082 installed bytes. Full installed Runtime:
  13,166,903,952 bytes. Segmented compressed payload total: 9,450,626,611 bytes.
  Runtime manifest SHA-256: 21ce6fbc7b7f33be8c164805dcc1d96b8bec66eb1031281550e6eb9cf6f40b32.
- Duplicate standalone DINO weights were removed only after all 812 model
  parameters/buffers matched byte-for-byte following complete model loading.
  Real fallback ran without that extra checkpoint. Git payload is unnecessary
  with content-hashed immutable source locks. Their owned backups remain.
- gsplat has compiled 7.5/8.0/8.6/8.9/9.0/10.0/12.0+PTX coverage. Only RTX 5090
  execution has been tested. MapAnything peaked at 8.03 GiB on 12 frames;
  documentation now recommends at least 12 GiB for fallback, more for large scenes.
- Independent source CI passed. Exact draft package CI failed before download
  because read-only GITHUB_TOKEN cannot access unpublished release assets.
  Auto-review rejected changing workflow contents permission to write. That
  permission remains read. A helper is prepared to supply only expiring,
  read-only signed asset URLs in an encrypted Actions secret; not yet invoked.
- Disk monitor preserves initial I: free 77,560,659,968 bytes and all minima.
  After the quota pause other work had consumed additional space; current free
  is approximately 23–24 GB. The 15 GB reserve remains. Report volume growth
  honestly: it includes unrelated processes and is not solely this build's peak.

Next: actual installer upgrade and Unicode-path GUI/Viewer/Timeline; final
installed ordinary and real-fallback E2E/export; exact artifact independent
Windows CI (installer, first-use Runtime setup, standalone worker ABIs, both UI
shells, uninstall preservation); final hashes/provenance/docs and release gate.
Do not publish or mark the goal complete before required evidence is available.

References: PyInstaller external-program environment isolation and operating
mode documentation; CPython Windows embedding; NVIDIA CUDA compatibility;
Inno Setup per-user installation and GetSHA256OfFile documentation. These support
the design; actual package acceptance is the release evidence.

### 2026-09-13 resumed verification

RC3 installer upgrade passed with all 3,139 immutable installed files matching
its manifest, an intentionally modified obsolete DLL preserved, and existing
project metadata/Runtime retained. RC3 Core: 262,867,633 bytes, SHA-256
4e922ff5f9c9e492d6818be1dcc233081028c31327e01a4f0106bb05f061fdb5;
installer: 180,627,545 bytes, SHA-256
39752c893811f43362ea00b97804b9e40d9143def6bc131c1eb9dc373ab7b166.
Both are uploaded but remain draft.

Visible RC3 ModernUI and ClassicUI rendered the real 63,042-Gaussian fallback
scene and passed orbit/pan/zoom (about 60 FPS). Prior black screenshots resulted
from launching the application with SW_HIDE. Render acceptance now uses a visible
window. The native Computer Use screenshot helper twice returned unsupported
interface 0x80004002, so evidence uses the application's actual visible window
capture, together with structured JavaScript interaction results.

Further verification found missing WebChannel registration: objectName alone
was insufficient for QML registeredObjects. Explicit registerObject fixed native
bridge ping in both shells. Modern Timeline diagnostics now choose a registered
frame instead of assuming frame 0 was reconstructed. Both shell candidates
successfully activated camera 1 and rendered its camera view. These two QML files
were deployed only to the owned test installation for rapid diagnosis; its Core
must be restored by the next actual installer before claiming exact final-package
acceptance. Source Core build 8 and final regression are currently running.

### Native dependency closure correction

RC4 installed update was safely aborted by Restart Manager because the old
manual acceptance GUI (PID 38048, recorded launch) was still running. That owned
process was closed. Installer migration now runs in BeforeInstall, after file
occupancy checks (commit 1307931); RC5 installer compiled, not yet installed.

A static import audit found six Microsoft C++ DLL names missing beside COLMAP;
System32 on the developer host provided them, and a developer-equipped Windows
runner could also hide this. All 11 release CRT/OpenMP DLLs from the licensed
VS2022 14.44 redistributable set were signature-verified, hash-locked, and bundled
app-local, adding 2,039,070 bytes. Three fail-closed assembly tests passed. CI now
requires those exact local files and executes native COLMAP/FFmpeg directly.
The COLMAP component alone was repackaged; all model/environment payloads are
unchanged. New Runtime sizes: base download 2,604,125,637 / install 4,246,826,940;
fallback download 6,847,320,850 / install 8,922,116,082. Core metadata and installer
must now be refreshed to carry this revised manifest before final E2E/CI.

### 2026-09-19 RC6 exact installation acceptance

Resumed from the user-requested pause. The exact RC6 installer SHA-256 is
0c72503647b7aa6b93976c9b5cc13f67b2fbd592408e55bb4328fe1ed2b8bc0c
(180,619,881 bytes). Core ZIP SHA-256 is
f2621c0987a5b59db4b194dd3251a5d914ed341047d788cf994bfaca22b65f58
(262,869,083 bytes). Runtime manifest SHA-256 is
081ddfc5e4243610ba15c72cf9c54b98856ddf120da9bdee32646296794f253f.

Actual RC6 installer exited 0 in the existing owned Unicode-path installation.
All 3,139 inventory files matched their sizes and SHA-256; all 11 app-local CRT
files matched the lock. Native COLMAP starts with only Windows system paths.
The post-fix static import audit found no missing native dependencies and no
remaining external MSVC 140/OpenMP imports. Evidence is under
build/public-beta/evidence/{installed-core-integrity-rc6.json,colmap-native-dependencies-rc6.json,colmap-rc6-help.txt}.
Full final source regression: 276 passed, no skips, 55.56 seconds
(pytest-regression-rc6.xml). Exact frozen GPU Pipeline and independent Windows
acceptance are still pending; these results alone do not authorize a pass claim.
