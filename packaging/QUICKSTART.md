# GaussianOS Public Beta Quick Start

For a new installation, run `GaussianOS-0.1.0-beta.1-Setup-win-x64.exe`.
Choose a writable installation location and launch GaussianOS. The first-use
window downloads and verifies the reconstruction resources automatically; an
interrupted download resumes on the next launch. Python, Conda, CUDA Toolkit,
PATH changes and terminal commands are not required.

Create a project, import a video or images, choose a quality preset and start
the Pipeline. If ordinary camera reconstruction needs MapAnything, GaussianOS
automatically downloads its additional environment and full model before
continuing. This first fallback needs an Internet connection. Once all required
resources are installed, the same features can run offline.

Use Viewer and Camera Timeline to inspect the completed reconstruction, then
export a Scene Bundle to a directory you choose. Projects from earlier versions
remain supported. The Start menu also includes Classic UI and Diagnostics.

Reconstruction requires 64-bit Windows 10/11, an NVIDIA GPU with at least 8 GiB
VRAM and compute capability 7.5 or newer, and an R580-or-newer NVIDIA driver.
For MapAnything, use 12 GiB or more VRAM; larger scenes can require 16 GiB or more. Only the listed release acceptance hardware has been executed; other supported architectures remain Beta coverage. The application
checks compatibility and reports actionable failures; no CPU training fallback
is promised. Keep at least 5 GiB free for project processing in addition to the
installed resources, with more space for larger projects.

Installer updates preserve Runtime, Settings, Cache, Logs, Projects and Exports.
Uninstalling the application also preserves these user-created directories.
Diagnostics creates a ZIP in Logs without source videos or project artifacts.
