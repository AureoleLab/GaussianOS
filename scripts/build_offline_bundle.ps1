[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$RuntimeSource,
    [string]$OutputDirectory = (Join-Path $PSScriptRoot "..\release")
)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
& (Join-Path $PSScriptRoot 'build_portable.ps1') -OutputDirectory $OutputDirectory -SkipArchive
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$app = Join-Path $root 'build\portable-core\GaussianOS'
$runtime = Resolve-Path $RuntimeSource
$manifest = Get-Content (Join-Path $root 'dist\runtime-manifest.json') | ConvertFrom-Json
foreach ($asset in $manifest.assets) {
    $candidate = Join-Path $runtime $asset.target
    if (-not (Test-Path $candidate)) { throw "Offline runtime is missing locked asset: $($asset.id)" }
    if ((Get-FileHash $candidate -Algorithm SHA256).Hash.ToLower() -ne $asset.sha256) { throw "Offline runtime hash mismatch: $($asset.id)" }
}
Copy-Item (Join-Path $runtime '*') (Join-Path $app 'runtime') -Recurse -Force
$bad = Get-ChildItem $app -Recurse -File -Include *.ply,*.scene-bundle,*.pt,*.pth,*.ckpt | Where-Object { $_.FullName -notmatch 'runtime\\downloads\\dinov2' }
if ($bad) { throw "Full Offline contains disallowed project/research artifacts: $($bad.FullName -join ', ')" }
New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
$sevenZip = (Get-Command 7z.exe -ErrorAction SilentlyContinue).Source
$archive = Join-Path $OutputDirectory 'GaussianOS-Full-Offline-win-x64.7z'
if ($sevenZip) { & $sevenZip a -t7z -mx=9 $archive (Join-Path $root 'build\portable-core\GaussianOS') | Out-Host } else { $archive = Join-Path $OutputDirectory 'GaussianOS-Full-Offline-win-x64.zip'; Compress-Archive -Path $app -DestinationPath $archive -CompressionLevel Optimal }
$unpacked = (Get-ChildItem $app -Recurse -File | Measure-Object Length -Sum).Sum
[ordered]@{ archive = $archive; unpacked_bytes = $unpacked; compressed_bytes = (Get-Item $archive).Length; sha256 = (Get-FileHash $archive -Algorithm SHA256).Hash.ToLower() } | ConvertTo-Json | Set-Content "$archive.manifest.json" -Encoding utf8
Write-Host "Full Offline unpacked: $unpacked bytes; archive: $((Get-Item $archive).Length) bytes"
