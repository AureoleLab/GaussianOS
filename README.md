# GaussianOS — Alpha

GaussianOS is a Windows desktop workflow for static 3D Gaussian Splatting:
video/image import, quality-aware sampling, COLMAP reconstruction with a
locked MapAnything fallback, gsplat training, WebGL viewing, and PLY /
SceneBundle export. It is Alpha software, currently validated primarily on an
RTX 5090. It does not claim support for dynamic scenes.

## Portable Core

Download `GaussianOS-Portable-Core-win-x64.zip` from the Alpha Release, unzip
it anywhere writable, and run `GaussianOS.bat`. No administrator rights are
required. The first launch runs a runtime doctor. The Core archive deliberately
does not contain Worker runtimes or model weights; its in-app runtime screen
installs only version-locked, SHA-256-verified assets into `runtime/` beside the
application, so the folder remains portable. Interrupted downloads resume.

If the computer is offline, use the Runtime Import entry with a directory from
the approved Full Offline bundle. The doctor clearly reports missing runtime,
unsupported NVIDIA driver, and integrity failures. GPU reconstruction/training
requires a supported NVIDIA GPU and adequate VRAM.

`GaussianOS-Full-Offline-win-x64.7z`, when published, contains only approved
production runtime/model assets and is not stored in this source repository.

## Development

```powershell
uv sync --extra test --extra compatibility --extra desktop
uv run pytest
uv run gaussian-factory-gui
.\scripts\build_portable.ps1
```

The launcher defaults to ModernUI while retaining the production ClassicUI
compatibility shell:

```powershell
.\start_gaussian_os.bat --ui modern
.\start_gaussian_os.bat --ui classic
.\start_gaussian_os.bat --safe-ui
```

Command-line selection takes precedence over the persisted preference. If the
Modern QML root cannot load, startup records the QML error in
`~/.gaussian-factory/logs/desktop-ui.log` and loads ClassicUI in a fresh QML
engine. Interface changes made in Settings take effect after restart.

The production profile excludes research-only workers and unapproved models.
Never commit project data, model weights, runtime directories, generated PLY or
SceneBundle assets, videos, caches, or credentials.

## Roadmap

- P2.8: portable Windows Alpha and open-source release
- P3: deferred; no P3 functionality is included in this release

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for distribution notices,
[SECURITY.md](SECURITY.md) for reporting, and [CONTRIBUTING.md](CONTRIBUTING.md)
for contribution rules.
