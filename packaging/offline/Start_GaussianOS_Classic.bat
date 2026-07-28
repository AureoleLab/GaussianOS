@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

set "OFFLINE_ROOT=%~dp0"
set "CORE_ROOT=%~1"
if not defined CORE_ROOT set "CORE_ROOT=%~dp0..\GaussianOS-Portable-Core-win-x64"
set "CORE_ROOT=%CORE_ROOT:"=%"

if exist "%CORE_ROOT%\Application\GaussianOS.exe" goto :core_found
echo GaussianOS Portable Core was not found next to this Offline Runtime.
echo Drag the Portable Core folder onto this BAT, or enter its full path.
set /p "CORE_ROOT=Portable Core folder: "
set "CORE_ROOT=%CORE_ROOT:"=%"

:core_found
if not exist "%CORE_ROOT%\Application\GaussianOS.exe" (
    echo ERROR: Application\GaussianOS.exe was not found in:
    echo "%CORE_ROOT%"
    pause
    exit /b 1
)

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%OFFLINE_ROOT%\Test_RuntimePresence.ps1" -CoreRoot "%CORE_ROOT%"
if errorlevel 1 goto :install
goto :launch

:install
set "GAUSSIANOS_RUNTIME_NO_PAUSE=1"
call "%OFFLINE_ROOT%\Install_Runtime.bat" "%CORE_ROOT%"
set "INSTALL_EXIT=%ERRORLEVEL%"
set "GAUSSIANOS_RUNTIME_NO_PAUSE="
if not "%INSTALL_EXIT%"=="0" (
    echo GaussianOS was not started because Runtime installation failed.
    pause
    exit /b %INSTALL_EXIT%
)

:launch
call "%CORE_ROOT%\Start_GaussianOS_Classic.bat"
exit /b %ERRORLEVEL%
