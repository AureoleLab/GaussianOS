[CmdletBinding()]
param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot "..\portable-output"),
    [string]$FactoryRoot = (Join-Path $PSScriptRoot "..\.gaussian-factory"),
    [string]$DinoCheckpoint = (Join-Path $env:USERPROFILE ".cache\torch\hub\checkpoints\dinov2_vitg14_pretrain.pth"),
    [Parameter(Mandatory)][string]$FfmpegArchive,
    [string]$Python310Home = (Join-Path $env:APPDATA "uv\python\cpython-3.10-windows-x86_64-none"),
    [string]$Python312Home = (Join-Path $env:APPDATA "uv\python\cpython-3.12-windows-x86_64-none"),
    [string]$GitRoot = "C:\Program Files\Git",
    [string]$SevenZip = (Join-Path $PSScriptRoot "..\.gaussian-factory\tools\7zip\7zr.exe"),
    [switch]$SkipArchive
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$output = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Force -Path $output | Out-Null

function Copy-Tree([string]$Source, [string]$Destination, [string[]]$ExcludeDirectories = @()) {
    if (-not (Test-Path -LiteralPath $Source)) { throw "Required runtime source is missing: $Source" }
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    $arguments = @($Source, $Destination, '/E', '/COPY:DAT', '/DCOPY:DAT', '/R:2', '/W:1', '/NFL', '/NDL', '/NP')
    if ($ExcludeDirectories.Count) { $arguments += '/XD'; $arguments += $ExcludeDirectories }
    & robocopy.exe @arguments | Out-Host
    if ($LASTEXITCODE -gt 7) { throw "robocopy failed ($LASTEXITCODE): $Source" }
}

function Make-StandaloneEnvironment([string]$EnvironmentSource, [string]$PythonHome, [string]$Destination) {
    Copy-Tree $EnvironmentSource $Destination @('__pycache__')
    Copy-Tree $PythonHome $Destination @('__pycache__', 'site-packages')
    Remove-Item -LiteralPath (Join-Path $Destination 'pyvenv.cfg') -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $Destination 'Lib\site-packages\__editable__.mapanything-1.1.2.pth') -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath (Join-Path $Destination 'Lib\site-packages\__editable___mapanything_1_1_2_finder.py') -Force -ErrorAction SilentlyContinue
    Get-ChildItem -LiteralPath (Join-Path $Destination 'Scripts') -File -Filter 'activate*' -ErrorAction SilentlyContinue | Remove-Item -Force
}

& (Join-Path $PSScriptRoot 'build_portable.ps1') -OutputDirectory $output -SkipArchive
$core = Join-Path $output 'GaussianOS-Portable-Core-win-x64'
$full = Join-Path $output 'GaussianOS-Full-Offline-win-x64'
if (Test-Path -LiteralPath $full) { Remove-Item -LiteralPath $full -Recurse -Force }
Copy-Item -LiteralPath $core -Destination $full -Recurse -Force
$runtime = Join-Path $full 'runtime'

$ffmpegHash = '50764b52d38cb0baf8af938c0e4ca886d2c6753b520b2c319b532ed5c17e7cbf'
if ((Get-FileHash -LiteralPath $FfmpegArchive -Algorithm SHA256).Hash.ToLower() -ne $ffmpegHash) { throw 'FFmpeg archive SHA-256 mismatch.' }
$ffmpegTemp = Join-Path $root 'build\ffmpeg-portable'
if (Test-Path -LiteralPath $ffmpegTemp) { Remove-Item -LiteralPath $ffmpegTemp -Recurse -Force }
Expand-Archive -LiteralPath $FfmpegArchive -DestinationPath $ffmpegTemp
$ffmpegRoot = Get-ChildItem -LiteralPath $ffmpegTemp -Directory | Select-Object -First 1
Copy-Tree $ffmpegRoot.FullName (Join-Path $runtime 'tools\ffmpeg')

Copy-Tree (Join-Path $FactoryRoot 'tools\colmap\3.13.0') (Join-Path $runtime 'tools\colmap\3.13.0')
Get-ChildItem -LiteralPath (Join-Path $runtime 'tools\colmap\3.13.0') -Recurse -File -Filter '*.pdb' | Remove-Item -Force
Copy-Tree $GitRoot (Join-Path $runtime 'tools\git') @('usr\share\doc', 'mingw64\share\doc')
Make-StandaloneEnvironment (Join-Path $FactoryRoot 'envs\gsplat-1.5.3') $Python310Home (Join-Path $runtime 'envs\gsplat-1.5.3')
Make-StandaloneEnvironment (Join-Path $FactoryRoot 'envs\mapanything-1.1.2') $Python312Home (Join-Path $runtime 'envs\mapanything-1.1.2')
Copy-Tree (Join-Path $FactoryRoot 'sources\gsplat-v1.5.3') (Join-Path $runtime 'sources\gsplat-v1.5.3') @('build', 'tests', 'docs', '__pycache__')
Copy-Tree (Join-Path $FactoryRoot 'sources\map-anything-v1.1.2') (Join-Path $runtime 'sources\map-anything-v1.1.2') @('tests', '__pycache__')
Copy-Tree (Join-Path $FactoryRoot 'sources\dinov2-7764ea0') (Join-Path $runtime 'sources\dinov2-7764ea0') @('tests', '__pycache__')
Copy-Tree (Join-Path $FactoryRoot 'downloads\map-anything-apache-00f9c245') (Join-Path $runtime 'downloads\map-anything-apache-00f9c245')
$dinoTarget = Join-Path $runtime 'downloads\dinov2-7764ea0\dinov2_vitg14_pretrain.pth'
New-Item -ItemType Directory -Force -Path (Split-Path $dinoTarget) | Out-Null
Copy-Item -LiteralPath $DinoCheckpoint -Destination $dinoTarget

$bad = Get-ChildItem $full -Recurse -File -Include *.ply,*.scene-bundle,*.ckpt | Select-Object -First 1
if ($bad) { throw "Full Offline contains a forbidden project/training artifact: $($bad.FullName)" }

$doctor = Start-Process -FilePath (Join-Path $full 'GaussianOS.exe') -ArgumentList '--doctor' -WorkingDirectory $full -Wait -PassThru
if ($doctor.ExitCode -ne 0) { Get-Content (Join-Path $full 'doctor-report.txt') -ErrorAction SilentlyContinue; throw "Full Offline doctor failed ($($doctor.ExitCode))." }

$unpacked = (Get-ChildItem $full -Recurse -File | Measure-Object Length -Sum).Sum
$files = @(Get-ChildItem $full -Recurse -File).Count
$archive = Join-Path $output 'GaussianOS-Full-Offline-win-x64.7z'
if (-not $SkipArchive) {
    $sevenZip = if (Test-Path -LiteralPath $SevenZip) { (Resolve-Path $SevenZip).Path } else { (Get-Command 7z.exe -ErrorAction SilentlyContinue).Source }
    if (-not $sevenZip) { throw '7z.exe or the official standalone 7zr.exe is required to create the Full Offline archive.' }
    Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue
    & $sevenZip a -t7z -mx=7 -mmt=on $archive $full | Out-Host
    if ($LASTEXITCODE -ne 0) { throw '7-Zip compression failed.' }
}
$compressed = if (Test-Path $archive) { (Get-Item $archive).Length } else { 0 }
$archiveHash = if ($compressed) { (Get-FileHash $archive -Algorithm SHA256).Hash.ToLower() } else { $null }
[ordered]@{ archive=$archive; files=$files; unpacked_bytes=$unpacked; compressed_bytes=$compressed; sha256=$archiveHash } | ConvertTo-Json | Set-Content "$archive.manifest.json" -Encoding utf8
Write-Host "Full Offline: $files files; unpacked $unpacked bytes; archive $compressed bytes"
