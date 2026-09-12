; Core is embedded for reliable installation; Runtime remains component-based.
#ifndef CorePackage
  #error CorePackage is required
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
CloseApplications=yes
RestartApplications=no
SetupLogging=yes
LicenseFile=..\LICENSE

[Files]
Source: "obsolete-core-files.tsv"; Flags: dontcopy
Source: "{#CorePackage}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

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

[Code]
procedure CurStepChanged(CurStep: TSetupStep);
var
  Entries: TArrayOfString;
  I, Separator, Suffix: Integer;
  RelativePath, ExpectedHash, ExistingFile, BackupFile: String;
begin
  if CurStep <> ssInstall then Exit;
  { Exact paths and hashes from the audited previous Core manifest. Never
    recursively delete Application or any user-data directory during upgrades. }
  ExtractTemporaryFile('obsolete-core-files.tsv');
  if not LoadStringsFromFile(ExpandConstant('{tmp}\obsolete-core-files.tsv'), Entries) then
    RaiseException('Could not read the verified Core migration inventory.');
  for I := 0 to GetArrayLength(Entries) - 1 do begin
    Separator := Pos('|', Entries[I]);
    if Separator <= 1 then Continue;
    RelativePath := Copy(Entries[I], 1, Separator - 1);
    StringChangeEx(RelativePath, '/', '\', True);
    ExpectedHash := Copy(Entries[I], Separator + 1, MaxInt);
    if (Pos('Application\', RelativePath) <> 1) or (Pos('..', RelativePath) <> 0) then
      RaiseException('Invalid Core migration path.');
    ExistingFile := ExpandConstant('{app}\') + RelativePath;
    if not FileExists(ExistingFile) then Continue;
    if CompareText(GetSHA256OfFile(ExistingFile), ExpectedHash) = 0 then begin
      if not DeleteFile(ExistingFile) then
        RaiseException('Close GaussianOS and retry the installation: ' + ExistingFile);
      Log('Removed audited obsolete Core file: ' + RelativePath);
    end else begin
      { Preserve an unexpectedly modified file rather than delete unknown data. }
      BackupFile := ExpandConstant('{app}\Cache\CoreUpgradeBackup\0.1.0-beta.1\') + RelativePath;
      Suffix := 0;
      while FileExists(BackupFile) do begin
        Suffix := Suffix + 1;
        BackupFile := ExpandConstant('{app}\Cache\CoreUpgradeBackup\0.1.0-beta.1\') + RelativePath + '.' + IntToStr(Suffix);
      end;
      if not ForceDirectories(ExtractFileDir(BackupFile)) or not RenameFile(ExistingFile, BackupFile) then
        RaiseException('Could not preserve an existing Core file. Close GaussianOS and retry: ' + ExistingFile);
      Log('Preserved modified obsolete Core file: ' + RelativePath);
    end;
  end;
end;
