@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title Set the OpenAI API key (from a file)

echo.
echo  ============================================================
echo    SET THE OPENAI API KEY  -  no console pasting needed
echo  ============================================================
echo.

if not exist ".env" (
  echo  ERROR: no .env file found in %CD%
  echo.
  pause
  exit /b 1
)
if not exist ".venv\Scripts\python.exe" (
  echo  ERROR: .venv not found. Run Setup_Factory_Development.bat first.
  echo.
  pause
  exit /b 1
)

set "KEYFILE=%~dp0new_openai_key.txt"

REM --- First run: make the file, open Notepad, and stop. -----------------
if not exist "%KEYFILE%" (
  echo  Step 1 of 2
  echo.
  echo  Notepad is opening now.
  echo.
  echo    1. Paste your new OpenAI key into it  ^(Ctrl+V^)
  echo    2. Save it            ^(Ctrl+S^)
  echo    3. Close Notepad
  echo    4. Run this file again
  echo.
  break > "%KEYFILE%"
  start /wait notepad "%KEYFILE%"
  echo  ------------------------------------------------------------
  echo   When you have saved and closed Notepad, run this file again.
  echo  ------------------------------------------------------------
  echo.
  pause
  exit /b 0
)

REM --- Second run: read the key out of the file --------------------------
set "NEWKEY="
for /f "usebackq delims=" %%K in ("%KEYFILE%") do (
  if not defined NEWKEY set "NEWKEY=%%K"
)

REM strip stray spaces / quotes a paste can bring along
if defined NEWKEY set "NEWKEY=!NEWKEY: =!"
if defined NEWKEY set "NEWKEY=!NEWKEY:"=!"

if not defined NEWKEY (
  echo  The file is empty:
  echo  %KEYFILE%
  echo.
  echo  Open it, paste your key, save, then run this again.
  echo.
  start notepad "%KEYFILE%"
  pause
  exit /b 1
)

set "HEAD=!NEWKEY:~0,7!"
set "TAIL=!NEWKEY:~-4!"
echo  Found a key in the file: !HEAD!...!TAIL!
echo.

echo !NEWKEY! | findstr /b "sk-" >nul
if errorlevel 1 (
  echo  WARNING: that does not start with "sk-", which OpenAI keys normally do.
  set "CONFIRM="
  set /p "CONFIRM=  Use it anyway? Type YES to continue: "
  if /i not "!CONFIRM!"=="YES" (
    echo.
    echo  Cancelled. No changes made.
    echo.
    pause
    exit /b 1
  )
)

REM --- back up .env before writing ---------------------------------------
set "STAMP=%DATE:~-4%%DATE:~4,2%%DATE:~7,2%_%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%"
set "STAMP=%STAMP: =0%"
set "BACKUP=.env.backup_%STAMP%"
copy /y ".env" "%BACKUP%" >nul
if not exist "%BACKUP%" (
  echo  ERROR: could not create a backup. Stopping to be safe.
  echo.
  pause
  exit /b 1
)
echo  Backup saved as %BACKUP%
echo.
echo  Checking the key with OpenAI before saving it...
echo.

set "FACTORY_NEW_OPENAI_KEY=!NEWKEY!"
set "NEWKEY="
".venv\Scripts\python.exe" "scripts\set_openai_key.py"
set "RC=%ERRORLEVEL%"
set "FACTORY_NEW_OPENAI_KEY="

echo.
if not "%RC%"=="0" (
  echo  ============================================================
  echo    NOT SAVED - see the reason above
  echo  ============================================================
  echo.
  echo  Your previous key is untouched. Fix the key in:
  echo  %KEYFILE%
  echo  then run this file again.
  echo.
  pause
  exit /b 1
)

REM --- success: shred the plaintext key file ----------------------------
del /f /q "%KEYFILE%" >nul 2>nul

echo  ============================================================
echo    DONE - the key is saved and verified
echo  ============================================================
echo.
echo   The temporary key file has been deleted for you.
echo.
echo   NEXT STEPS:
echo     1. Tell Claude the key is in - it will restart the app.
echo     2. Delete this backup once happy ^(it holds the OLD key^):
echo        %CD%\%BACKUP%
echo.
pause
exit /b 0
