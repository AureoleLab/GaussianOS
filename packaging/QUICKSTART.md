# GaussianOS Portable Quick Start

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

Replace only `Application` when updating the Core. Keep `Runtime`, `Settings`,
`Cache`, `Logs`, `Projects`, and `Exports` to preserve user and Runtime data.
