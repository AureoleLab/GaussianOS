[CmdletBinding()]
param([Parameter(Mandatory)][string]$Archive)
$ErrorActionPreference = 'Stop'
$scratch = Join-Path ([IO.Path]::GetTempPath()) ("GaussianOS-portable-" + [guid]::NewGuid())
Expand-Archive -LiteralPath $Archive -DestinationPath $scratch
$app = Get-ChildItem $scratch -Directory | Select-Object -First 1
if (-not (Test-Path (Join-Path $app.FullName 'GaussianOS.exe'))) { throw 'Portable archive does not contain GaussianOS.exe.' }
if (-not (Test-Path (Join-Path $app.FullName 'runtime-manifest.json'))) { throw 'Portable archive does not contain runtime-manifest.json.' }
$forbidden = Get-ChildItem $app.FullName -Recurse -File -Include *.ply,*.scene-bundle,*.pt,*.pth,*.ckpt,*.safetensors
if ($forbidden) { throw "Core archive contains project data or model weights: $($forbidden.FullName -join ', ')" }
& (Join-Path $app.FullName 'GaussianOS.exe') --doctor
if ($LASTEXITCODE -ne 0 -and $LASTEXITCODE -ne 2) { throw 'Portable executable failed its clean-directory doctor smoke check.' }
Remove-Item $scratch -Recurse -Force
Write-Host 'Portable archive verification passed.'
