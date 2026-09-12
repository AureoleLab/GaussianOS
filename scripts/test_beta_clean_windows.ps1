# Run on a fresh GitHub-hosted Windows runner against the exact draft assets.
# No GPU reconstruction is claimed here; the local GPU acceptance is separate.
$ErrorActionPreference = 'Stop'
$assetLinks = $env:BETA_ASSET_URLS_JSON | ConvertFrom-Json
if (-not $assetLinks) { throw 'Temporary read-only draft asset links are missing.' }
foreach ($link in $assetLinks) { Write-Output "::add-mask::$($link.url)" }
function Download-BetaAsset([string]$Filename, [string]$Directory) {
    $links = @($assetLinks | Where-Object { $_.filename -eq $Filename })
    if ($links.Count -ne 1) { throw "No unique read-only link for $Filename" }
    Invoke-WebRequest -Uri $links[0].url -OutFile (Join-Path $Directory $Filename) -TimeoutSec 1200 -MaximumRetryCount 3 -RetryIntervalSec 3
}
$releaseConfig = Get-Content -LiteralPath (Join-Path $PSScriptRoot '../docs/beta-ci-trigger.json') -Raw | ConvertFrom-Json
if (-not $env:BETA_TAG) { $env:BETA_TAG = $releaseConfig.tag }
if (-not $env:BETA_CORE_SHA256) { $env:BETA_CORE_SHA256 = $releaseConfig.core_sha256 }
$root = Join-Path $env:RUNNER_TEMP 'GaussianOS-Clean-Acceptance'
if (Test-Path -LiteralPath $root) { throw 'Clean acceptance directory already exists.' }
$evidence = Join-Path $root 'evidence'
$downloads = Join-Path $root 'downloads'
$installed = Join-Path $root '中文 Beta with spaces'
New-Item -ItemType Directory -Path $evidence,$downloads,$installed | Out-Null
if ($env:BETA_CORE_SHA256 -notmatch '^[a-f0-9]{64}$') { throw 'Expected Core SHA-256 is invalid.' }
Download-BetaAsset 'GaussianOS-Core-win-x64.zip' $downloads
$core = Join-Path $downloads 'GaussianOS-Core-win-x64.zip'
$coreHash = (Get-FileHash -LiteralPath $core -Algorithm SHA256).Hash.ToLower()
if ($coreHash -ne $env:BETA_CORE_SHA256) { throw 'Core release asset SHA-256 mismatch.' }
Download-BetaAsset 'GaussianOS-0.1.0-beta.1-Setup-win-x64.exe' $downloads
$setup = Join-Path $downloads 'GaussianOS-0.1.0-beta.1-Setup-win-x64.exe'
$setupHash = (Get-FileHash -LiteralPath $setup -Algorithm SHA256).Hash.ToLower()
if ($setupHash -ne $releaseConfig.installer_sha256) { throw 'Installer SHA-256 mismatch.' }
$setupArgs = @('/CURRENTUSER','/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',('/DIR="' + $installed + '"'),('/LOG="' + (Join-Path $evidence 'install.log') + '"'))
$setupProcess = Start-Process -FilePath $setup -ArgumentList $setupArgs -WindowStyle Hidden -PassThru -Wait
if ($setupProcess.ExitCode -ne 0) { throw "Real installer failed: $($setupProcess.ExitCode)" }
Add-Type -AssemblyName System.IO.Compression.FileSystem
$archive = [IO.Compression.ZipFile]::OpenRead($core)
try {
    $reader = [IO.StreamReader]::new($archive.GetEntry('build-manifest.json').Open())
    try { $expectedBuildManifest = $reader.ReadToEnd() } finally { $reader.Dispose() }
} finally { $archive.Dispose() }
if ([IO.File]::ReadAllText((Join-Path $installed 'build-manifest.json')) -ne $expectedBuildManifest) { throw 'Installer Core differs from independently hashed Core archive.' }
$coreInventory = $expectedBuildManifest | ConvertFrom-Json
foreach ($entry in $coreInventory.files) {
    $path = [IO.Path]::GetFullPath((Join-Path $installed $entry.path))
    if (-not $path.StartsWith($installed + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'Core inventory path escaped installation.' }
    if (-not (Test-Path -LiteralPath $path) -or (Get-Item -LiteralPath $path).Length -ne $entry.size_bytes -or (Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLower() -ne $entry.sha256) {
        throw "Installed Core content does not match its build manifest: $($entry.path)"
    }
}
$manifest = Get-Content -LiteralPath (Join-Path $installed 'runtime-manifest.json') -Raw | ConvertFrom-Json
$cache = Join-Path $installed 'Cache\RuntimeDownloads'
New-Item -ItemType Directory -Path $cache -Force | Out-Null
# Test both independent CPython ABIs; omit large inference models on this CPU
# runner, while retaining the full base runtime and its required LPIPS weights.
$components = @($manifest.components | Where-Object { $_.required -or $_.component_id -in @('mapanything-source','mapanything-environment','dinov2-source') })
foreach ($component in $components) {
    foreach ($part in $component.source.artifact.parts) {
        Download-BetaAsset $part.filename $cache
    }
}
Remove-Item Env:BETA_ASSET_URLS_JSON
# From this point, every application/worker launch uses the package with an
# empty user profile and hostile Python/Conda variables. No checkout import.
$profileRoot = Join-Path $root 'Empty Profile'
New-Item -ItemType Directory -Path $profileRoot | Out-Null
$env:USERPROFILE = $profileRoot
$env:APPDATA = Join-Path $profileRoot 'Roaming'
$env:LOCALAPPDATA = Join-Path $profileRoot 'Local'
New-Item -ItemType Directory -Path $env:APPDATA,$env:LOCALAPPDATA | Out-Null
$env:PATH = "$env:SystemRoot\System32;$env:SystemRoot;$env:SystemRoot\System32\Wbem"
$env:PYTHONHOME = 'Z:\absent-python'
$env:PYTHONPATH = 'Z:\absent-checkout'
$env:CONDA_PREFIX = 'Z:\absent-conda'
$exe = Join-Path $installed 'Application\GaussianOS.exe'
$firstUse = Start-Process -FilePath $exe -ArgumentList '--runtime-setup' -WorkingDirectory $profileRoot -WindowStyle Hidden -PassThru
if (-not $firstUse.WaitForExit(1200000)) { $firstUse.Kill(); throw 'Graphical first-use setup timed out.' }
if ($firstUse.ExitCode -ne 0) {
    Copy-Item -LiteralPath (Join-Path $installed 'Logs\runtime-setup-error.txt') -Destination $evidence -ErrorAction SilentlyContinue
    throw "Graphical first-use setup failed: $($firstUse.ExitCode)"
}
foreach ($component in @($components | Where-Object { -not $_.required })) {
    $p = Start-Process -FilePath $exe -ArgumentList @('--runtime-install',$component.component_id) -WorkingDirectory $profileRoot -WindowStyle Hidden -PassThru -Wait
    if ($p.ExitCode -notin @(0,2,4)) { throw "Runtime installer failed: $($component.component_id): $($p.ExitCode)" }
}
foreach ($component in $components) {
    if (-not (Test-Path -LiteralPath (Join-Path (Join-Path $installed 'Runtime') $component.relative_install_path))) {
        throw "Requested Runtime component did not install: $($component.component_id)"
    }
}
$colmap = Join-Path $installed 'Runtime\tools\colmap\3.13.0\bin\colmap.exe'
$crtLock = Get-Content -LiteralPath (Join-Path $PSScriptRoot '../third_party/locks/microsoft-vc-runtime.json') -Raw | ConvertFrom-Json
foreach ($file in $crtLock.files) {
    $native = Join-Path (Split-Path $colmap) $file.filename
    if (-not (Test-Path -LiteralPath $native) -or (Get-FileHash -LiteralPath $native -Algorithm SHA256).Hash.ToLower() -ne $file.sha256) {
        throw "COLMAP must carry its own locked C++ dependency: $($file.filename)"
    }
}
& $colmap -h *> (Join-Path $evidence 'colmap-native-help.txt')
if ($LASTEXITCODE -ne 0) { throw 'Native COLMAP cannot start from the installed package.' }
& (Join-Path $installed 'Runtime\tools\ffmpeg\bin\ffmpeg.exe') -version *> (Join-Path $evidence 'ffmpeg-native-version.txt')
if ($LASTEXITCODE -ne 0) { throw 'Native FFmpeg cannot start from the installed package.' }
$p = Start-Process -FilePath $exe -ArgumentList @('--doctor','--runtime-verify-full') -WorkingDirectory $profileRoot -WindowStyle Hidden -PassThru -Wait
$doctor = Get-Content -LiteralPath (Join-Path $installed 'Logs\doctor-report.json') -Raw | ConvertFrom-Json
Copy-Item -LiteralPath (Join-Path $installed 'Logs\doctor-report.json') -Destination $evidence
if ($doctor.core_status -ne 'ok' -or $doctor.runtime_status -ne 'ok') { throw 'Packaged full Runtime integrity failed.' }
$probes = @()
foreach ($entry in @(@('gsplat-1.5.3','workers.recon_colmap'),@('gsplat-1.5.3','workers.train_gsplat'),@('mapanything-1.1.2','workers.recon_mapanything'))) {
    $python = Join-Path $installed "Runtime\envs\$($entry[0])\python.exe"
    $log = Join-Path $evidence "$($entry[1]).txt"
    Push-Location $profileRoot
    try {
        & $python -B -X utf8 -m $entry[1] --help *> $log
        if ($LASTEXITCODE -ne 0) { throw "Standalone worker launch failed: $($entry[1])" }
        $probe = & $python -B -X utf8 -c 'import json,sys,torch,numpy,safetensors; print(json.dumps(dict(executable=sys.executable, prefix=sys.prefix, paths=sys.path, torch=torch.__version__, cuda_available=torch.cuda.is_available())))'
        if ($LASTEXITCODE -ne 0) { throw "Standalone native dependency load failed: $($entry[0])" }
        $parsed = $probe | ConvertFrom-Json
        foreach ($path in $parsed.paths) {
            if (-not ([IO.Path]::GetFullPath($path)).StartsWith($installed + '\', [StringComparison]::OrdinalIgnoreCase)) { throw "Worker import path escaped package: $path" }
        }
        $probes += $parsed
        if ($entry[0] -eq 'mapanything-1.1.2') {
            $nativeProbe = @'
from pathlib import Path
import pycolmap
from packages.native_paths import native_output_directory
root = Path.cwd() / '中文 Native Path' / ('long-' + 'x'*100) / ('long-' + 'y'*100)
with native_output_directory(root):
    Path('sparse').mkdir()
    pycolmap.Reconstruction().write('sparse')
assert (root / 'sparse/cameras.bin').is_file()
print('pycolmap Unicode and long-path output: passed')
'@
            & $python -B -X utf8 -c $nativeProbe *> (Join-Path $evidence 'pycolmap-native-path.txt')
            if ($LASTEXITCODE -ne 0) { throw 'Native Unicode/long-path reconstruction output failed.' }
        }
    } finally { Pop-Location }
}
foreach ($ui in @('modern','classic')) {
    $png = Join-Path $evidence "$ui.png"
    $arguments = @('--ui',$ui,'--acceptance-evidence',('"' + $png + '"'),'--acceptance-delay-ms','15000')
    # A rendered WebEngine gate needs a visible application window, not SW_HIDE.
    $p = Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $profileRoot -WindowStyle Normal -PassThru
    if (-not $p.WaitForExit(90000)) { $p.Kill(); throw "$ui UI acceptance timed out." }
    if ($p.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $png)) { throw "$ui UI acceptance failed." }
    $guiReport = Get-Content -LiteralPath ([IO.Path]::ChangeExtension($png, '.json')) -Raw | ConvertFrom-Json
    if ($guiReport.status -ne 'succeeded' -or $guiReport.ui_loaded -ne $ui) { throw "$ui rendered UI report failed." }
}
Copy-Item -LiteralPath (Join-Path $installed 'Logs\desktop-ui.log') -Destination $evidence
$sentinel = Join-Path $installed 'Projects\acceptance-preserve\project.json'
New-Item -ItemType Directory -Path (Split-Path $sentinel) -Force | Out-Null
[IO.File]::WriteAllText($sentinel, '{"test":"preserve user data"}')
$uninstaller = Join-Path $installed 'unins000.exe'
$uninstallArgs = @('/VERYSILENT','/SUPPRESSMSGBOXES','/NORESTART',('/LOG="' + (Join-Path $evidence 'uninstall.log') + '"'))
$uninstall = Start-Process -FilePath $uninstaller -ArgumentList $uninstallArgs -WindowStyle Hidden -PassThru -Wait
if ($uninstall.ExitCode -ne 0 -or (Test-Path -LiteralPath $exe)) { throw 'Real uninstaller failed.' }
if ([IO.File]::ReadAllText($sentinel) -ne '{"test":"preserve user data"}') { throw 'Uninstaller modified user project data.' }
if (-not (Test-Path -LiteralPath (Join-Path $installed 'Runtime\envs\gsplat-1.5.3\python.exe'))) { throw 'Uninstaller removed reusable Runtime.' }
[ordered]@{ status='succeeded'; core_sha256=$coreHash; installer_sha256=$setupHash; install_and_uninstall='passed'; runner_os=[Environment]::OSVersion.VersionString;
    worker_probes=$probes; scope='Fresh Windows runner, exact draft artifacts, empty profile, isolated PATH. No GPU pipeline claimed.' } |
    ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $evidence 'report.json') -Encoding utf8
