# GaussianOS 0.1.0-beta.1 acceptance record

RC6 passed the local GPU and independent Windows package acceptance gates on
2026-09-19. The exact accepted artifacts are approved for Public Beta release
within the hardware and scene limitations recorded below.

## Baseline and artifact identity

The baseline is the real development working tree preserved in `9fd6c83`,
including 43 functional changes from `codex/portable-pipeline-distribution-diagnostics`
at `77bd048`. Historical main was not used as the release baseline. Release work
is on `codex/public-beta-20260906`. Application source is `8928fa08`; later commits
add installer migration ordering, COLMAP redistributables and acceptance tooling.
The installed application executable SHA-256 is
`835793553645b607321e6d4ce8d7c08176c7ae00af4d83173abe608da686611b`.

| Artifact | Bytes | SHA-256 |
|---|---:|---|
| Windows installer | 180619881 | `0c72503647b7aa6b93976c9b5cc13f67b2fbd592408e55bb4328fe1ed2b8bc0c` |
| Core ZIP | 262869083 | `f2621c0987a5b59db4b194dd3251a5d914ed341047d788cf994bfaca22b65f58` |
| Runtime manifest | 22567 | `081ddfc5e4243610ba15c72cf9c54b98856ddf120da9bdee32646296794f253f` |

All 17 published-candidate Runtime segments match the manifest's sizes and
SHA-256 at GitHub. Actual RC6 installation exited 0; all 3,139 inventoried Core
files and 11 app-local Microsoft CRT/OpenMP files matched their locked hashes.
COLMAP starts with only Windows system paths; static imports have no missing
DLLs or external MSVC 140/OpenMP dependencies.

## Distribution fixes

- Isolated managed CPython GUI build; clean native search paths and audits of
  all 340 collected library origins prevent developer ICU/DLL contamination.
- Independent embedded CPython workers (3.10 and 3.12), explicit module paths,
  no editable-source or Conda dependency, and isolated external-tool launches.
- Unicode/long-path native reconstruction output, compatible fallback point-cloud
  loading for Scene Bundle export, and explicit Viewer WebChannel registration.
- Per-user embedded-Core installer, automatic segmented/resumable SHA-256-verified
  Runtime installation, atomic component replacement, rollback and reuse.
- Upgrade migration after file-occupancy checks, with changed obsolete Core files
  preserved rather than deleted. Projects and Runtime survive uninstall.
- Full Apache MapAnything weights retained; only byte-identical redundant encoder
  weights and unnecessary Git distribution removed. No reconstruction feature cut.

## Exact installed EXE on Windows 10 / RTX 5090

Windows 10 Pro 19045, RTX 5090, driver 591.44. Both runs used the installed EXE
in a Unicode/spaces path, an empty profile, deliberately invalid Python/Conda
variables, system-only inherited PATH, and offline model flags. Production video
import and PipelineController were exercised. Preview: 12 frames, 1,000 steps.

| Check | Ordinary COLMAP path | Actual MapAnything fallback |
|---|---:|---:|
| Full Pipeline | Passed | Passed |
| Gaussians | 9051 | 61961 |
| Exported point-cloud points | 4004 | 65095 |
| Cameras | 12 | 12 |
| Scene Bundle export | Passed | Passed |
| Project reopen | Passed | Passed |
| Runtime full hash before / after | Passed / Passed | Passed / Passed |
| ModernUI Viewer / Timeline | Passed / Passed | Passed / Passed |
| ClassicUI Viewer / Timeline | Passed / Passed | Passed / Passed |

Eight actual visible-window captures have successful structured interaction
reports; screenshots were inspected. Both real exported Gaussian PLY files load
in plyfile 1.1.3, gsply 0.4.6, SplatTransform 3.0.0 and Brush 0.3.0. Brush evidence
is CLI loading, not an external rendered-scene quality test. Source regression:
**276 passed, no skips**. One-click diagnostics passed all three worker probes,
redacts local paths, and includes no source video, Gaussian/point-cloud PLY or model.
Local evidence is retained under `build/public-beta/evidence/rc6-*` and
`pytest-regression-rc6.xml`; private test media and scenes are not published.

## Independent Windows package acceptance

The first RC6 run installed and verified the Core and Runtime and started native
COLMAP/FFmpeg, then failed because the acceptance script combined two CLI modes
and looked for a report that mode does not generate. `--doctor` alone already
performs the full audit and emits JSON. The script was corrected without changing
the tested installer/Core. The second run **passed** against the same SHA-256 artifacts, including real
per-user installation, first-use Runtime setup, full hash verification, standalone
3.10/3.12 workers with package-only imports, native Unicode/long-path output,
rendered ModernUI/ClassicUI, and real uninstall preserving Runtime/project data.
Both downloaded runner screenshots were visually inspected. Windows runner OS:
10.0.20348 (Windows Server 2022). The temporary read-only asset secret was removed.
Successful run:
https://github.com/AureoleLab/GaussianOS/actions/runs/35417957032

This CPU runner does not establish GPU training on a second machine or GPU family.

## Size and disk accounting

Decimal bytes, excluding projects and the separately saved installer:

| Configuration | Download including installer | Installed Core + Runtime |
|---|---:|---:|
| Base workflow | 2784745518 | 4910368560 |
| All fallback components installed | 9632066368 | 13832484642 |

Installed Core is 663541620 bytes. Base Runtime is 2604125637 bytes compressed /
4246826940 installed; optional fallback adds 6847320850 / 8922116082 bytes.
Successful downloads are deleted after atomic installation; interrupted downloads
are retained for resume. No second full Runtime copy was created during final
acceptance. Updates reuse unchanged components.

The disk monitor began with 77560659968 free bytes on I:. Its recorded minimum
and latest free space are retained in `disk-peak.json`. Whole-volume growth also
includes unrelated user activity, so it is not claimed as build-only peak usage.
A 15000000000-byte reserve was maintained; user project/development data was not
deleted. At acceptance closure the recorded minimum was 21772832768 bytes free, current free
space was 21772832768 bytes, and whole-volume observed peak growth was 55787827200
bytes. These values must not be described as build-only disk consumption.

## Known Beta limits

Only RTX 5090 GPU execution has been tested. The compiled extension includes
7.5/8.0/8.6/8.9/9.0/10.0/12.0+PTX targets, but compilation is not hardware execution
proof. The installer is unsigned. Preview success does not guarantee quality for
arbitrary footage, large scenes, low-memory GPUs or dynamic content. Independent
Windows CPU acceptance complements, rather than replaces, GPU end-to-end testing.
