param(
    [ValidateSet("light", "dark")]
    [string]$Theme = "light",
    [ValidateSet("workspace", "library")]
    [string]$Page = "workspace",
    [ValidateSet("compact", "standard", "comfortable")]
    [string]$Density = "standard",
    [ValidateSet("light", "balanced", "strong")]
    [string]$Weight = "balanced",
    [int]$Width = 1600,
    [int]$Height = 900,
    [double]$Scale = 0
)

$ErrorActionPreference = "Stop"
$prototypeRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$arguments = @(
    "run", "--extra", "desktop", "python",
    (Join-Path $prototypeRoot "prototype.py"),
    "--theme", $Theme,
    "--page", $Page,
    "--density", $Density,
    "--weight", $Weight,
    "--width", $Width,
    "--height", $Height
)
if ($Scale -gt 0) {
    $arguments += @("--scale", $Scale)
}
& uv @arguments
