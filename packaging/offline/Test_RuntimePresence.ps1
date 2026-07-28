[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$CoreRoot
)
$ErrorActionPreference = 'Stop'
$core = [IO.Path]::GetFullPath($CoreRoot)
$manifestPath = Join-Path $core 'runtime-manifest.json'
if (-not (Test-Path -LiteralPath $manifestPath -PathType Leaf)) {
    exit 1
}
try {
    $manifest = Get-Content -LiteralPath $manifestPath -Raw |
        ConvertFrom-Json
    $runtime = Join-Path $core $manifest.runtime_root
    foreach ($component in @($manifest.components | Where-Object required)) {
        $componentRoot = Join-Path $runtime $component.relative_install_path
        foreach ($check in @($component.verification)) {
            $target = Join-Path $componentRoot $check.path
            if (-not (Test-Path -LiteralPath $target)) {
                exit 1
            }
            if ($check.type -eq 'file' -and
                (Get-Item -LiteralPath $target).Length -ne
                    [int64]$check.size_bytes) {
                exit 1
            }
        }
    }
    exit 0
} catch {
    exit 1
}
