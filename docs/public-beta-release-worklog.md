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

## Work remaining

### Resume checkpoint

Latest checkpoint (13:05 local): **269 tests passed, no skips**, including actual
Brush 0.3.0 and splat-transform 3.0.0 consumer checks. Frozen E2E Acceptance-002
fully succeeded: 8,974 Gaussians, 12 cameras, 4,004 exported points, valid external
Scene Bundle, project reopen, Viewer data/Timeline and full Runtime hashes before
and after. The packaged MapAnything worker on the long video independently
passed a real fallback: baseline 75% -> 100% registered, 50,564 points, completed
COLMAP BA, absent standalone DINO checkpoint, 8.03 GiB peak VRAM. Rendered GUI
and independent fresh Windows acceptance remain pending.

Runtime payloads are complete and CRC/SHA-256 verified. Base: 2,603,305,761
download bytes / 4,244,787,870 installed bytes. Fallback: 6,847,320,850 download
bytes / 8,922,116,082 installed bytes. Full Runtime: 13,166,903,952 installed
bytes. Core build 3 includes first-use repair, disk budget and redaction fixes.
Its final archive and thin installer are being generated.

The owned staging distribution has been moved, without copying Runtime, to
`I:/GaussianOS-Beta 验证` outside the checkout for relocation acceptance. Historical
test reports still contain the old source location; new tests must use new paths.
Owned removed-runtime backups remain in `build/public-beta/removed-runtime-backup`;
a combined cleanup/move command was auto-review blocked, so no cleanup occurred.
Separate verified relocation succeeded. There is no pending permission request.
I: remains above 46 GB free; peak volume growth is recorded by the monitor.

`.github/workflows/beta-clean-machine.yml` will test the exact draft Core and
Runtime assets on a fresh Windows runner, including both Python ABIs and both UI
shells. It explicitly does not claim a GPU pipeline on a CPU-only runner.

- Standalone Runtime assembled in `build/public-beta/stage`; no original runtime
  or user project was modified. CPython `_pth`, editable-pointer replacement,
  frozen-process DLL search reset and sanitized worker environment implemented.
- gsplat extension rebuilt for 7.5/8.0/8.6/8.9/9.0/10.0/12.0+PTX. Only RTX 5090
  execution has been tested; compilation is not other-GPU validation.
- Latest regression: **259 passed, 2 external consumer checks skipped**.
- Frozen EXE completed 12-frame COLMAP reconstruction and 1,000 training steps:
  12/12 cameras, 4,009 points, 9,349 Gaussians, PSNR 14.505 -> 18.096.
  Viewer data and 154 timeline records loaded. Overall acceptance FAILED at the
  external export harness's missing destination directory; fixed in source,
  awaiting rebuilt EXE and rerun. This is not a complete acceptance pass.
- MapAnything initialization audit compared all 812 parameters/buffers after
  full checkpoint loading, with and without the redundant DINOv2 pretraining
  checkpoint: byte-identical. Production now skips redundant initialization;
  real packaged fallback execution is still required before removing the
  staged 4,546,108,579-byte duplicate checkpoint.
- Hash-locked resumable/segmented downloads, serialized runtime installation,
  base/fallback phases and graphical first-use setup are implemented; manifests,
  installer, final payloads and GUI acceptance are still being completed.
- Inno Setup 7.1.0 compiler installed under owned build tools after official
  download, SHA-256 and Authenticode verification. No elevated privileges used.
- I: observed peak growth ~19.67 GB so far; 57.89 GB free. Continuous disk monitor
  preserves pre-interruption minima in `evidence/disk-peak.json`.
- PATH/profile isolation on this development GPU host is NOT an independent
  clean-machine result. No independent clean-machine/CI acceptance yet.
- Stage Application is stale. Rebuild before evaluating source changes; never
  publish stage Cache/Projects/test media or raw development evidence.

- Assemble a reproducible self-contained Runtime from verified actual assets,
  with explicit CPython closure, portable imports and no user cache reliance.
- Address frozen subprocess DLL/path isolation and executable-level E2E mode.
- Define and verify a supported GPU matrix; rebuild gsplat for the matrix.
- Produce a normal installer/download experience with verifiable resumable
  component payloads and update reuse. Keep all functional capabilities.
- Measure disk peak with safety reserve; avoid full redundant Runtime copies.
- Run the final EXE's video pipeline, fallback, viewer, timeline, export,
  diagnostics and project regressions from isolated paths/environments.
- Distinguish restricted-host testing from an independent clean machine.
- Produce hashes, CI/release provenance, artifacts, and an honest release gate.

Technical references consulted: PyInstaller common issues / external programs
(`https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html`), CPython
Windows embedding (`https://docs.python.org/3.10/using/windows.html`), NVIDIA
CUDA compatibility (`https://docs.nvidia.com/deploy/cuda-compatibility/minor-version-compatibility.html`).
