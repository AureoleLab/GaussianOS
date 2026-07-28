# Distribution optimization audit — 2026-07-28

## Scope and rollback

- Repository: `I:\GaussianOS`
- Starting branch: `codex/modern-ui-migration`
- Starting HEAD: `72291ee79827351eeb5fe8fac7923887f8e45e44`
- Optimization branch: `codex/distribution-optimization-20260728`
- Origin: `https://github.com/AureoleLab/GaussianOS.git`
- Pre-existing untracked `EXPORTUSER/` and `tmp/` data was preserved and was not
  added to a commit or package.
- Rollback tags:
  - `backup/pre-distribution-optimization-20260728`
  - `backup/golden-baseline-before-distribution-20260728`
  - `backup/runtime-architecture-20260728`

## Golden baseline

- Source compile: passed.
- Test suite before distribution changes: 198 passed, 2 opt-in external
  compatibility checks skipped.
- Test suite after the final changes: 213 passed, 2 identical opt-in checks
  skipped (215 collected).
- ModernUI and ClassicUI source GUI/WebEngine smoke: passed and visually
  inspected.
- Baseline evidence:
  `build/distribution-audit/baseline/pytest-baseline.xml`,
  `modern-ui.png`, and `classic-ui.png`.
- Final evidence:
  `build/distribution-audit/final-regression.xml` and the packaged validation
  logs/screenshots in the isolated validation directory.

The tests cover project lifecycle and isolation, Easy/Pro sampling, video/image
ingest contracts, camera timeline, COLMAP/fallback status, gsplat worker
contracts, Viewer/WebEngine behavior, cancellation/recovery, settings, export
round trips, and stable project/run/generation identities.

## Size baseline and result

The repository occupied 71,406,692,718 bytes before optimization. Its largest
top-level contributors were:

| Path | Bytes |
| --- | ---: |
| `便携包` | 32,274,700,247 |
| `.gaussian-factory` | 18,622,972,914 |
| `build` | 13,730,593,558 |
| `tests` | 2,478,209,247 |
| `benchmark_runs` | 1,759,737,912 |
| `.venv` | 879,843,130 |
| `dist` | 681,939,644 |
| `release` | 393,855,264 |

| Product | Before | After | Change |
| --- | ---: | ---: | ---: |
| Portable Core, unpacked | 753,819,903 | 668,718,843 | -85,101,060 (-11.29%) |
| Portable Core archive | 393,491,676 | 267,266,836 | -126,224,840 (-32.08%) |
| Runtime source vs. offline payload | 18,622,972,914 | 17,759,119,558 | -863,853,356 (-4.64%) |

The final Core contains 3,101 files. The Offline Runtime contains 71,138 files.

## Safe optimization decisions

Removed from the Core package only:

- exact WebEngine debug/release resource duplicates;
- `.pdb` files;
- `.pyc` and `__pycache__` bytecode caches;
- package-ineligible build/test/source-map data selected by the audited content
  policy.

The exact Core pruning report is embedded in the Core package. The measured
debug/cache removal was 86,856,581 bytes. Release WebEngine resources were
checked before their debug pairs were removed.

Retained because safe removal was not proven:

- all CUDA/Torch DLLs;
- all Qt plugins and translations not proven unreachable;
- `numba` and `llvmlite`, which are used by compressed PLY support;
- gsplat, MapAnything and DINOv2 sources, environments and locked models;
- duplicate DLL/package groups reachable through dynamic loaders;
- all user projects, exports, receipts, locks, logs and settings.

No repository Runtime/cache tree was deleted. Large pre-existing build and
benchmark data remains available for rollback and further evidence-based
optimization.

## Core and Runtime architecture

The portable layout separates `Application`, `Runtime`, `Settings`, `Cache`,
`Logs`, `Projects`, and `Exports`. Runtime operations share a versioned manifest
and support detection, resumable/retried download, staging, critical and full
tree SHA-256 verification, atomic commit, offline import, reuse, fault
classification, and repair. The manifest rejects absolute paths and
`runtime/runtime` nesting.

Core-only ModernUI and ClassicUI start without a Runtime. Doctor distinguishes
Core, missing/incomplete/corrupt Runtime, GPU/CUDA, external tools and project
data. Runtime operations do not write to project or export directories.

The Offline Runtime root includes `Install_Runtime.bat`,
`Start_GaussianOS.bat`, and `Start_GaussianOS_Classic.bat`. They locate a
sibling or user-selected Portable Core, validate required manifest files,
perform the verified offline import when needed, and launch the selected UI
without embedding a duplicate Application in the Runtime package.

## Artifacts

Release directory: `J:\GaussianOS-release-20260728`

| Artifact | Bytes | SHA-256 |
| --- | ---: | --- |
| `GaussianOS-Portable-Core-win-x64.zip` | 267,257,718 | `e04d1d2908dc21c29829cc208321e960b14f67721d2fb57ab843ef8ec4e2a1f5` |
| `GaussianOS-Offline-Runtime-win-x64.7z` | 12,323,188,782 | `ff03b454f9b05789a7b831cfdf50a607baddbddc6828ccc305837ccae5bda9ec` |
| `GaussianOS-Full-Offline-win-x64.7z` | 12,501,429,769 | `b5c6cb70d124f1323149f94eb3745d3eed2c71fb2e4683dbd02757b4dfa7bb66` |

The directory also contains `SHA256SUMS.txt`, `runtime-manifest.json`,
`build-manifest.json`, `VERSION`, `CHANGELOG.md`, `QUICKSTART.md`, and
`TROUBLESHOOTING.md`.

## Isolated validation

Validation directory:
`J:\GaussianOS-clean-validation-20260728 中文 空格`

Passed:

- Core ZIP extraction outside the repository;
- Core-only doctor (`Core: ok`, `Runtime: not_installed`);
- packaged ModernUI, ClassicUI and WebEngine startup;
- Offline Runtime `Start_GaussianOS.bat` launching the selected packaged Core
  from a Chinese and spaced path;
- full Offline Runtime import and 71,138-file tree verification;
- deliberate same-size FFprobe corruption, precise component/file diagnosis,
  atomic repair, empty staging and a final all-`ok` doctor;
- synthetic video generation with packaged FFmpeg, packaged video analysis,
  12 selected frames, 72-frame timeline and committed project;
- moving the entire Core through Chinese, spaced and long paths;
- replacing/deleting `Application` without changing Runtime, Projects or
  Exports.

Not completed in the isolated directory:

- a fresh end-to-end COLMAP/MapAnything/gsplat training run followed by Viewer,
  restart recovery and Scene Bundle export. Windows UI automation could not
  attach to the Qt window (`0x80004002`). Existing source tests and prior real
  project evidence pass these chains, but they are not substituted for the
  required isolated packaged run.
- the two external Graphdeco npm/Brush compatibility checks remain opt-in
  because their external executables were not configured.

## Release decision

The Core/Runtime architecture and artifacts are reproducible candidates and all
performed checks passed. They do **not** yet satisfy the formal distribution
gate because the isolated packaged full training-to-export run was not
completed. Do not publish them as a formal release until that remaining clean
environment check passes without changing algorithms, parameters, protocols or
output semantics.

## Full Offline follow-up

A user extraction test showed that the Runtime-only archive could be mistaken
for a standalone application. That archive intentionally has no
`Application\GaussianOS.exe`, but its launcher previously waited for a Core
path without stating this clearly.

The follow-up adds a single-folder
`GaussianOS-Full-Offline-win-x64.7z` containing one Application and one Runtime
root. The Runtime-only launchers now auto-discover a sibling Core and otherwise
fail with an explicit explanation and a pointer to the Full Offline product;
they no longer present an unexplained empty path prompt.

The Full Offline candidate was extracted and validated at
`C:\GStest(del)\GaussianOS-Full-Offline-win-x64`. Complete doctor reported Core,
Runtime, GPU, external tools, and project data as `ok`, with full Runtime
verification and no issues. Actual packaged ModernUI and ClassicUI BAT launches
both succeeded. The complete automated regression after this follow-up is 213
passed and 2 unchanged opt-in external checks skipped (215 collected).

This follow-up fixes installation and launch usability only. It does not change
training algorithms, parameters, project protocols, Viewer behavior, or export
semantics. The release decision above remains unchanged until the clean
training-to-export gate is completed.
