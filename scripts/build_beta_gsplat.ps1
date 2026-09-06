[CmdletBinding()]
param(
    [Parameter(Mandatory)][string]$VcVars,
    [Parameter(Mandatory)][string]$CudaRoot,
    [string]$Python = (Join-Path $PSScriptRoot '..\.gaussian-factory\envs\gsplat-1.5.3\Scripts\python.exe'),
    [string]$Source = (Join-Path $PSScriptRoot '..\.gaussian-factory\sources\gsplat-v1.5.3'),
    [string]$Output = (Join-Path $PSScriptRoot '..\build\public-beta\gsplat')
)
$ErrorActionPreference = 'Stop'
$resolvedVcVars = (Resolve-Path -LiteralPath $VcVars).Path
$resolvedCuda = (Resolve-Path -LiteralPath $CudaRoot).Path
$resolvedPython = (Resolve-Path -LiteralPath $Python).Path
$resolvedSource = (Resolve-Path -LiteralPath $Source).Path
$resolvedOutput = [IO.Path]::GetFullPath($Output)
if (Test-Path -LiteralPath (Join-Path $resolvedOutput 'lib\gsplat\csrc.pyd')) {
    throw 'A compiled extension already exists. Use a new output directory to retain its provenance.'
}
foreach ($value in @($resolvedVcVars, $resolvedCuda, $resolvedPython, $resolvedSource, $resolvedOutput)) {
    if ($value -match '["%\r\n]') { throw 'Build paths contain unsupported command-script characters.' }
}
New-Item -ItemType Directory -Path $resolvedOutput -Force | Out-Null
$batch = Join-Path $resolvedOutput 'compile.cmd'
$lines = @(
    '@echo off',
    ('call "{0}"' -f $resolvedVcVars),
    'if errorlevel 1 exit /b %errorlevel%',
    ('set "CUDA_HOME={0}"' -f $resolvedCuda),
    ('set "CUDA_PATH={0}"' -f $resolvedCuda),
    'set "PATH=%CUDA_HOME%\bin;%PATH%"',
    'set "TORCH_CUDA_ARCH_LIST=7.5;8.0;8.6;8.9;9.0;10.0;12.0+PTX"',
    'set "MAX_JOBS=4"', 'set "DISTUTILS_USE_SDK=1"', 'set "MSSdk=1"',
    ('"{0}" -B setup.py build_ext --build-lib "{1}\lib" --build-temp "{1}\temp"' -f $resolvedPython, $resolvedOutput),
    'exit /b %errorlevel%'
)
$lines | Set-Content -LiteralPath $batch -Encoding ascii
Push-Location $resolvedSource
try {
    & $batch *> (Join-Path $resolvedOutput 'build.log')
    if ($LASTEXITCODE -ne 0) { throw 'gsplat extension build failed; inspect build.log.' }
} finally { Pop-Location }
$extension = Join-Path $resolvedOutput 'lib\gsplat\csrc.pyd'
[ordered]@{
    sha256 = (Get-FileHash -LiteralPath $extension -Algorithm SHA256).Hash.ToLower()
    size_bytes = (Get-Item -LiteralPath $extension).Length
    architectures = '7.5;8.0;8.6;8.9;9.0;10.0;12.0+PTX'
    cuda_root = $resolvedCuda
    source = $resolvedSource
    python = $resolvedPython
} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $resolvedOutput 'extension-provenance.json') -Encoding utf8
