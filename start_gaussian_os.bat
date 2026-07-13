@echo off
setlocal

cd /d "%~dp0"
title GaussianOS Launcher

where uv >nul 2>nul
if errorlevel 1 (
    echo [GaussianOS] uv was not found in PATH.
    echo Install uv from https://docs.astral.sh/uv/ and run this launcher again.
    pause
    exit /b 1
)

echo [GaussianOS] Starting desktop application...
uv run --extra desktop gaussian-factory-gui
set "exit_code=%errorlevel%"

if not "%exit_code%"=="0" (
    echo.
    echo [GaussianOS] Startup failed with exit code %exit_code%.
    pause
)

exit /b %exit_code%
