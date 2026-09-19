@echo off
setlocal
REM ===================================================================
REM  Push v1.8.1 to GitHub - SAFE
REM
REM  This pushes ONE BRANCH: fix/v1.8.1-workspace-to-builder
REM
REM  It does NOT merge to main.
REM  It does NOT deploy anything.
REM  It does NOT touch Render or the live site.
REM
REM  Nothing a customer can see changes when you run this.
REM ===================================================================

set REPO=C:\Users\user\Documents\Product-Pipeline\Factory-v1.3
set BRANCH=fix/v1.8.1-workspace-to-builder
set REPORT=%USERPROFILE%\Desktop\v1_8_1_push_report.txt

cd /d "%REPO%" || (echo Could not find the Factory folder. & pause & exit /b 1)

echo Pushing v1.8.1 to GitHub...
echo.

> "%REPORT%" echo v1.8.1 PUSH REPORT
>>"%REPORT%" echo Run at: %DATE% %TIME%
>>"%REPORT%" echo Folder: %REPO%
>>"%REPORT%" echo.
>>"%REPORT%" echo ===================================================================
>>"%REPORT%" echo STEP 1 - Which branch am I on?
>>"%REPORT%" echo ===================================================================
for /f "delims=" %%B in ('git branch --show-current') do set CURRENT=%%B
>>"%REPORT%" echo Current branch: %CURRENT%
>>"%REPORT%" echo Expected      : %BRANCH%
>>"%REPORT%" echo.

if not "%CURRENT%"=="%BRANCH%" (
  >>"%REPORT%" echo STOPPED. You are not on the v1.8.1 branch, so nothing was pushed.
  >>"%REPORT%" echo Nothing was changed. Send this report to Claude.
  notepad "%REPORT%"
  exit /b 1
)

>>"%REPORT%" echo ===================================================================
>>"%REPORT%" echo STEP 2 - Is anything unsaved?
>>"%REPORT%" echo ===================================================================
git -c core.autocrlf=input status --short >>"%REPORT%" 2>&1
>>"%REPORT%" echo (nothing listed above means everything is saved)
>>"%REPORT%" echo.

>>"%REPORT%" echo ===================================================================
>>"%REPORT%" echo STEP 3 - What is being pushed
>>"%REPORT%" echo ===================================================================
git log --oneline origin/main..HEAD >>"%REPORT%" 2>&1
>>"%REPORT%" echo.

>>"%REPORT%" echo ===================================================================
>>"%REPORT%" echo STEP 4 - Pushing the branch (NOT main)
>>"%REPORT%" echo ===================================================================
git push -u origin %BRANCH% >>"%REPORT%" 2>&1
set PUSHED=%ERRORLEVEL%
>>"%REPORT%" echo.

if "%PUSHED%"=="0" (
  >>"%REPORT%" echo RESULT: SUCCESS - the branch is now on GitHub.
  >>"%REPORT%" echo.
  >>"%REPORT%" echo main was NOT changed. Nothing was deployed. The live site is
  >>"%REPORT%" echo untouched. Opening a pull request, merging, and the Render
  >>"%REPORT%" echo builder branch switch are all still your decision.
) else (
  >>"%REPORT%" echo RESULT: DID NOT PUSH - see the message above.
  >>"%REPORT%" echo.
  >>"%REPORT%" echo Nothing was changed on GitHub. Your work is still safe in this
  >>"%REPORT%" echo folder. If it asked you to sign in, run this file again and
  >>"%REPORT%" echo complete the GitHub sign-in window.
)

>>"%REPORT%" echo.
>>"%REPORT%" echo ===================================================================
>>"%REPORT%" echo STEP 5 - Where things stand now
>>"%REPORT%" echo ===================================================================
git log --oneline -1 >>"%REPORT%" 2>&1
git branch -vv >>"%REPORT%" 2>&1

echo Done. Opening the report...
notepad "%REPORT%"
endlocal
