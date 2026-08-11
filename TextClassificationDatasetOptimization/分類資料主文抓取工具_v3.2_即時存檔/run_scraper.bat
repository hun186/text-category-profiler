@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"

set "TEST_MODE=0"
if /I "%~2"=="test" set "TEST_MODE=1"
if /I "%~2"=="--test-mode" set "TEST_MODE=1"

set "INPUT_ZIP="
set "BASE_DIR=%~dp0"
if not "%~1"=="" (
    set "INPUT_ZIP=%~f1"
    set "BASE_DIR=%~dp1"
)

if defined INPUT_ZIP if not exist "%INPUT_ZIP%" (
    echo [ERROR] Input ZIP not found:
    echo %INPUT_ZIP%
    pause
    exit /b 2
)

set "PY_LAUNCHER=py -3"
where py >nul 2>nul
if errorlevel 1 (
    where python >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Python 3 was not found.
        echo Install Python 3.10 or newer, or run this from an active Conda environment.
        pause
        exit /b 2
    )
    set "PY_LAUNCHER=python"
)

if not exist ".venv\Scripts\python.exe" (
    echo [1/3] Creating local Python environment...
    %PY_LAUNCHER% -m venv .venv
    if errorlevel 1 goto :error
)

set "PYTHON_EXE=%CD%\.venv\Scripts\python.exe"
for /f %%i in ('powershell -NoProfile -Command "Get-Date -Format yyyyMMdd_HHmmss"') do set "STAMP=%%i"

if "%TEST_MODE%"=="1" (
    set "OUTPUT_PREFIX=Article_Text_Package_TEST"
    set "MODE_NAME=TEST"
) else (
    set "OUTPUT_PREFIX=Article_Text_Package"
    set "MODE_NAME=FULL"
)

set "OUTPUT_DIR=%BASE_DIR%%OUTPUT_PREFIX%_%STAMP%"
set "OUTPUT_ZIP=%BASE_DIR%%OUTPUT_PREFIX%_%STAMP%.zip"
set "LOG_DIR=%BASE_DIR%Article_Scrape_Log_%MODE_NAME%_%STAMP%"

echo [2/3] Installing required packages...
"%PYTHON_EXE%" -m pip install --upgrade pip
if errorlevel 1 goto :error
"%PYTHON_EXE%" -m pip install -r requirements-core.txt
if errorlevel 1 goto :error
"%PYTHON_EXE%" -m pip install -r requirements-optional.txt
if errorlevel 1 echo [WARN] Optional packages failed to install. Built-in extraction will still be used.

echo.
echo [3/3] Starting article extraction...
echo Completed article TXT files are saved immediately during the ARTICLE stage.
if "%TEST_MODE%"=="1" echo Mode: TEST - 10 results per search index, 20 articles per category.
if "%TEST_MODE%"=="0" echo Mode: FULL - no program-side result or category limit.
echo Output: %OUTPUT_DIR%
echo.

if defined INPUT_ZIP goto :run_with_input
if "%TEST_MODE%"=="1" goto :run_default_test

goto :run_default_full

:run_with_input
if "%TEST_MODE%"=="1" (
    "%PYTHON_EXE%" scrape_articles.py --input-zip "%INPUT_ZIP%" --output-dir "%OUTPUT_DIR%" --output-zip "%OUTPUT_ZIP%" --log-dir "%LOG_DIR%" --workers 6 --per-domain-delay 1.2 --dedupe-scope category --clean-output --test-mode
) else (
    "%PYTHON_EXE%" scrape_articles.py --input-zip "%INPUT_ZIP%" --output-dir "%OUTPUT_DIR%" --output-zip "%OUTPUT_ZIP%" --log-dir "%LOG_DIR%" --workers 6 --per-domain-delay 1.2 --dedupe-scope category --clean-output
)
goto :finished

:run_default_test
"%PYTHON_EXE%" scrape_articles.py --output-dir "%OUTPUT_DIR%" --output-zip "%OUTPUT_ZIP%" --log-dir "%LOG_DIR%" --workers 6 --per-domain-delay 1.2 --dedupe-scope category --clean-output --test-mode
goto :finished

:run_default_full
"%PYTHON_EXE%" scrape_articles.py --output-dir "%OUTPUT_DIR%" --output-zip "%OUTPUT_ZIP%" --log-dir "%LOG_DIR%" --workers 6 --per-domain-delay 1.2 --dedupe-scope category --clean-output

:finished
set "RC=%ERRORLEVEL%"
echo.
if "%RC%"=="0" (
    echo Completed successfully.
) else (
    echo Completed with errors. Check the CSV files in:
    echo %LOG_DIR%
)
echo Output folder: %OUTPUT_DIR%
echo Output ZIP:    %OUTPUT_ZIP%
pause
exit /b %RC%

:error
echo.
echo [ERROR] Environment setup or package installation failed.
pause
exit /b 1
