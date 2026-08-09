@echo off
setlocal EnableExtensions
cd /d "%~dp0"
title Digital Product Factory - Create Git Safety Baseline

echo ================================================================
echo  CREATE A RECOVERABLE FACTORY BASELINE
echo ================================================================
echo This works only in the folder containing app.py.
echo It does not start Flask or call any paid service.
echo.

if not exist "app.py" (
  echo ERROR: app.py was not found in:
  echo %CD%
  goto :failed
)

where git >nul 2>nul
if errorlevel 1 (
  echo ERROR: Git is not installed or is not on PATH.
  echo Install Git for Windows, then run this file again.
  goto :failed
)

if exist ".git\" (
  echo Git is already initialized. No new baseline was created.
  git status --short
  pause
  exit /b 0
)

git init
if errorlevel 1 goto :failed
git add .
if errorlevel 1 goto :failed

git diff --cached --quiet
if not errorlevel 1 (
  echo ERROR: Git found no source files to protect.
  goto :failed
)

git grep --cached -n -E "sk-[A-Za-z0-9_-]{20,}|TAVILY_API_KEY[ ]*=[ ]*[^ ]+|OPENAI_API_KEY[ ]*=[ ]*sk-" > "%TEMP%\factory_secret_scan.txt"
if not errorlevel 1 (
  echo SAFETY STOP: A possible secret was found in files staged for Git.
  type "%TEMP%\factory_secret_scan.txt"
  git reset
  goto :failed
)

set /p FACTORY_GIT_EMAIL=Enter your email for this local backup commit: 
if "%FACTORY_GIT_EMAIL%"=="" (
  echo ERROR: An email is required to create the baseline commit.
  git reset
  goto :failed
)

git config user.name "Lonnie Brown"
git config user.email "%FACTORY_GIT_EMAIL%"
git commit -m "Factory baseline before controlled repairs"
if errorlevel 1 goto :failed

echo.
echo SUCCESS: The Factory now has a recoverable Git baseline.
git status --short
pause
exit /b 0

:failed
echo.
echo No completed baseline was created. Review the message above.
pause
exit /b 1
