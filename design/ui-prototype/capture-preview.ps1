param(
    [ValidateSet("light", "dark")]
    [string]$Theme = "light",
    [double]$Scale = 1.25
)

$ErrorActionPreference = "Stop"
$prototypeRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$output = Join-Path $prototypeRoot "screenshots\gaussianos-light-1600x900-125.png"
if ($Theme -eq "dark") {
    $output = Join-Path $prototypeRoot "screenshots\gaussianos-dark-1600x900-125.png"
}
& uv run --extra desktop python (Join-Path $prototypeRoot "prototype.py") `
    --theme $Theme --page library --width 1600 --height 900 --scale $Scale --screenshot $output
