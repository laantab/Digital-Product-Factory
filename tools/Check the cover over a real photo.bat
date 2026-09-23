@echo off
setlocal
title Cover check over a real photograph
set "REPO=%USERPROFILE%\Documents\Product-Pipeline\Factory-v1.3"
set "PY=%USERPROFILE%\AppData\Local\Python\pythoncore-3.14-64\python.exe"
if not exist "%PY%" set "PY=python"
echo.
echo   Building the three book covers over a real photograph.
echo   This is free. Pexels costs nothing and no project is changed.
echo.
pushd "%REPO%" || (echo Factory folder not found. & pause & exit /b 1)
"%PY%" scripts\check_cover_over_a_real_photo.py
set "RC=%ERRORLEVEL%"
popd
echo.
if not "%RC%"=="0" (
  echo   It did not finish, so no pictures were made. The reason is printed above.
  echo   Nothing was changed.
) else (
  echo   Done. The pictures are on your Desktop in "Cover check over a real photo".
)
echo.
pause
endlocal
