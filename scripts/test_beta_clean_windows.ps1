# Run on a fresh GitHub-hosted Windows runner against the exact draft assets.
# No GPU reconstruction is claimed here; the local GPU acceptance is separate.
$ErrorActionPreference = 'Stop'
$root = Join-Path $env:RUNNER_TEMP 'GaussianOS-Clean-Acceptance'
if (Test-Path -LiteralPath $root) { throw 'Clean acceptance directory already exists.' }
$evidence = Join-Path $root 'evidence'
$downloads = Join-Path $root 'downloads'
$installed = Join-Path $root '中文 Beta with spaces'
New-Item -ItemType Directory -Path $evidence,$downloads,$installed | Out-Null
if ($env:BETA_CORE_SHA256 -notmatch '^[a-f0-9]{64}$') { throw 'Expected Core SHA-256 is invalid.' }
& gh release download $env:BETA_TAG --repo $env:GITHUB_REPOSITORY --pattern 'GaussianOS-Core-win-x64.zip' --dir $downloads
if ($LASTEXITCODE -ne 0) { throw 'Core release asset download failed.' }
$core = Join-Path $downloads 'GaussianOS-Core-win-x64.zip'
$coreHash = (Get-FileHash -LiteralPath $core -Algorithm SHA256).Hash.ToLower()
if ($coreHash -ne $env:BETA_CORE_SHA256) { throw 'Core release asset SHA-256 mismatch.' }
Expand-Archive -LiteralPath $core -DestinationPath $installed
$manifest = Get-Content -LiteralPath (Join-Path $installed 'runtime-manifest.json') -Raw | ConvertFrom-Json
$cache = Join-Path $installed 'Cache\RuntimeDownloads'
New-Item -ItemType Directory -Path $cache -Force | Out-Null
# Test both independent CPython ABIs; omit large inference models on this CPU
# runner, while retaining the full base runtime and its required LPIPS weights.
$components = @($manifest.components | Where-Object { $_.required -or $_.component_id -in @('mapanything-source','mapanything-environment','dinov2-source') })
foreach ($component in $components) {
    foreach ($part in $component.source.artifact.parts) {
        & gh release download $env:BETA_TAG --repo $env:GITHUB_REPOSITORY --pattern $part.filename --dir $cache
        if ($LASTEXITCODE -ne 0) { throw "Runtime release download failed: $($part.filename)" }
    }
}
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
foreach ($component in $components) {
    $p = Start-Process -FilePath $exe -ArgumentList @('--runtime-install',$component.component_id) -WorkingDirectory $profileRoot -WindowStyle Hidden -PassThru -Wait
    if ($p.ExitCode -notin @(0,2,4)) { throw "Runtime installer failed: $($component.component_id): $($p.ExitCode)" }
}
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
    } finally { Pop-Location }
}
foreach ($ui in @('modern','classic')) {
    $png = Join-Path $evidence "$ui.png"
    $arguments = @('--ui',$ui,'--acceptance-evidence',('"' + $png + '"'),'--acceptance-delay-ms','15000')
    $p = Start-Process -FilePath $exe -ArgumentList $arguments -WorkingDirectory $profileRoot -WindowStyle Hidden -PassThru
    if (-not $p.WaitForExit(90000)) { $p.Kill(); throw "$ui UI acceptance timed out." }
    if ($p.ExitCode -ne 0 -or -not (Test-Path -LiteralPath $png)) { throw "$ui UI acceptance failed." }
}
Copy-Item -LiteralPath (Join-Path $installed 'Logs\desktop-ui.log') -Destination $evidence
[ordered]@{ status='succeeded'; core_sha256=$coreHash; runner_os=[Environment]::OSVersion.VersionString;
    worker_probes=$probes; scope='Fresh Windows runner, exact draft artifacts, empty profile, isolated PATH. No GPU pipeline claimed.' } |
    ConvertTo-Json -Depth 8 | Set-Content -LiteralPath (Join-Path $evidence 'report.json') -Encoding utf8
