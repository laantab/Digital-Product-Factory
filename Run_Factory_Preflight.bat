@echo off
setlocal
cd /d "%~dp0"
title Digital Product Factory - Release Gate

echo ================================================================
echo  DIGITAL PRODUCT FACTORY - ENFORCED RELEASE GATE
echo ================================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python is not available on PATH.
  goto :failed
)

python preflight_check.py
if errorlevel 1 goto :failed

echo.
echo SUCCESS: The full release gate passed.
pause
exit /b 0

:failed
echo.
echo STOP: Preflight failed. Do not release or accept code changes.
echo Read the error above, fix it, and run this file again.
pause
exit /b 1
