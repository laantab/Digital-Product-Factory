@echo off
setlocal EnableDelayedExpansion
cd /d "%~dp0"
title Set the OpenAI API key

echo.
echo  ============================================================
echo    SET THE OPENAI API KEY
echo  ============================================================
echo.
echo  Nothing here is uploaded. .env stays on this computer and is
echo  not tracked by git.
echo.

if not exist ".env" (
  echo  ERROR: no .env file found in:
  echo  %CD%
  echo.
  echo  Nothing was changed.
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

REM --- show what is set right now, masked --------------------------------
for /f "usebackq tokens=1,* delims==" %%A in (`findstr /b "OPENAI_API_KEY=" ".env"`) do (
  set "CUR=%%B"
)
if defined CUR (
  set "HEAD=!CUR:~0,7!"
  set "TAIL=!CUR:~-4!"
  echo  Current key: !HEAD!...!TAIL!
) else (
  echo  Current key: none set yet.
)

echo.
echo  ------------------------------------------------------------
echo   Get a key at platform.openai.com  ^-^>  API keys
echo   ^-^>  Create new secret key  ^-^>  Copy
echo.
echo   To paste below: RIGHT-CLICK in this window, then press Enter.
echo  ------------------------------------------------------------
echo.

set "NEWKEY="
set /p "NEWKEY=  Paste the new key here: "

if not defined NEWKEY (
  echo.
  echo  Nothing entered. No changes made.
  echo.
  pause
  exit /b 1
)

REM --- sanity check the shape before touching anything --------------------
echo !NEWKEY! | findstr /b "sk-" >nul
if errorlevel 1 (
  echo.
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
  echo.
  echo  ERROR: could not create a backup. Stopping to be safe.
  echo.
  pause
  exit /b 1
)
echo.
echo  Backup saved as %BACKUP%
echo.
echo  Checking the key with OpenAI before saving it...
echo.

REM --- hand off to Python: verify, then write both key names -------------
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
  echo  Your previous key is untouched. The backup is at:
  echo  %CD%\%BACKUP%
  echo.
  pause
  exit /b 1
)

echo  ============================================================
echo    DONE - the key is saved and verified
echo  ============================================================
echo.
echo   NEXT STEPS:
echo     1. Restart the Factory app so it reads the new key,
echo        or tell Claude the key is in and it will restart it.
echo     2. Delete the backup below once you are happy - it still
echo        contains the OLD key:
echo        %CD%\%BACKUP%
echo.
pause
exit /b 0
