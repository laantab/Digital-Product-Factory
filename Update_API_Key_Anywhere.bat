@echo off
setlocal enabledelayedexpansion
title Update OpenAI API Key
color 0B

echo.
echo  ============================================================
echo    Update the OpenAI API key
echo  ============================================================
echo.

REM ================================================================
REM  1. Find the .env file automatically
REM ================================================================
set "ENVFILE="

REM -- Is it right next to this batch file?
if exist "%~dp0.env" set "ENVFILE=%~dp0.env"

REM -- Try the known Factory location
if not defined ENVFILE (
  set "TRY=%USERPROFILE%\OneDrive\Desktop\Factory_Stabilized_Source_V2_20260809\Factory_Stabilized_V2\flask_app\.env"
  if exist "!TRY!" set "ENVFILE=!TRY!"
)

REM -- Search the OneDrive Desktop for any flask_app folder
if not defined ENVFILE (
  echo  Searching for your Factory folder, please wait...
  for /f "delims=" %%D in ('dir /s /b /ad "%USERPROFILE%\OneDrive\Desktop\flask_app" 2^>nul') do (
    if not defined ENVFILE if exist "%%D\.env" set "ENVFILE=%%D\.env"
  )
)

REM -- Last resort: search the whole user folder
if not defined ENVFILE (
  echo  Still searching, this may take a minute...
  for /f "delims=" %%D in ('dir /s /b /ad "%USERPROFILE%\flask_app" 2^>nul') do (
    if not defined ENVFILE if exist "%%D\.env" set "ENVFILE=%%D\.env"
  )
)

if not defined ENVFILE (
  echo.
  echo  ------------------------------------------------------------
  echo   COULD NOT FIND your .env file anywhere.
  echo   Tell Claude this happened.
  echo  ------------------------------------------------------------
  echo.
  pause
  exit /b 1
)

echo  Found your settings file:
echo  %ENVFILE%
echo.

REM ================================================================
REM  2. Show the current key, masked
REM ================================================================
set "EF=%ENVFILE%"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$line = Select-String -Path $env:EF -Pattern '^\s*OPENAI_API_KEY\s*=' | Select-Object -First 1;" ^
  "if ($line) { $v = ($line.Line -split '=',2)[1].Trim().Trim([char]39).Trim([char]34);" ^
  "  if ($v.Length -gt 11) { Write-Host ('  Current key: ' + $v.Substring(0,7) + '...' + $v.Substring($v.Length-4)) }" ^
  "  else { Write-Host '  Current key: (present but very short)' } }" ^
  "else { Write-Host '  No key line found yet - one will be added.' }"

echo.
echo  ------------------------------------------------------------
echo   Go to platform.openai.com
echo   Delete the OLD key. Create a NEW one. Copy it.
echo   Then paste it below.
echo.
echo   To paste: RIGHT-CLICK in this window, then press Enter.
echo  ------------------------------------------------------------
echo.

REM ================================================================
REM  3. Ask for the new key
REM ================================================================
set "NEWKEY="
set /p "NEWKEY=  Paste the new key here: "

if not defined NEWKEY (
  echo.
  echo   Nothing entered. No changes made.
  echo.
  pause
  exit /b 1
)

REM -- Warn if it looks wrong, but let them override
echo !NEWKEY! | findstr /b "sk-" >nul
if errorlevel 1 (
  echo.
  echo   WARNING: that does not start with "sk-".
  echo   OpenAI keys normally do.
  echo.
  set "CONFIRM="
  set /p "CONFIRM=  Use it anyway? Type YES to continue: "
  if /i not "!CONFIRM!"=="YES" (
    echo.
    echo   Cancelled. No changes made.
    echo.
    pause
    exit /b 1
  )
)

REM ================================================================
REM  4. Back up the old file first
REM ================================================================
set "STAMP=%DATE:~-4%%DATE:~4,2%%DATE:~7,2%_%TIME:~0,2%%TIME:~3,2%%TIME:~6,2%"
set "STAMP=%STAMP: =0%"
set "BACKUP=%ENVFILE%.backup_%STAMP%"

copy /y "%ENVFILE%" "%BACKUP%" >nul
if not exist "%BACKUP%" (
  echo.
  echo   ERROR: could not create a backup. Stopping to be safe.
  echo.
  pause
  exit /b 1
)

echo.
echo   Backup saved.
echo.

REM ================================================================
REM  5. Swap the key in
REM ================================================================
set "NEWKEY_FOR_PS=!NEWKEY!"

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$p = $env:EF;" ^
  "$k = $env:NEWKEY_FOR_PS;" ^
  "$lines = Get-Content -Path $p;" ^
  "$found = $false;" ^
  "$out = foreach ($l in $lines) {" ^
  "  if ($l -match '^\s*OPENAI_API_KEY\s*=') { $found = $true; 'OPENAI_API_KEY=' + $k } else { $l } };" ^
  "if (-not $found) { $out = @($out) + ('OPENAI_API_KEY=' + $k) };" ^
  "Set-Content -Path $p -Value $out -Encoding UTF8"

set "RC=%ERRORLEVEL%"
set "NEWKEY_FOR_PS="
set "NEWKEY="

if not "%RC%"=="0" (
  echo.
  echo   ERROR: the update failed. Your backup is safe at:
  echo   %BACKUP%
  echo.
  pause
  exit /b 1
)

REM ================================================================
REM  6. Confirm what is now in the file
REM ================================================================
echo  ============================================================
echo    DONE
echo  ============================================================
echo.

powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$line = Select-String -Path $env:EF -Pattern '^\s*OPENAI_API_KEY\s*=' | Select-Object -First 1;" ^
  "if ($line) { $v = ($line.Line -split '=',2)[1].Trim();" ^
  "  if ($v.Length -gt 11) { Write-Host ('  New key now set: ' + $v.Substring(0,7) + '...' + $v.Substring($v.Length-4)) } }"

echo.
echo   NEXT STEPS:
echo     1. Restart the Factory app.
echo     2. Run Run_Factory_Preflight.bat - expect 885 passed.
echo     3. Then delete the backup file, which still has the
echo        OLD key in it:
echo        %BACKUP%
echo.
echo   Nothing here goes to GitHub - .env is not tracked by git.
echo.

pause
