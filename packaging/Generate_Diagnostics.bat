@echo off
setlocal
"%~dp0Application\GaussianOS.exe" --diagnostic-zip
set "GAUSSIANOS_DIAGNOSTIC_EXIT=%ERRORLEVEL%"
echo.
if "%GAUSSIANOS_DIAGNOSTIC_EXIT%"=="0" (
  echo Diagnostic ZIP created in: %~dp0Logs
) else (
  echo Diagnostic generation failed. See: %~dp0Logs\diagnostic-error.txt
)
pause
exit /b %GAUSSIANOS_DIAGNOSTIC_EXIT%
