@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

set "OFFLINE_ROOT=%~dp0"
set "CORE_ROOT=%~1"
if not defined CORE_ROOT set "CORE_ROOT=%~dp0..\GaussianOS-Portable-Core-win-x64"
set "CORE_ROOT=%CORE_ROOT:"=%"

if exist "%CORE_ROOT%\Application\GaussianOS.exe" goto :core_found
for /d %%D in ("%OFFLINE_ROOT%..\*") do (
    if exist "%%~fD\Application\GaussianOS.exe" set "CORE_ROOT=%%~fD"
)
if exist "%CORE_ROOT%\Application\GaussianOS.exe" goto :core_found
echo ERROR: This is a Runtime-only package and does not contain GaussianOS.exe.
echo Extract GaussianOS-Portable-Core-win-x64 next to this folder, or use
echo GaussianOS-Full-Offline-win-x64 for a single-folder offline application.
echo You can also drag a Portable Core folder onto this BAT.
goto :failed

:core_found
if not exist "%CORE_ROOT%\Application\GaussianOS.exe" (
    echo ERROR: Application\GaussianOS.exe was not found in:
    echo "%CORE_ROOT%"
    goto :failed
)
if not exist "%CORE_ROOT%\Runtime_Manager.ps1" (
    echo ERROR: Runtime_Manager.ps1 was not found in:
    echo "%CORE_ROOT%"
    goto :failed
)

echo Importing and verifying Offline Runtime into:
echo "%CORE_ROOT%\Runtime"
echo This can take several minutes. Projects and exports are not modified.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%CORE_ROOT%\Runtime_Manager.ps1" -Import "%OFFLINE_ROOT%"
set "IMPORT_EXIT=%ERRORLEVEL%"

if "%IMPORT_EXIT%"=="0" goto :installed
if "%IMPORT_EXIT%"=="4" (
    echo WARNING: Runtime import succeeded, but no compatible NVIDIA GPU was detected.
    goto :installed
)
echo ERROR: Runtime import or verification failed with exit code %IMPORT_EXIT%.
echo See "%CORE_ROOT%\Logs\runtime-operation-report.txt".
goto :failed

:installed
echo Offline Runtime import and verification completed.
if not "%GAUSSIANOS_RUNTIME_NO_PAUSE%"=="1" pause
exit /b 0

:failed
if not "%GAUSSIANOS_RUNTIME_NO_PAUSE%"=="1" pause
exit /b 1
