@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title Digital Product Factory - Verify v1.8.0 Workflows

REM ==========================================================================
REM  Double-click this file. It only READS and TESTS.
REM
REM  It does not push to GitHub, does not touch Render, does not deploy,
REM  does not call any paid API, and does not change any of your books.
REM
REM  When it finishes it writes a plain-text report to your Desktop and
REM  opens it in Notepad.
REM ==========================================================================

set "PY=C:\Users\user\AppData\Local\Python\pythoncore-3.14-64\python.exe"
if not exist "%PY%" set "PY=python"

set "DESK=%USERPROFILE%\OneDrive\Desktop"
if not exist "%DESK%" set "DESK=%USERPROFILE%\Desktop"
set "REPORT=%DESK%\Factory_v1.8.0_Verification.txt"

echo Running the v1.8.0 checks. This takes a couple of minutes.
echo A report will open in Notepad when it is done.
echo.

> "%REPORT%" echo DIGITAL PRODUCT FACTORY - v1.8.0 WORKFLOWS VERIFICATION
>>"%REPORT%" echo Run on %DATE% at %TIME%
>>"%REPORT%" echo Folder: %CD%
>>"%REPORT%" echo.
>>"%REPORT%" echo THIS REPORT IS LOCAL ONLY. Nothing was pushed and nothing was deployed.
>>"%REPORT%" echo.

REM ---------------------------------------------------------------- 1. state
>>"%REPORT%" echo ==========================================================
>>"%REPORT%" echo 1. WHERE YOU ARE
>>"%REPORT%" echo ==========================================================
git rev-parse --abbrev-ref HEAD  >>"%REPORT%" 2>&1
git log -1 --oneline             >>"%REPORT%" 2>&1
>>"%REPORT%" echo.
>>"%REPORT%" echo VERSION file:
type VERSION                     >>"%REPORT%" 2>&1
>>"%REPORT%" echo.
>>"%REPORT%" echo Uncommitted changes:
git status --short               >>"%REPORT%" 2>&1
>>"%REPORT%" echo.

REM ------------------------------------------------------------ 2. new tests
>>"%REPORT%" echo ==========================================================
>>"%REPORT%" echo 2. THE v1.8.0 TESTS (the new work)
>>"%REPORT%" echo ==========================================================
set "FACTORY_TEST_MODE=1"
"%PY%" -m pytest -q tests\test_ebook_workflow_execution.py >>"%REPORT%" 2>&1
if errorlevel 1 (set "R2=FAILED") else (set "R2=PASSED")
>>"%REPORT%" echo.
>>"%REPORT%" echo RESULT: !R2!
>>"%REPORT%" echo.

REM --------------------------------------------------- 3. no regression here
>>"%REPORT%" echo ==========================================================
>>"%REPORT%" echo 3. THE BUILD ENGINE TESTS THAT ALREADY PASSED (no regression)
>>"%REPORT%" echo ==========================================================
"%PY%" -m pytest -q tests\test_ebook_durable_executor.py tests\test_ebook_build_resume_recovery.py tests\test_ebook_resume_hands_work_to_the_server.py tests\test_ebook_resume_surface.py >>"%REPORT%" 2>&1
if errorlevel 1 (set "R3=FAILED") else (set "R3=PASSED")
>>"%REPORT%" echo.
>>"%REPORT%" echo RESULT: !R3!
>>"%REPORT%" echo.

REM ------------------------------------------------------ 4. stability gate
>>"%REPORT%" echo ==========================================================
>>"%REPORT%" echo 4. FAST STABILITY GATE (your other products still fine)
>>"%REPORT%" echo ==========================================================
"%PY%" -m pytest -q tests\factory_golden_customer_path_smoke_suite.py tests\test_universal_topic_puzzle_engine.py tests\test_crossword_scope_answerkey_zip_repair.py tests\test_coloring_book_sea_creatures_customer_path.py tests\test_coloring_book_local_fallback_theme_classification.py tests\test_spelling_worksheet_topic_relevance.py tests\test_spelling_worksheet_release_readiness.py tests\test_spelling_worksheet_semantic_scope.py tests\test_african_animals_topic_repair.py tests\test_invite_gate.py tests\test_render_persistence_patch.py tests\test_customer_journey_every_product_type.py tests\test_ebook_saved_projects_visibility.py tests\test_saved_projects_reopen_build.py tests\test_reopen_packaging_identity_pass2.py tests\test_download_slug_package_id.py tests\test_word_search_topic_scope_contract.py tests\test_coloring_book_interior_no_text_contract.py tests\test_function_lock_registry_integrity.py tests\test_function_lock_enforcement.py tests\test_storage_foundation.py tests\test_storage_r2_cutover.py >>"%REPORT%" 2>&1
if errorlevel 1 (set "R4=FAILED") else (set "R4=PASSED")
>>"%REPORT%" echo.
>>"%REPORT%" echo RESULT: !R4!
>>"%REPORT%" echo.

REM -------------------------------------------- 5. local mode is untouched
>>"%REPORT%" echo ==========================================================
>>"%REPORT%" echo 5. YOUR PC IS UNAFFECTED
>>"%REPORT%" echo ==========================================================
>>"%REPORT%" echo The Factory only behaves differently when FACTORY_EXECUTION_MODE
>>"%REPORT%" echo is set to "workflow". On this PC it is not set, so the Factory
>>"%REPORT%" echo builds books exactly as it did in v1.7.29, including local Ollama.
>>"%REPORT%" echo.
>>"%REPORT%" echo Value of FACTORY_EXECUTION_MODE on this PC: [%FACTORY_EXECUTION_MODE%]
>>"%REPORT%" echo (empty square brackets above means "not set", which is correct)
>>"%REPORT%" echo.

REM --------------------------------------------------------------- summary
>>"%REPORT%" echo ==========================================================
>>"%REPORT%" echo SUMMARY
>>"%REPORT%" echo ==========================================================
>>"%REPORT%" echo   2. v1.8.0 tests ............... !R2!
>>"%REPORT%" echo   3. build engine tests ......... !R3!
>>"%REPORT%" echo   4. fast stability gate ........ !R4!
>>"%REPORT%" echo.
if "!R2!"=="PASSED" if "!R3!"=="PASSED" if "!R4!"=="PASSED" (
  >>"%REPORT%" echo   ALL CHECKS PASSED.
) else (
  >>"%REPORT%" echo   SOMETHING FAILED. Scroll up in this file to the section
  >>"%REPORT%" echo   marked FAILED and send that part to Claude.
)
>>"%REPORT%" echo.
>>"%REPORT%" echo ==========================================================
>>"%REPORT%" echo WHAT HAS NOT BEEN DONE
>>"%REPORT%" echo ==========================================================
>>"%REPORT%" echo   - Nothing was pushed to GitHub.
>>"%REPORT%" echo   - No Render service was created or changed.
>>"%REPORT%" echo   - The live site is still running v1.7.29 and is untouched.
>>"%REPORT%" echo   - Creating the Render Workflow service costs money and is
>>"%REPORT%" echo     your decision. See V1_8_0_WORKFLOWS_DEPLOYMENT.md.
>>"%REPORT%" echo.

start "" notepad "%REPORT%"
endlocal
exit /b 0
