; Compile with /DCoreURL=... /DCoreSHA256=... /DCoreInstalledBytes=...
; Core hash is pinned into this installer; Runtime hashes are pinned in Core.
#ifndef CoreURL
  #error CoreURL is required
#endif
#ifndef CoreSHA256
  #error CoreSHA256 is required
#endif
#ifndef CoreInstalledBytes
  #error CoreInstalledBytes is required
#endif
#ifndef ReleaseOutput
  #define ReleaseOutput "..\build\public-beta\release"
#endif

[Setup]
AppId={{1DBE1C87-3ED3-4A6F-A873-0E79F4E58550}
AppName=GaussianOS
AppVersion=0.1.0-beta.1
AppPublisher=AureoleLab
AppPublisherURL=https://github.com/AureoleLab/GaussianOS
DefaultDirName={localappdata}\GaussianOS
DefaultGroupName=GaussianOS
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0.17763
WizardStyle=modern
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\Application\GaussianOS.exe
OutputDir={#ReleaseOutput}
OutputBaseFilename=GaussianOS-0.1.0-beta.1-Setup-win-x64
Compression=lzma2
SolidCompression=yes
ArchiveExtraction=auto
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
LicenseFile=..\LICENSE

[Files]
Source: "{#CoreURL}"; DestName: "GaussianOS-Core.zip"; DestDir: "{app}"; Hash: "{#CoreSHA256}"; ExternalSize: {#CoreInstalledBytes}; Flags: external download extractarchive recursesubdirs ignoreversion

[Tasks]
Name: desktopicon; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Icons]
Name: "{group}\GaussianOS"; Filename: "{app}\Application\GaussianOS.exe"; WorkingDir: "{app}"
Name: "{group}\GaussianOS Classic"; Filename: "{app}\Application\GaussianOS.exe"; Parameters: "--ui classic"; WorkingDir: "{app}"
Name: "{group}\GaussianOS Diagnostics"; Filename: "{app}\Application\GaussianOS.exe"; Parameters: "--diagnostic-zip"; WorkingDir: "{app}"
Name: "{autodesktop}\GaussianOS"; Filename: "{app}\Application\GaussianOS.exe"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\Application\GaussianOS.exe"; Description: "Launch GaussianOS and prepare reconstruction resources"; Flags: nowait postinstall skipifsilent

; Runtime, Settings, Cache, Logs, Projects and Exports are created by the app,
; not owned by this uninstaller. Never recursively remove the application root.
