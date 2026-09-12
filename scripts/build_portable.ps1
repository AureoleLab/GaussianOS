[CmdletBinding()]
param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot "..\release"),
    [string]$RuntimeManifest = (Join-Path $PSScriptRoot "..\dist\runtime-manifest.json"),
    [switch]$SkipArchive
)
$ErrorActionPreference = 'Stop'
# Resolve the build tool before discarding the caller's tool/Conda/Qt PATH.
$uvExecutable = (Get-Command uv -ErrorAction Stop).Source
$buildEnvironment = Join-Path $PSScriptRoot '..\build\public-beta\gui-build-env'
$buildEnvironment = [IO.Path]::GetFullPath($buildEnvironment)
$buildPython = Join-Path $buildEnvironment 'Scripts\python.exe'
$savedEnvironment = @{}
Get-ChildItem Env: | Where-Object {
    $_.Name -match '^(PATH$|PYTHON|CONDA|CUDA|QT_|QML|VIRTUAL_ENV$|UV_PROJECT_ENVIRONMENT$|UV_PYTHON_PREFERENCE$)'
} | ForEach-Object {
    $savedEnvironment[$_.Name] = $_.Value
    Remove-Item -LiteralPath ('Env:' + $_.Name)
}
try {
$env:PATH = (Join-Path $env:SystemRoot 'System32') + ';' + $env:SystemRoot
$env:UV_PROJECT_ENVIRONMENT = $buildEnvironment
$env:UV_PYTHON_PREFERENCE = 'only-managed'
$env:PYTHONNOUSERSITE = '1'
$env:PYTHONDONTWRITEBYTECODE = '1'
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
    $allowedBuild = [IO.Path]::GetFullPath((Join-Path $root 'build')) + [IO.Path]::DirectorySeparatorChar
    if (-not $resolvedBuild.StartsWith($allowedBuild, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean unexpected build path: $resolvedBuild"
    }
    Remove-Item -LiteralPath $buildRoot -Recurse -Force
}
if (Test-Path -LiteralPath $package) {
    $resolvedPackage = [IO.Path]::GetFullPath($package)
    if (-not $resolvedPackage.StartsWith($output.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to replace unexpected package path: $resolvedPackage"
    }
    Remove-Item -LiteralPath $package -Recurse -Force
}
New-Item -ItemType Directory -Force -Path `
    $buildRoot, $pyinstallerDist, $pyinstallerWork, $specRoot, $package | Out-Null

Push-Location $root
try {
    & $uvExecutable python install 3.13.9
    if ($LASTEXITCODE -ne 0) { throw 'Managed build Python installation failed.' }
    $managedPython = & $uvExecutable python find 3.13.9
    if ($LASTEXITCODE -ne 0) { throw 'Managed build Python resolution failed.' }
    $managedPython = $managedPython.Trim()
    & $uvExecutable sync --frozen --extra desktop --extra compatibility --no-dev --python $managedPython
    if ($LASTEXITCODE -ne 0) { throw 'Locked GUI environment synchronization failed.' }
    & $uvExecutable pip install --python $buildPython --requirements packaging/build-requirements.txt
    if ($LASTEXITCODE -ne 0) { throw 'Pinned packager installation failed.' }
    & $buildPython -B -c "import sys; from apps.desktop.main import _qt; assert sys.version_info[:3] == (3, 13, 9); _qt()"
    if ($LASTEXITCODE -ne 0) { throw 'Isolated source Qt import failed.' }
    & $buildPython -B -m PyInstaller `
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
        --hidden-import PySide6.QtWebChannel `
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

# Refuse native libraries captured from unrelated tools, even if they happen
# to satisfy a DLL filename. Record source hashes outside the shipped payload.
$nativeAudit = Join-Path $buildRoot 'native-origin-audit.json'
& $buildPython -B (Join-Path $root 'scripts/audit_native_origins.py') `
    --toc (Join-Path $pyinstallerWork 'GaussianOS\Analysis-00.toc') `
    --application $application --report $nativeAudit
if ($LASTEXITCODE -ne 0) { throw 'Native dependency provenance gate failed.' }

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
& $buildPython -B (Join-Path $root 'scripts/package_policy.py') prune `
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
    (Join-Path $root 'packaging\managed-installation.json'), `
    (Join-Path $root 'packaging\Start_GaussianOS.bat'), `
    (Join-Path $root 'packaging\Start_GaussianOS_Classic.bat'), `
    (Join-Path $root 'packaging\Doctor.ps1'), `
    (Join-Path $root 'packaging\Generate_Diagnostics.bat'), `
    (Join-Path $root 'packaging\Runtime_Manager.ps1') `
    -Destination $package
Copy-Item -LiteralPath $pruneReport -Destination (Join-Path $package 'prune-report.json')

foreach ($directory in 'Runtime', 'Settings', 'Cache', 'Logs', 'Projects', 'Exports') {
    $path = Join-Path $package $directory
    New-Item -ItemType Directory -Force -Path $path | Out-Null
    New-Item -ItemType File -Force -Path (Join-Path $path '.gaussianos-directory') | Out-Null
}

# The import-only CLI cannot open a native exception dialog. Fail the build
# before archiving if Qt or WebEngine cannot actually load in the frozen EXE.
$probe = Start-Process -FilePath (Join-Path $application 'GaussianOS.exe') `
    -ArgumentList '--gui-import-probe' -WorkingDirectory $package -WindowStyle Hidden -PassThru
if (-not $probe.WaitForExit(60000)) {
    Stop-Process -Id $probe.Id -Force
    throw 'Frozen GUI import probe timed out.'
}
if ($probe.ExitCode -ne 0) { throw 'Frozen GUI import probe failed; inspect Logs/gui-import-probe.json.' }
$probeReport = Join-Path $package 'Logs\gui-import-probe.json'
if ((Get-Content -LiteralPath $probeReport -Raw | ConvertFrom-Json).status -ne 'succeeded') {
    throw 'Frozen GUI import result was not successful.'
}
Move-Item -LiteralPath $probeReport -Destination (Join-Path $buildRoot 'gui-import-probe.json')
# Generated probe logs are evidence, never distributable data.



$auditReport = Join-Path $buildRoot 'core-package-audit.json'
& $buildPython -B (Join-Path $root 'scripts/package_policy.py') audit-core `
    --package $package `
    --report $auditReport
if ($LASTEXITCODE -ne 0) {
    throw 'Portable Core content gate failed.'
}
Copy-Item -LiteralPath $auditReport -Destination (Join-Path $package 'package-audit.json')

& $buildPython -B (Join-Path $root 'scripts/package_policy.py') build-manifest `
    --package $package `
    --product 'GaussianOS Portable Core' `
    --feature 'ModernUI and ClassicUI' `
    --feature 'Qt QML and WebEngine Viewer' `
    --feature 'Core-only project management and export access' `
    --feature 'Runtime detect/install/offline-import/verify/repair' `
    --feature 'privacy-safe one-click diagnostic ZIP' `
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

} finally {
    Get-ChildItem Env: | Where-Object {
        $_.Name -match '^(PATH$|PYTHON|CONDA|CUDA|QT_|QML|VIRTUAL_ENV$|UV_PROJECT_ENVIRONMENT$|UV_PYTHON_PREFERENCE$)'
    } | ForEach-Object { Remove-Item -LiteralPath ('Env:' + $_.Name) }
    foreach ($name in $savedEnvironment.Keys) {
        Set-Item -LiteralPath ('Env:' + $name) -Value $savedEnvironment[$name]
    }
}
