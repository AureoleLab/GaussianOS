[CmdletBinding()]
param()
$process = Start-Process `
    -FilePath (Join-Path $PSScriptRoot 'Application\GaussianOS.exe') `
    -ArgumentList '--doctor' `
    -WorkingDirectory $PSScriptRoot `
    -Wait `
    -PassThru
$report = Join-Path $PSScriptRoot 'Logs\doctor-report.txt'
if (Test-Path -LiteralPath $report) {
    Get-Content -LiteralPath $report
}
exit $process.ExitCode
