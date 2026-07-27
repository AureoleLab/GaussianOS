[CmdletBinding()]
param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot "..\release"),
    [Parameter(Mandatory)][string]$RuntimeSource,
    [string]$RuntimeManifestTemplate = (Join-Path $PSScriptRoot "..\dist\runtime-manifest.json"),
    [string]$SevenZip = (Join-Path $PSScriptRoot "..\.gaussian-factory\tools\7zip\7zr.exe"),
    [switch]$SkipArchive
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$output = [IO.Path]::GetFullPath($OutputDirectory)
$source = (Resolve-Path $RuntimeSource).Path
$template = (Resolve-Path $RuntimeManifestTemplate).Path
$buildRoot = Join-Path $root 'build\distribution-optimization\offline'
$package = Join-Path $output 'GaussianOS-Offline-Runtime-win-x64'
$runtime = Join-Path $package 'Runtime'

if ((Split-Path $source -Leaf).Equals('runtime', [StringComparison]::OrdinalIgnoreCase) -and
    (Test-Path -LiteralPath (Join-Path $source 'runtime'))) {
    throw "Runtime source contains forbidden runtime/runtime nesting: $source"
}
if (Test-Path -LiteralPath $buildRoot) {
    $resolvedBuild = [IO.Path]::GetFullPath($buildRoot)
    $allowedBuild = [IO.Path]::GetFullPath((Join-Path $root 'build'))
    if (-not $resolvedBuild.StartsWith($allowedBuild, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean unexpected build path: $resolvedBuild"
    }
    Remove-Item -LiteralPath $buildRoot -Recurse -Force
}
if (Test-Path -LiteralPath $package) {
    $resolvedPackage = [IO.Path]::GetFullPath($package)
    if (-not $resolvedPackage.StartsWith($output, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to replace unexpected package path: $resolvedPackage"
    }
    Remove-Item -LiteralPath $package -Recurse -Force
}
New-Item -ItemType Directory -Force -Path $buildRoot, $runtime | Out-Null

function Copy-Tree(
    [string]$Source,
    [string]$Destination,
    [string[]]$ExcludeDirectories = @()
) {
    if (-not (Test-Path -LiteralPath $Source -PathType Container)) {
        throw "Required Runtime component is missing: $Source"
    }
    New-Item -ItemType Directory -Force -Path $Destination | Out-Null
    $arguments = @(
        $Source,
        $Destination,
        '/E',
        '/COPY:DAT',
        '/DCOPY:DAT',
        '/R:2',
        '/W:1',
        '/NFL',
        '/NDL',
        '/NP'
    )
    if ($ExcludeDirectories.Count) {
        $arguments += '/XD'
        $arguments += $ExcludeDirectories
    }
    & robocopy.exe @arguments | Out-Host
    if ($LASTEXITCODE -gt 7) {
        throw "robocopy failed ($LASTEXITCODE): $Source"
    }
}

$directComponents = @(
    'tools\ffmpeg',
    'tools\colmap\3.13.0',
    'tools\git',
    'envs\gsplat-1.5.3',
    'envs\mapanything-1.1.2',
    'downloads\map-anything-apache-00f9c245',
    'downloads\dinov2-7764ea0'
)
foreach ($component in $directComponents) {
    Copy-Tree (Join-Path $source $component) (Join-Path $runtime $component)
}
$sourceComponents = @(
    'sources\gsplat-v1.5.3',
    'sources\map-anything-v1.1.2',
    'sources\dinov2-7764ea0'
)
foreach ($component in $sourceComponents) {
    Copy-Tree `
        (Join-Path $source $component) `
        (Join-Path $runtime $component) `
        @('.git', 'build', 'tests', 'docs', '__pycache__')
}

$finalManifest = Join-Path $package 'runtime-manifest.json'
& uv run python scripts/finalize_runtime_manifest.py `
    --template $template `
    --runtime $runtime `
    --output $finalManifest `
    --component gsplat-source `
    --component mapanything-source `
    --component dinov2-source
if ($LASTEXITCODE -ne 0) {
    throw 'Runtime manifest finalization failed.'
}

Copy-Item -LiteralPath `
    (Join-Path $root 'packaging\VERSION'), `
    (Join-Path $root 'packaging\QUICKSTART.md'), `
    (Join-Path $root 'packaging\TROUBLESHOOTING.md'), `
    (Join-Path $root 'packaging\DIRECTORY_LAYOUT.md'), `
    (Join-Path $root 'LICENSE'), `
    (Join-Path $root 'THIRD_PARTY_NOTICES.md') `
    -Destination $package

& uv run python scripts/package_policy.py build-manifest `
    --package $package `
    --product 'GaussianOS Offline Runtime' `
    --feature 'COLMAP 3.13.0 CUDA' `
    --feature 'MapAnything 1.1.2 fallback and locked models' `
    --feature 'gsplat 1.5.3 training environment' `
    --feature 'FFmpeg video import and portable Git'
if ($LASTEXITCODE -ne 0) {
    throw 'Offline Runtime build manifest generation failed.'
}

# One full tree verification is the release gate. It reads every Runtime file
# and does not use the development PATH to resolve component locations.
$previousDistributionRoot = $env:GAUSSIANOS_DISTRIBUTION_ROOT
try {
    $env:GAUSSIANOS_DISTRIBUTION_ROOT = $package
    & uv run python -c "from apps.desktop.portable import doctor_report; r=doctor_report(full=True); print(r.payload()); raise SystemExit(0 if r.runtime_status == 'ok' else 1)"
    if ($LASTEXITCODE -ne 0) {
        throw 'Assembled Offline Runtime failed full component verification.'
    }
} finally {
    if ($null -eq $previousDistributionRoot) {
        Remove-Item Env:\GAUSSIANOS_DISTRIBUTION_ROOT -ErrorAction SilentlyContinue
    } else {
        $env:GAUSSIANOS_DISTRIBUTION_ROOT = $previousDistributionRoot
    }
}

# The Core and Offline Runtime must carry the byte-identical manifest.
& (Join-Path $PSScriptRoot 'build_portable.ps1') `
    -OutputDirectory $output `
    -RuntimeManifest $finalManifest
if ($LASTEXITCODE -ne 0) {
    throw 'Portable Core build failed.'
}

$archive = Join-Path $output 'GaussianOS-Offline-Runtime-win-x64.zip'
if (-not $SkipArchive) {
    $sevenZipCommand = if (Test-Path -LiteralPath $SevenZip) {
        (Resolve-Path $SevenZip).Path
    } else {
        (Get-Command 7z.exe -ErrorAction SilentlyContinue).Source
    }
    Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue
    if ($sevenZipCommand) {
        Push-Location $output
        try {
            & $sevenZipCommand a -tzip -mx=5 -mmt=on $archive (Split-Path $package -Leaf) | Out-Host
            if ($LASTEXITCODE -ne 0) {
                throw '7-Zip Offline Runtime compression failed.'
            }
        } finally {
            Pop-Location
        }
    } else {
        Compress-Archive `
            -LiteralPath $package `
            -DestinationPath $archive `
            -CompressionLevel Optimal
    }
}

$files = @(Get-ChildItem -LiteralPath $package -Recurse -File)
$summary = [ordered]@{
    product = 'GaussianOS Offline Runtime'
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
    Set-Content -LiteralPath (Join-Path $output 'GaussianOS-Offline-Runtime-win-x64.manifest.json') -Encoding utf8
Copy-Item -LiteralPath $finalManifest -Destination (Join-Path $output 'runtime-manifest.json') -Force
Write-Host (
    "Offline Runtime: {0} files; {1} unpacked bytes; {2} archive bytes" -f `
        $summary.file_count, $summary.unpacked_bytes, $summary.compressed_bytes
)
