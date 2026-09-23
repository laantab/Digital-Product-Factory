@echo off
setlocal EnableExtensions EnableDelayedExpansion
title Factory Release Manager

REM ===========================================================================
REM  Factory Release Manager
REM
REM  One double-click takes a finished release branch all the way to a pull
REM  request you only have to click Merge on.
REM
REM    1. Checks you are in the right repository and on the right commit
REM    2. Runs the Fast Stability Gate in a temporary copy
REM    3. Runs the full release gate: live main against your branch
REM    4. Pushes the branch ONLY if the gate found no new failures
REM    5. Creates the pull request, or opens the page to create it
REM    6. Writes one plain-language report and opens it in Notepad
REM
REM  It never touches .env, never spends money, never merges, never deploys,
REM  never changes a Render setting, and never pushes a branch whose gate
REM  failed. It does not switch your branch or touch your unsaved files.
REM
REM  TO USE IT: edit the two lines under SETTINGS, then double-click.
REM ===========================================================================

REM ------------------------------- SETTINGS ---------------------------------
set "BRANCH=v1.9.1-launch-blockers"
set "EXPECTED_COMMIT=REPLACE_WITH_TIP"
REM  The exact commit this run is meant to push. If the branch is on anything
REM  else the file stops and changes nothing. Leaving it blank turns that check
REM  OFF and accepts whatever the branch happens to point at -- only do that
REM  knowingly. Claude sets this to the reviewed commit for each release.
REM --------------------------------------------------------------------------

set "REPO=%USERPROFILE%\Documents\Product-Pipeline\Factory-v1.3"
set "EXPECTED_REPO=laantab/Digital-Product-Factory"
set "BASE=main"
set "PY=%USERPROFILE%\AppData\Local\Python\pythoncore-3.14-64\python.exe"
if not exist "%PY%" set "PY=python"
set "DESK=%USERPROFILE%\OneDrive\Desktop"
if not exist "%DESK%" set "DESK=%USERPROFILE%\Desktop"
set "REPORT=%DESK%\Factory release report.txt"
set "WT=%TEMP%\factory_release_fast"
set "WA=%TEMP%\factory_release_main"
set "WB=%TEMP%\factory_release_branch"

echo.
echo   Factory Release Manager
echo   Branch: %BRANCH%
echo.
echo   Working. Leave this window open - it takes about 20 to 30 minutes.
echo   A report will open in Notepad when it finishes.
echo.

>"%REPORT%" echo FACTORY RELEASE REPORT
>>"%REPORT%" echo Branch : %BRANCH%
>>"%REPORT%" echo Run at : %DATE% %TIME%
>>"%REPORT%" echo.
>>"%REPORT%" echo This file does not merge, deploy, change any Render setting,
>>"%REPORT%" echo touch .env, or make any paid call. It pushes only %BRANCH%,
>>"%REPORT%" echo and only if the release gate finds no new failures.
>>"%REPORT%" echo.

pushd "%REPO%" >nul 2>&1 || (>>"%REPORT%" echo STOPPED SAFELY: Factory folder not found at %REPO%. & goto :finish)

REM --------------------------------------------------------------- STEP 1 ---
>>"%REPORT%" echo === STEP 1 of 6 - Safety checks. Nothing is changed here. ===
set "REMOTE="
for /f "delims=" %%A in ('git remote get-url origin 2^>nul') do set "REMOTE=%%A"
echo !REMOTE! | findstr /i "%EXPECTED_REPO%" >nul || (>>"%REPORT%" echo STOPPED SAFELY: this is not the Digital Product Factory repository: !REMOTE! & goto :leave)
>>"%REPORT%" echo OK - repository is %EXPECTED_REPO%
git fetch --quiet origin >nul 2>&1

set "GITDIR="
for /f "delims=" %%A in ('git rev-parse --git-dir 2^>nul') do set "GITDIR=%%A"
for %%F in (MERGE_HEAD rebase-merge rebase-apply CHERRY_PICK_HEAD index.lock) do if exist "!GITDIR!\%%F" (>>"%REPORT%" echo STOPPED SAFELY: Git is busy with another operation ^(%%F^). Nothing was changed. & goto :leave)

set "HEAD="
for /f "delims=" %%A in ('git rev-parse "%BRANCH%" 2^>nul') do set "HEAD=%%A"
if "!HEAD!"=="" (>>"%REPORT%" echo STOPPED SAFELY: there is no branch called %BRANCH%. & goto :leave)
if not "%EXPECTED_COMMIT%"=="" if /i not "!HEAD!"=="%EXPECTED_COMMIT%" (>>"%REPORT%" echo STOPPED SAFELY: %BRANCH% is at "!HEAD!", expected %EXPECTED_COMMIT%. & goto :leave)
>>"%REPORT%" echo OK - %BRANCH% is at !HEAD!

set "VER="
for /f "delims=" %%A in ('git show "%BRANCH%:VERSION" 2^>nul') do set "VER=%%A"
>>"%REPORT%" echo OK - VERSION on the branch is !VER!

set "CUR="
for /f "delims=" %%A in ('git branch --show-current 2^>nul') do set "CUR=%%A"
if /i "!CUR!"=="%BRANCH%" (>>"%REPORT%" echo STOPPED SAFELY: %BRANCH% is your open branch; this file only runs when it is not, so your working files are never touched. & goto :leave)
set "DIRTY=0"
for /f %%A in ('git status --porcelain 2^>nul ^| find /c /v ""') do set "DIRTY=%%A"
>>"%REPORT%" echo OK - your open branch is !CUR!; its !DIRTY! unsaved file^(s^) are left exactly as they are.

set "MAINSHA="
for /f "tokens=1" %%A in ('git ls-remote --heads origin "refs/heads/%BASE%" 2^>nul') do set "MAINSHA=%%A"
if "!MAINSHA!"=="" (>>"%REPORT%" echo STOPPED SAFELY: could not read %BASE% from GitHub. Check your internet connection. & goto :leave)
>>"%REPORT%" echo OK - GitHub %BASE% is at !MAINSHA!
>>"%REPORT%" echo.

REM --------------------------------------------------------------- STEP 2 ---
>>"%REPORT%" echo === STEP 2 of 6 - Python packages ===
"%PY%" -m pip install --quiet -r requirements.txt >nul 2>&1
"%PY%" -m pip install --quiet "Flask-Login==0.6.3" "bcrypt==5.0.0" >>"%REPORT%" 2>&1
if errorlevel 1 (>>"%REPORT%" echo STOPPED SAFELY: could not install the Python packages. Nothing was pushed. & goto :leave)
>>"%REPORT%" echo OK
>>"%REPORT%" echo.

REM --------------------------------------------------------------- STEP 3 ---
>>"%REPORT%" echo === STEP 3 of 6 - Fast Stability Gate, in a temporary copy ===
if exist "%WT%" git worktree remove --force "%WT%" >nul 2>&1
git worktree add --detach "%WT%" "%BRANCH%" >>"%REPORT%" 2>&1
if errorlevel 1 (>>"%REPORT%" echo STOPPED SAFELY: could not make the temporary copy. & goto :leave)
pushd "%WT%"
"%PY%" scripts\fast_gate.py > "%TEMP%\factory_fast_gate.txt" 2>&1
set "RC=!ERRORLEVEL!"
popd
git worktree remove --force "%WT%" >nul 2>&1
powershell -NoProfile -Command "Get-Content -Tail 8 '%TEMP%\factory_fast_gate.txt'" >>"%REPORT%"
if not "!RC!"=="0" (>>"%REPORT%" echo FAST GATE FAILED - exit code !RC!. Nothing was pushed. & goto :leave)
>>"%REPORT%" echo FAST GATE PASSED
>>"%REPORT%" echo.

REM --------------------------------------------------------------- STEP 4 ---
>>"%REPORT%" echo === STEP 4 of 6 - Full release gate: live %BASE% against %BRANCH% ===
>>"%REPORT%" echo This is the long part. About 20 to 30 minutes.
for %%W in ("!WA!" "!WB!") do if exist "%%~W" git worktree remove --force "%%~W" >nul 2>&1
git worktree add --detach "!WA!" "!MAINSHA!" >nul 2>&1 || (>>"%REPORT%" echo STOPPED: could not copy %BASE%. & goto :leave)
git worktree add --detach "!WB!" "%BRANCH%" >nul 2>&1 || (>>"%REPORT%" echo STOPPED: could not copy %BRANCH%. & goto :gatecleanup)
pushd "!WA!"
"%PY%" scripts\run_factory_tests.py > "%TEMP%\factory_gate_main.txt" 2>&1
popd
pushd "!WB!"
"%PY%" scripts\run_factory_tests.py > "%TEMP%\factory_gate_branch.txt" 2>&1
popd
set "CMP=%DESK%\Factory Gate Tools\compare_gate.py"
if not exist "!CMP!" (>>"%REPORT%" echo STOPPED: could not find the gate comparison tool at !CMP! & goto :gatecleanup)
"%PY%" "!CMP!" "!WA!\test-results\factory-junit.xml" "!WB!\test-results\factory-junit.xml" > "%TEMP%\factory_gate_compare.txt" 2>&1
type "%TEMP%\factory_gate_compare.txt" >>"%REPORT%"
findstr /c:"MERGE GATE: PASS" "%TEMP%\factory_gate_compare.txt" >nul
set "GATE=!ERRORLEVEL!"
for %%W in ("!WA!" "!WB!") do if exist "%%~W" git worktree remove --force "%%~W" >nul 2>&1
if not "!GATE!"=="0" (
  >>"%REPORT%" echo.
  >>"%REPORT%" echo THE GATE FOUND NEW FAILURES. Nothing was pushed and no pull request was made.
  >>"%REPORT%" echo Send the list above to Claude; it is the exact thing to fix.
  goto :leave
)
>>"%REPORT%" echo.
>>"%REPORT%" echo FULL GATE PASSED - no new failures
>>"%REPORT%" echo.

REM --------------------------------------------------------------- STEP 5 ---
>>"%REPORT%" echo === STEP 5 of 6 - Push this branch to GitHub ===
git push origin "%BRANCH%:refs/heads/%BRANCH%" >>"%REPORT%" 2>&1
if errorlevel 1 (>>"%REPORT%" echo STOPPED SAFELY: the push did not complete. & goto :leave)
set "REMOTE_FULL="
for /f "tokens=1" %%A in ('git ls-remote --heads origin "refs/heads/%BRANCH%" 2^>nul') do set "REMOTE_FULL=%%A"
>>"%REPORT%" echo Your computer : !HEAD!
>>"%REPORT%" echo GitHub        : !REMOTE_FULL!
if /i not "!HEAD!"=="!REMOTE_FULL!" (>>"%REPORT%" echo STOPPED: GitHub does not match what was pushed. & goto :leave)
>>"%REPORT%" echo PUSH COMPLETE - GitHub matches.
>>"%REPORT%" echo.

REM --------------------------------------------------------------- STEP 6 ---
>>"%REPORT%" echo === STEP 6 of 6 - Pull request ===
set "PRURL=https://github.com/%EXPECTED_REPO%/compare/%BASE%...%BRANCH%"
where gh >nul 2>&1
if errorlevel 1 (
  >>"%REPORT%" echo The GitHub command line tool is not installed, so the pull request
  >>"%REPORT%" echo was not created automatically. The page to create it is opening in
  >>"%REPORT%" echo your browser now. Everything is already pushed and tested.
  start "" "!PRURL!"
  goto :done
)
gh auth status >nul 2>&1
if errorlevel 1 (
  >>"%REPORT%" echo The GitHub command line tool is installed but not signed in
  >>"%REPORT%" echo ^(run: gh auth login^). The page to create the pull request is
  >>"%REPORT%" echo opening in your browser now.
  start "" "!PRURL!"
  goto :done
)
set "BODYFILE=%TEMP%\factory_pr_body.md"
>"%BODYFILE%" echo Release branch %BRANCH% at !HEAD!.
>>"%BODYFILE%" echo.
>>"%BODYFILE%" echo The full release gate was run against GitHub %BASE% ^(!MAINSHA!^) and
>>"%BODYFILE%" echo found no new failures. The Fast Stability Gate passed. The branch was
>>"%BODYFILE%" echo pushed only after both.
>>"%BODYFILE%" echo.
>>"%BODYFILE%" echo Gate comparison:
>>"%BODYFILE%" echo.
>>"%BODYFILE%" echo ```
type "%TEMP%\factory_gate_compare.txt" >>"%BODYFILE%"
>>"%BODYFILE%" echo ```
>>"%BODYFILE%" echo.
>>"%BODYFILE%" echo Opened by Factory Release Manager. Nothing was merged or deployed.
gh pr create --base "%BASE%" --head "%BRANCH%" --title "Factory %VER% - %BRANCH%" --body-file "%BODYFILE%" > "%TEMP%\factory_pr.txt" 2>&1
if errorlevel 1 (
  >>"%REPORT%" echo Could not create the pull request automatically:
  powershell -NoProfile -Command "Get-Content -Tail 5 '%TEMP%\factory_pr.txt'" >>"%REPORT%"
  >>"%REPORT%" echo The page to create it by hand is opening in your browser now.
  start "" "!PRURL!"
  goto :done
)
set "PRLINK="
for /f "delims=" %%A in ('type "%TEMP%\factory_pr.txt" ^| findstr /i "https://github.com"') do set "PRLINK=%%A"
>>"%REPORT%" echo Pull request created: !PRLINK!
start "" "!PRLINK!"

:done
>>"%REPORT%" echo.
>>"%REPORT%" echo ==========================================================
>>"%REPORT%" echo   EVERYTHING PASSED. One thing left for you to do:
>>"%REPORT%" echo   click the green Merge button on the pull request page
>>"%REPORT%" echo   that just opened in your browser.
>>"%REPORT%" echo.
>>"%REPORT%" echo   Nothing has been merged or deployed yet. The live site is
>>"%REPORT%" echo   still running %BASE% at !MAINSHA!.
>>"%REPORT%" echo ==========================================================
goto :leave

:gatecleanup
for %%W in ("!WA!" "!WB!") do if exist "%%~W" git worktree remove --force "%%~W" >nul 2>&1

:leave
popd >nul 2>&1
:finish
>>"%REPORT%" echo.
>>"%REPORT%" echo Finished: %DATE% %TIME%
start "" notepad.exe "%REPORT%"
endlocal
