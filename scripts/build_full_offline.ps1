[CmdletBinding()]
param(
    [string]$OutputDirectory = '',
    [Parameter(Mandatory)][string]$PortableCoreDirectory,
    [Parameter(Mandatory)][string]$OfflineRuntimeDirectory,
    [string]$SevenZip = '',
    [switch]$SkipArchive
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $root 'release'
}
if (-not $SevenZip) {
    $SevenZip = Join-Path $root '.gaussian-factory\tools\7zip\7zr.exe'
}
$output = [IO.Path]::GetFullPath($OutputDirectory)
$core = (Resolve-Path $PortableCoreDirectory).Path
$offline = (Resolve-Path $OfflineRuntimeDirectory).Path
$package = Join-Path $output 'GaussianOS-Full-Offline-win-x64'
$archive = Join-Path $output 'GaussianOS-Full-Offline-win-x64.7z'

if (-not (Test-Path -LiteralPath (Join-Path $core 'Application\GaussianOS.exe') -PathType Leaf)) {
    throw "Portable Core is missing Application\GaussianOS.exe: $core"
}
$runtimeSource = Join-Path $offline 'Runtime'
if (-not (Test-Path -LiteralPath $runtimeSource -PathType Container)) {
    throw "Offline Runtime is missing its Runtime directory: $offline"
}
$coreManifest = Join-Path $core 'runtime-manifest.json'
$offlineManifest = Join-Path $offline 'runtime-manifest.json'
if (-not (Test-Path -LiteralPath $coreManifest -PathType Leaf) -or
    -not (Test-Path -LiteralPath $offlineManifest -PathType Leaf)) {
    throw 'Core or Offline Runtime manifest is missing.'
}
if ((Get-FileHash -LiteralPath $coreManifest -Algorithm SHA256).Hash -ne
    (Get-FileHash -LiteralPath $offlineManifest -Algorithm SHA256).Hash) {
    throw 'Portable Core and Offline Runtime manifests differ.'
}
if (Test-Path -LiteralPath (Join-Path $runtimeSource 'Runtime')) {
    throw "Offline Runtime contains forbidden Runtime\Runtime nesting."
}

function Copy-Tree([string]$Source, [string]$Destination) {
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    & robocopy.exe `
        $Source `
        $Destination `
        /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NP | Out-Host
    if ($LASTEXITCODE -gt 7) {
        throw "robocopy failed ($LASTEXITCODE): $Source"
    }
}

if (Test-Path -LiteralPath $package) {
    $resolvedPackage = [IO.Path]::GetFullPath($package)
    if (-not $resolvedPackage.StartsWith(
        [IO.Path]::GetFullPath($output),
        [StringComparison]::OrdinalIgnoreCase
    )) {
        throw "Refusing to replace unexpected package path: $resolvedPackage"
    }
    Remove-Item -LiteralPath $package -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $package | Out-Null
Copy-Tree $core $package
Copy-Tree $runtimeSource (Join-Path $package 'Runtime')

if (Test-Path -LiteralPath (Join-Path $package 'Runtime\Runtime')) {
    throw 'Full Offline package contains forbidden Runtime\Runtime nesting.'
}
foreach ($required in @(
    'Application\GaussianOS.exe',
    'Runtime',
    'Start_GaussianOS.bat',
    'Start_GaussianOS_Classic.bat',
    'Doctor.ps1',
    'Runtime_Manager.ps1',
    'runtime-manifest.json'
)) {
    if (-not (Test-Path -LiteralPath (Join-Path $package $required))) {
        throw "Full Offline package is missing: $required"
    }
}

$previousDistributionRoot = $env:GAUSSIANOS_DISTRIBUTION_ROOT
try {
    $env:GAUSSIANOS_DISTRIBUTION_ROOT = $package
    & uv run python -c "from apps.desktop.portable import doctor_report; r=doctor_report(full=True); print(r.payload()); raise SystemExit(r.exit_code)"
    if ($LASTEXITCODE -ne 0) {
        throw 'Full Offline package failed complete doctor verification.'
    }
} finally {
    if ($null -eq $previousDistributionRoot) {
        Remove-Item Env:\GAUSSIANOS_DISTRIBUTION_ROOT -ErrorAction SilentlyContinue
    } else {
        $env:GAUSSIANOS_DISTRIBUTION_ROOT = $previousDistributionRoot
    }
}

& uv run python scripts/package_policy.py build-manifest `
    --package $package `
    --product 'GaussianOS Full Offline' `
    --feature 'ModernUI and ClassicUI' `
    --feature 'Qt QML and WebEngine Viewer' `
    --feature 'COLMAP, MapAnything, gsplat, FFmpeg, models and tools' `
    --feature 'single-folder offline launch'
if ($LASTEXITCODE -ne 0) {
    throw 'Full Offline build manifest generation failed.'
}

if (-not $SkipArchive) {
    $sevenZipCommand = if (Test-Path -LiteralPath $SevenZip) {
        (Resolve-Path $SevenZip).Path
    } else {
        (Get-Command 7z.exe -ErrorAction SilentlyContinue).Source
    }
    if (-not $sevenZipCommand) {
        throw '7z.exe or the approved standalone 7zr.exe is required.'
    }
    Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue
    Push-Location $output
    try {
        & $sevenZipCommand a -t7z -mx=7 -mmt=on $archive (Split-Path $package -Leaf) | Out-Host
        if ($LASTEXITCODE -ne 0) {
            throw 'Full Offline compression failed.'
        }
    } finally {
        Pop-Location
    }
}

$files = @(Get-ChildItem -LiteralPath $package -Recurse -File)
$summary = [ordered]@{
    product = 'GaussianOS Full Offline'
    package_directory = $package
    archive = if (Test-Path -LiteralPath $archive) { $archive } else { $null }
    file_count = $files.Count
    unpacked_bytes = [int64](($files | Measure-Object Length -Sum).Sum)
    compressed_bytes = if (Test-Path -LiteralPath $archive) {
        (Get-Item -LiteralPath $archive).Length
    } else { 0 }
    sha256 = if (Test-Path -LiteralPath $archive) {
        (Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLower()
    } else { $null }
}
$summary | ConvertTo-Json -Depth 5 |
    Set-Content -LiteralPath (Join-Path $output 'GaussianOS-Full-Offline-win-x64.manifest.json') -Encoding utf8
Write-Host (
    "Full Offline: {0} files; {1} unpacked bytes; {2} archive bytes" -f `
        $summary.file_count, $summary.unpacked_bytes, $summary.compressed_bytes
)
