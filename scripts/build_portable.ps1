[CmdletBinding()]
param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot "..\release"),
    [string]$RuntimeManifest = (Join-Path $PSScriptRoot "..\dist\runtime-manifest.json"),
    [switch]$SkipArchive
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$output = [IO.Path]::GetFullPath($OutputDirectory)
$manifestSource = (Resolve-Path $RuntimeManifest).Path
$buildRoot = Join-Path $root 'build\distribution-optimization\core'
$pyinstallerDist = Join-Path $buildRoot 'pyinstaller-dist'
$pyinstallerWork = Join-Path $buildRoot 'pyinstaller-work'
$specRoot = Join-Path $buildRoot 'spec'
$package = Join-Path $output 'GaussianOS-Portable-Core-win-x64'
$application = Join-Path $package 'Application'
$qmlData = (Join-Path $root 'apps\desktop\qml') + ';apps/desktop/qml'
$viewerData = (Join-Path $root 'apps\desktop\viewer_web') + ';apps/desktop/viewer_web'
$configsData = (Join-Path $root 'configs') + ';configs'
$workersData = (Join-Path $root 'workers') + ';workers'
$packagesData = (Join-Path $root 'packages') + ';packages'

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
New-Item -ItemType Directory -Force -Path `
    $buildRoot, $pyinstallerDist, $pyinstallerWork, $specRoot, $package | Out-Null

Push-Location $root
try {
    & uv run --with 'pyinstaller==6.17.0' pyinstaller `
        --noconfirm `
        --clean `
        --onedir `
        --name GaussianOS `
        --windowed `
        --distpath $pyinstallerDist `
        --workpath $pyinstallerWork `
        --specpath $specRoot `
        --hidden-import PySide6.QtWebEngineCore `
        --hidden-import PySide6.QtWebEngineQuick `
        --add-data $qmlData `
        --add-data $viewerData `
        --add-data $configsData `
        --add-data $workersData `
        --add-data $packagesData `
        apps/desktop/__main__.py
    if ($LASTEXITCODE -ne 0) {
        throw "PyInstaller failed ($LASTEXITCODE)."
    }
} finally {
    Pop-Location
}
Move-Item -LiteralPath (Join-Path $pyinstallerDist 'GaussianOS') -Destination $application

# External Runtime Pythons must never use Application\_internal as cwd: that
# directory contains CPython 3.13 extension modules from PyInstaller which can
# shadow the 3.10/3.12 Runtime stdlib. Keep a pure-Python worker host beside it.
$workerHost = Join-Path $application 'worker_host'
New-Item -ItemType Directory -Force -Path $workerHost | Out-Null
foreach ($directory in @('workers', 'packages', 'configs')) {
    $sourceDirectory = Join-Path $root $directory
    $destinationDirectory = Join-Path $workerHost $directory
    & robocopy.exe `
        $sourceDirectory `
        $destinationDirectory `
        /E /COPY:DAT /DCOPY:DAT /R:2 /W:1 /NFL /NDL /NP /XD __pycache__ | Out-Host
    if ($LASTEXITCODE -gt 7) {
        throw "Worker host copy failed ($LASTEXITCODE): $sourceDirectory"
    }
}

$pruneReport = Join-Path $buildRoot 'core-prune-report.json'
& uv run python scripts/package_policy.py prune `
    --application $application `
    --report $pruneReport
if ($LASTEXITCODE -ne 0) {
    throw 'Audited Core pruning failed.'
}

Copy-Item -LiteralPath $manifestSource -Destination (Join-Path $package 'runtime-manifest.json')
Copy-Item -LiteralPath `
    (Join-Path $root 'LICENSE'), `
    (Join-Path $root 'THIRD_PARTY_NOTICES.md'), `
    (Join-Path $root 'packaging\VERSION'), `
    (Join-Path $root 'packaging\CHANGELOG.md'), `
    (Join-Path $root 'packaging\QUICKSTART.md'), `
    (Join-Path $root 'packaging\TROUBLESHOOTING.md'), `
    (Join-Path $root 'packaging\DIRECTORY_LAYOUT.md'), `
    (Join-Path $root 'packaging\Start_GaussianOS.bat'), `
    (Join-Path $root 'packaging\Start_GaussianOS_Classic.bat'), `
    (Join-Path $root 'packaging\Doctor.ps1'), `
    (Join-Path $root 'packaging\Runtime_Manager.ps1') `
    -Destination $package
Copy-Item -LiteralPath $pruneReport -Destination (Join-Path $package 'prune-report.json')

foreach ($directory in 'Runtime', 'Settings', 'Cache', 'Logs', 'Projects', 'Exports') {
    $path = Join-Path $package $directory
    New-Item -ItemType Directory -Force -Path $path | Out-Null
    New-Item -ItemType File -Force -Path (Join-Path $path '.gaussianos-directory') | Out-Null
}

$auditReport = Join-Path $buildRoot 'core-package-audit.json'
& uv run python scripts/package_policy.py audit-core `
    --package $package `
    --report $auditReport
if ($LASTEXITCODE -ne 0) {
    throw 'Portable Core content gate failed.'
}
Copy-Item -LiteralPath $auditReport -Destination (Join-Path $package 'package-audit.json')

& uv run python scripts/package_policy.py build-manifest `
    --package $package `
    --product 'GaussianOS Portable Core' `
    --feature 'ModernUI and ClassicUI' `
    --feature 'Qt QML and WebEngine Viewer' `
    --feature 'Core-only project management and export access' `
    --feature 'Runtime detect/install/offline-import/verify/repair' `
    --prune-report $pruneReport
if ($LASTEXITCODE -ne 0) {
    throw 'Portable Core build manifest generation failed.'
}

$archive = Join-Path $output 'GaussianOS-Portable-Core-win-x64.zip'
if (-not $SkipArchive) {
    Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue
    Compress-Archive `
        -LiteralPath $package `
        -DestinationPath $archive `
        -CompressionLevel Optimal
}
$files = @(Get-ChildItem -LiteralPath $package -Recurse -File)
$summary = [ordered]@{
    product = 'GaussianOS Portable Core'
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
    Set-Content -LiteralPath (Join-Path $output 'GaussianOS-Portable-Core-win-x64.manifest.json') -Encoding utf8
Write-Host (
    "Portable Core: {0} files; {1} unpacked bytes; {2} archive bytes" -f `
        $summary.file_count, $summary.unpacked_bytes, $summary.compressed_bytes
)
