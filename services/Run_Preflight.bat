@echo off
setlocal
title Factory Preflight Check
color 0B

cd /d "%~dp0"

echo.
echo  ============================================================
echo    Running the Factory release gate
echo    This may take several minutes. Please wait.
echo  ============================================================
echo.

REM ---- Find a usable Python ----------------------------------------
set "PY="

REM Prefer the project's own virtual environment if there is one
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
if not defined PY if exist "%~dp0venv\Scripts\python.exe" set "PY=%~dp0venv\Scripts\python.exe"

REM Otherwise fall back to whatever Python is installed
if not defined PY (
  where py >nul 2>&1 && set "PY=py"
)
if not defined PY (
  where python >nul 2>&1 && set "PY=python"
)

if not defined PY (
  echo  ------------------------------------------------------------
  echo   COULD NOT FIND PYTHON on this computer.
  echo   Tell Claude this happened.
  echo  ------------------------------------------------------------
  echo.
  pause
  exit /b 1
)

echo  Using Python: %PY%
echo.

REM ---- Sanity check that we are in the right folder -----------------
if not exist "%~dp0preflight_check.py" (
  echo  ------------------------------------------------------------
  echo   preflight_check.py was NOT found in this folder.
  echo.
  echo   This file needs to sit in the same folder as
  echo   preflight_check.py -- the flask_app folder.
  echo   Tell Claude this happened.
  echo  ------------------------------------------------------------
  echo.
  pause
  exit /b 1
)

REM ---- Run it, saving output to a log file --------------------------
set "LOG=%~dp0preflight_results.txt"
if exist "%LOG%" del /q "%LOG%"

echo  Starting tests...
echo.

%PY% "%~dp0preflight_check.py" > "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"

REM ---- Show the results --------------------------------------------
echo.
echo  ============================================================
echo    RESULTS
echo  ============================================================
echo.

REM Show the last part of the log, where the summary lives
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "Get-Content -Path '%LOG%' -Tail 40" 2>nul

echo.
echo  ============================================================
if "%RC%"=="0" (
  echo    PASSED  -  the gate is green.
) else (
  echo    FAILED  -  exit code %RC%
  echo    Something did not pass. The full log is saved at:
  echo    %LOG%
)
echo  ============================================================
echo.
echo  Full results saved to: preflight_results.txt
echo  Send that file to Claude if you want it explained.
echo.

pause
