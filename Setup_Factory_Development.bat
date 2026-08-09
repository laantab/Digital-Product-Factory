@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Digital Product Factory - One-Time Test Setup

echo ================================================================
echo  DIGITAL PRODUCT FACTORY - ONE-TIME TEST SETUP
echo ================================================================
echo This installs the exact local test dependencies into .venv.
echo It does not start Flask or call OpenAI, Tavily, or image generation.
echo.

where python >nul 2>nul
if errorlevel 1 (
  echo ERROR: Python is not available on PATH.
  goto :failed
)

if not exist ".venv\Scripts\python.exe" (
  python -m venv .venv
  if errorlevel 1 goto :failed
)

call ".venv\Scripts\activate.bat"
python -m pip install --upgrade pip
if errorlevel 1 goto :failed
python -m pip install -r requirements-dev.txt
if errorlevel 1 goto :failed

echo.
echo Dependencies installed. Running the enforced release gate now.
python preflight_check.py
if errorlevel 1 goto :failed

echo.
echo SUCCESS: Setup completed and the release gate passed.
pause
exit /b 0

:failed
echo.
echo STOP: Setup or preflight failed. Read the error above.
pause
exit /b 1
