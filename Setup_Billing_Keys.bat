@echo off
REM Double-click this to enter your Lemon Squeezy API key and webhook secret.
REM The values go straight into .env on this machine. Nothing is uploaded.
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_billing_keys.ps1"
echo.
pause
