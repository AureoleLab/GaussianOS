[CmdletBinding()]
param(
    [string]$OutputDirectory = (Join-Path $PSScriptRoot "..\release"),
    [switch]$SkipArchive
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$stage = Join-Path $root 'build\portable-core'
$dist = Join-Path $stage 'GaussianOS'
Remove-Item -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Force -Path $stage, $OutputDirectory | Out-Null

# onedir avoids onefile's startup extraction and keeps mutable runtime local.
Push-Location $root
try {
    & uv run --with 'pyinstaller==6.17.0' pyinstaller --noconfirm --clean --onedir --name GaussianOS --windowed `
        --hidden-import PySide6.QtWebEngineCore --hidden-import PySide6.QtWebEngineQuick `
        --add-data 'apps/desktop/qml;apps/desktop/qml' `
        --add-data 'apps/desktop/viewer_web;apps/desktop/viewer_web' `
        --add-data 'configs;configs' --add-data 'workers;workers' --add-data 'packages;packages' `
        apps/desktop/__main__.py
    if ($LASTEXITCODE -ne 0) { throw 'PyInstaller failed.' }
} finally { Pop-Location }
Move-Item -LiteralPath (Join-Path $root 'dist\GaussianOS') -Destination $stage

# Do not distribute research-only workers, test code, caches, PDBs, Qt examples,
# local project state, model checkpoints, or build artefacts.
$exclude = @('recon_gluemap','recon_vggt_omega','train_improvedgs','__pycache__','tests','benchmarks','*.pdb','*.pyc','*.pyo','*.log','*.tmp','*.ply','*.scene-bundle','*.safetensors','*.pt','*.pth','*.ckpt')
foreach ($pattern in $exclude) { Get-ChildItem -LiteralPath $stage -Recurse -Force -ErrorAction SilentlyContinue -Filter $pattern | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue }
Copy-Item (Join-Path $root 'dist\runtime-manifest.json') (Join-Path $dist 'runtime-manifest.json')
Copy-Item (Join-Path $root 'LICENSE'), (Join-Path $root 'THIRD_PARTY_NOTICES.md'), (Join-Path $root 'README.md') -Destination $dist
New-Item -ItemType Directory -Force -Path (Join-Path $dist 'runtime') | Out-Null
@'
@echo off
setlocal
cd /d "%~dp0"
GaussianOS.exe --doctor
GaussianOS.exe
'@ | Set-Content -LiteralPath (Join-Path $dist 'GaussianOS.bat') -Encoding ascii

$before = (Get-ChildItem $dist -Recurse -File | Measure-Object Length -Sum).Sum
$archive = Join-Path $OutputDirectory 'GaussianOS-Portable-Core-win-x64.zip'
if (-not $SkipArchive) { Remove-Item $archive -Force -ErrorAction SilentlyContinue; Compress-Archive -Path (Join-Path $stage 'GaussianOS') -DestinationPath $archive -CompressionLevel Optimal }
$after = if (Test-Path $archive) { (Get-Item $archive).Length } else { 0 }
$manifest = [ordered]@{ archive = $archive; unpacked_bytes = $before; compressed_bytes = $after; sha256 = if ($after) { (Get-FileHash $archive -Algorithm SHA256).Hash.ToLower() } else { $null }; files = @(Get-ChildItem $dist -Recurse -File | ForEach-Object { $_.FullName.Substring($dist.Length + 1) }) }
$manifest | ConvertTo-Json -Depth 4 | Set-Content (Join-Path $OutputDirectory 'GaussianOS-Portable-Core-win-x64.manifest.json') -Encoding utf8
Write-Host "Portable Core unpacked: $before bytes; archive: $after bytes"
