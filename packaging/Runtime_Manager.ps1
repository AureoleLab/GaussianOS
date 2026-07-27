[CmdletBinding(DefaultParameterSetName = 'List')]
param(
    [Parameter(ParameterSetName = 'List')][switch]$List,
    [Parameter(ParameterSetName = 'Install', Mandatory)][string[]]$Install,
    [Parameter(ParameterSetName = 'InstallAll', Mandatory)][switch]$InstallAll,
    [Parameter(ParameterSetName = 'Import', Mandatory)][string]$Import,
    [Parameter(ParameterSetName = 'Verify', Mandatory)][switch]$Verify,
    [Parameter(ParameterSetName = 'Repair', Mandatory)][string[]]$Repair,
    [Parameter(ParameterSetName = 'Repair')][string]$Source
)
$arguments = [System.Collections.Generic.List[string]]::new()
function Quote-ProcessArgument([string]$Value) {
    return '"' + $Value.Replace('"', '\"') + '"'
}
switch ($PSCmdlet.ParameterSetName) {
    'List' { $arguments.Add('--runtime-list') }
    'Install' {
        foreach ($component in $Install) {
            $arguments.Add('--runtime-install')
            $arguments.Add($component)
        }
    }
    'InstallAll' { $arguments.Add('--runtime-install-all') }
    'Import' {
        $arguments.Add('--runtime-import')
        $arguments.Add((Quote-ProcessArgument $Import))
    }
    'Verify' { $arguments.Add('--runtime-verify-full') }
    'Repair' {
        foreach ($component in $Repair) {
            $arguments.Add('--runtime-repair')
            $arguments.Add($component)
        }
        if ($Source) {
            $arguments.Add('--runtime-repair-source')
            $arguments.Add((Quote-ProcessArgument $Source))
        }
    }
}
$process = Start-Process `
    -FilePath (Join-Path $PSScriptRoot 'Application\GaussianOS.exe') `
    -ArgumentList $arguments `
    -WorkingDirectory $PSScriptRoot `
    -Wait `
    -PassThru
$report = Join-Path $PSScriptRoot 'Logs\runtime-operation-report.txt'
if (Test-Path -LiteralPath $report) {
    Get-Content -LiteralPath $report
}
exit $process.ExitCode
