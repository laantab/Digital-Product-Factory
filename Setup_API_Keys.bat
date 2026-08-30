@echo off
REM Double-click this to enter your OpenAI, Tavily, and Pexels API keys.
REM The values go straight into .env on this machine. Nothing is uploaded.
setlocal
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\setup_api_keys.ps1"
echo.
pause
