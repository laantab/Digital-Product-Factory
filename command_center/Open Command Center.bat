@echo off
REM Opens the Digital Product Factory Command Center on its own port (5090).
REM Safe to run alongside the owner's Factory (5055) and Claude's Factory (5077) --
REM this is a separate, read-only status page. It never touches projects.db,
REM never calls a paid API, and never generates a product.
cd /d "%~dp0.."
set COMMAND_CENTER_PORT=5090
start "" "http://127.0.0.1:5090/"
"C:\Users\user\AppData\Local\Python\pythoncore-3.14-64\python.exe" -m command_center.server
