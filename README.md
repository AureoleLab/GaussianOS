# GaussianOS — Public Beta

GaussianOS is a Windows desktop workflow for static 3D Gaussian Splatting:
video/image import, FFmpeg frame sampling, COLMAP reconstruction with automatic
MapAnything fallback, gsplat training, Gaussian Viewer, Camera Timeline, and
Scene Bundle export. Both ModernUI and ClassicUI remain available.

## Install on Windows

Download **GaussianOS-0.1.0-beta.1-Setup-win-x64.exe** from the
[Windows Beta release](https://github.com/AureoleLab/GaussianOS/releases/tag/v0.1.0-beta.1).
Run the installer and launch GaussianOS. No Python, Conda, CUDA Toolkit, PATH
configuration, source checkout, terminal commands, or administrator rights are
required. The first-use window automatically downloads and verifies the base
Runtime; additional MapAnything resources are installed when fallback is needed.
Interrupted downloads resume, and verified downloads are removed after installation.

Create a project, import video or images, choose a reconstruction profile, and
run the Pipeline. Inspect the result in Viewer and Camera Timeline, then export
a Scene Bundle containing Gaussian PLY, point cloud, cameras and scene manifest.
Once the required components are installed, reconstruction can run offline.

The installer is 180.62 MB. A first base installation downloads about **2.78 GB**
in total and occupies **4.91 GB**; installing every fallback component raises
those totals to **9.63 GB downloaded / 13.83 GB installed**. Figures use decimal
GB and exclude project data, temporary processing files and the saved installer.
Keep additional free space for reconstruction. Updates reuse unchanged Runtime
components; uninstall preserves Runtime, projects and user-created data.

## Beta requirements and limits

- 64-bit Windows 10/11 and an NVIDIA GPU, compute capability 7.5 or newer.
- At least 8 GiB VRAM for the base workflow; 12 GiB or more for MapAnything,
  with more required by larger scenes. NVIDIA R580-or-newer driver required.
- GPU end-to-end execution has been tested on RTX 5090 with driver 591.44.
  Other compiled GPU architectures have not yet been executed in acceptance.
- Preview acceptance uses 12 selected frames and 1,000 training steps. It
  verifies operation and exports, not reconstruction quality for arbitrary media.
- The installer is unsigned; Windows may show an unknown-publisher warning.
  Check the release SHA-256. Do not disable system security protections.
- Dynamic scenes and CPU-only training are not supported.

The Start menu includes Classic UI and Diagnostics. See the
[quick start](packaging/QUICKSTART.md), [troubleshooting](packaging/TROUBLESHOOTING.md)
and [release acceptance record](docs/public-beta-acceptance.md).
The Core ZIP is an alternative for portable deployment; new users should choose
the installer. Keep all sibling directories together when moving a portable copy.

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

- Public Beta: per-user Windows installer and verified on-demand Runtime
- P3: deferred; no P3 functionality is included in this release

See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for distribution notices,
[SECURITY.md](SECURITY.md) for reporting, and [CONTRIBUTING.md](CONTRIBUTING.md)
for contribution rules.
