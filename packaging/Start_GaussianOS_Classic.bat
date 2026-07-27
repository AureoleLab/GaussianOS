@echo off
setlocal
cd /d "%~dp0"
"%~dp0Application\GaussianOS.exe" --ui classic %*
