[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$Archive,
    [switch]$KeepScratch
)
$ErrorActionPreference = 'Stop'
$archivePath = (Resolve-Path $Archive).Path
$verifyWord = -join @([char]0x9A8C, [char]0x8BC1)
$firstLaunch = -join @([char]0x9996, [char]0x6B21, [char]0x542F, [char]0x52A8)
$movedLabel = -join @([char]0x79FB, [char]0x52A8, [char]0x540E, [char]0x7684)
$longPathLabel = -join @([char]0x957F, [char]0x8DEF, [char]0x5F84)
$scratch = Join-Path ([IO.Path]::GetTempPath()) (
    "GaussianOS $verifyWord with spaces " + [guid]::NewGuid()
)
$extract = Join-Path $scratch $firstLaunch
$movedRoot = Join-Path $scratch (
    "$movedLabel Portable Core " + (($longPathLabel + '-') * 8)
)
New-Item -ItemType Directory -Force -Path $extract | Out-Null
try {
    Expand-Archive -LiteralPath $archivePath -DestinationPath $extract
    $package = Get-ChildItem -LiteralPath $extract -Directory |
        Where-Object Name -eq 'GaussianOS-Portable-Core-win-x64' |
        Select-Object -First 1
    if (-not $package) {
        throw 'Portable archive root is missing.'
    }
    $root = $package.FullName
    $exe = Join-Path $root 'Application\GaussianOS.exe'
    if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
        throw 'Portable archive does not contain Application\GaussianOS.exe.'
    }
    foreach ($required in @(
        'runtime-manifest.json',
        'build-manifest.json',
        'VERSION',
        'QUICKSTART.md',
        'TROUBLESHOOTING.md',
        'Start_GaussianOS.bat',
        'Start_GaussianOS_Classic.bat',
        'Doctor.ps1',
        'Runtime_Manager.ps1'
    )) {
        if (-not (Test-Path -LiteralPath (Join-Path $root $required) -PathType Leaf)) {
            throw "Portable archive is missing $required."
        }
    }
    $forbidden = Get-ChildItem -LiteralPath $root -Recurse -File |
        Where-Object Extension -in @(
            '.ply', '.pt', '.pth', '.ckpt', '.safetensors', '.mp4', '.mov', '.avi'
        )
    if ($forbidden) {
        throw "Core contains model/project/media payload: $($forbidden.FullName -join ', ')"
    }
    if (Test-Path -LiteralPath (Join-Path $root 'Runtime\Runtime')) {
        throw 'Core contains forbidden Runtime\Runtime nesting.'
    }

    $doctor = Start-Process `
        -FilePath $exe `
        -ArgumentList '--doctor' `
        -WorkingDirectory $root `
        -Wait `
        -PassThru
    if ($doctor.ExitCode -ne 2) {
        throw "Core-only doctor must return 2, got $($doctor.ExitCode)."
    }
    $doctorJson = Join-Path $root 'Logs\doctor-report.json'
    $report = Get-Content -LiteralPath $doctorJson -Raw | ConvertFrom-Json
    if ($report.core_status -ne 'ok' -or $report.runtime_status -ne 'not_installed') {
        throw "Core-only doctor classification is wrong: $($report | ConvertTo-Json -Compress)"
    }

    foreach ($ui in 'modern', 'classic') {
        $evidence = Join-Path $root "Logs\$ui-clean-smoke.png"
        $argumentLine = (
            '--ui {0} --acceptance-evidence "{1}" --acceptance-delay-ms 5000' -f `
                $ui, $evidence.Replace('"', '\"')
        )
        $process = Start-Process `
            -FilePath $exe `
            -ArgumentList $argumentLine `
            -WorkingDirectory $root `
            -Wait `
            -PassThru
        if ($process.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $evidence)) {
            throw "$ui packaged GUI/WebEngine smoke failed ($($process.ExitCode))."
        }
    }

    $projectSentinel = Join-Path $root 'Projects\keep-project\project.json'
    $runtimeSentinel = Join-Path $root 'Runtime\keep-runtime.txt'
    $exportSentinel = Join-Path $root 'Exports\keep-export.txt'
    New-Item -ItemType Directory -Force -Path (Split-Path $projectSentinel) | Out-Null
    Set-Content -LiteralPath $projectSentinel -Value '{"project_id":"preserve"}' -Encoding utf8
    Set-Content -LiteralPath $runtimeSentinel -Value 'preserve' -Encoding utf8
    Set-Content -LiteralPath $exportSentinel -Value 'preserve' -Encoding utf8

    Move-Item -LiteralPath $root -Destination $movedRoot
    $root = $movedRoot
    $exe = Join-Path $root 'Application\GaussianOS.exe'
    $movedDoctor = Start-Process `
        -FilePath $exe `
        -ArgumentList '--doctor' `
        -WorkingDirectory $root `
        -Wait `
        -PassThru
    if ($movedDoctor.ExitCode -ne 2) {
        throw "Moved Core doctor failed ($($movedDoctor.ExitCode))."
    }
    foreach ($sentinel in @(
        'Projects\keep-project\project.json',
        'Runtime\keep-runtime.txt',
        'Exports\keep-export.txt'
    )) {
        if (-not (Test-Path -LiteralPath (Join-Path $root $sentinel))) {
            throw "Moving Core lost $sentinel."
        }
    }

    $applicationBackup = Join-Path $scratch 'removed-Application'
    Move-Item -LiteralPath (Join-Path $root 'Application') -Destination $applicationBackup
    if (-not (Test-Path -LiteralPath (Join-Path $root 'Projects\keep-project\project.json'))) {
        throw 'Removing Application removed project data.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $root 'Runtime\keep-runtime.txt'))) {
        throw 'Removing Application removed Runtime data.'
    }
    if (-not (Test-Path -LiteralPath (Join-Path $root 'Exports\keep-export.txt'))) {
        throw 'Removing Application removed export data.'
    }
    Write-Host 'Portable Core clean-directory, GUI, relocation, update-isolation, and deletion-isolation verification passed.'
} finally {
    if ($KeepScratch) {
        Write-Host "Verification scratch retained: $scratch"
    } elseif (Test-Path -LiteralPath $scratch) {
        $resolvedScratch = [IO.Path]::GetFullPath($scratch)
        $resolvedTemp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
        if (-not $resolvedScratch.StartsWith($resolvedTemp, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Refusing to remove unexpected verification path: $resolvedScratch"
        }
        Remove-Item -LiteralPath $scratch -Recurse -Force
    }
}
