@echo off
setlocal
cd /d "%~dp0"
title Digital Product Factory Pro - Book Studio
if not exist "services\ebook_v2\cli.py" goto failed
set "STUDIO_DATA=%LOCALAPPDATA%\DigitalProductFactoryPro\BookStudio"
set "FACTORY_TEST_MODE="
set "FACTORY_ACCESS_MODE=private"
if not exist ".ebook-v2-venv\Scripts\python.exe" (
  py -3 -m venv .ebook-v2-venv
  if errorlevel 1 goto failed
)
if not exist ".ebook-v2-venv\stock-visuals-1.ready" (
  ".ebook-v2-venv\Scripts\python.exe" -m pip install -r requirements-ebook-v2.txt
  if errorlevel 1 goto failed
  echo ready>".ebook-v2-venv\stock-visuals-1.ready"
)
".ebook-v2-venv\Scripts\python.exe" -m services.ebook_v2.cli init --data "%STUDIO_DATA%"
if errorlevel 1 goto failed
powershell -NoProfile -Command "try{$h=Invoke-RestMethod 'http://127.0.0.1:5088/health' -TimeoutSec 2;if($h.service -eq 'factory-book-studio'){if($h.worker_online){exit 0}else{exit 2}}}catch{};exit 1"
if errorlevel 2 (
  start "Book Studio Worker" ".ebook-v2-venv\Scripts\python.exe" -m services.ebook_v2.cli worker --data "%STUDIO_DATA%"
  start "" "http://127.0.0.1:5088"
  exit /b 0
)
if not errorlevel 1 (
  start "" "http://127.0.0.1:5088"
  exit /b 0
)
where ollama >nul 2>nul
if not errorlevel 1 (
  powershell -NoProfile -Command "try{Invoke-RestMethod 'http://127.0.0.1:11434/api/tags' -TimeoutSec 2 ^| Out-Null;exit 0}catch{exit 1}"
  if errorlevel 1 start "Local Writing Service" ollama serve
)
start "Book Studio Worker" ".ebook-v2-venv\Scripts\python.exe" -m services.ebook_v2.cli worker --data "%STUDIO_DATA%"
start "Book Studio Server" ".ebook-v2-venv\Scripts\python.exe" -m services.ebook_v2.cli serve --data "%STUDIO_DATA%"
powershell -NoProfile -Command "for($i=0;$i -lt 40;$i++){try{$h=Invoke-RestMethod 'http://127.0.0.1:5088/health' -TimeoutSec 1;if($h.service -eq 'factory-book-studio' -and $h.worker_online){exit 0}}catch{};Start-Sleep -Milliseconds 500};exit 1"
if errorlevel 1 goto failed
start "" "http://127.0.0.1:5088"
exit /b 0
:failed
echo Book Studio could not start. Extract the complete source folder and check the message above.
echo Your existing Factory and its books were not changed.
pause
exit /b 1
