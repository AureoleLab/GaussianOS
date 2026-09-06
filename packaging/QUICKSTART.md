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
Large scenes and MapAnything may need substantially more VRAM. The application
checks compatibility and reports actionable failures; no CPU training fallback
is promised. Keep at least 5 GiB free for project processing in addition to the
installed resources, with more space for larger projects.

Installer updates preserve Runtime, Settings, Cache, Logs, Projects and Exports.
Uninstalling the application also preserves these user-created directories.
Diagnostics creates a ZIP in Logs without source videos or project artifacts.

## Legacy portable packages

The instructions below describe historical alpha portable archives. Only use a
Runtime whose manifest exactly matches that Core; do not mix alpha and Beta
Runtime manifests. Current Beta users should use the installer above.

1. Extract `GaussianOS-Portable-Core-win-x64.zip` to any writable directory.
2. Run `Start_GaussianOS.bat`. ModernUI is the default; use
   `Start_GaussianOS_Classic.bat` for ClassicUI.
3. A Core-only installation starts normally and reports that Runtime is not
   installed. Projects and exports remain available.
4. For offline use, extract `GaussianOS-Offline-Runtime-win-x64.7z` next to
   the Portable Core. Double-click the Offline Runtime package's
   `Start_GaussianOS.bat`; it imports and verifies Runtime on first use, then
   starts ModernUI. `Start_GaussianOS_Classic.bat` does the same for ClassicUI.
   To install without starting the application, run `Install_Runtime.bat`.

   The PowerShell equivalent from the Portable Core is:

   `Runtime_Manager.ps1 -Import "<offline-package-directory>"`

5. The Runtime-only archive does not contain `GaussianOS.exe`. For a single
   extract-and-run package, use `GaussianOS-Full-Offline-win-x64.7z`; its root
   contains both `Application` and `Runtime`, and `Start_GaussianOS.bat`
   launches directly.
6. Run `Doctor.ps1` after installation or after moving the portable folder.
7. For a Pipeline start or Worker failure, double-click
   `Generate_Diagnostics.bat`. It creates a sendable ZIP in `Logs` containing
   redacted system, Runtime integrity, GPU, and Worker execution diagnostics.
   It does not include videos, project contents, or process environment values.

Replace only `Application` when updating the Core. Keep `Runtime`, `Settings`,
`Cache`, `Logs`, `Projects`, and `Exports` to preserve user and Runtime data.
