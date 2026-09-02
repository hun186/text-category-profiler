@echo off
setlocal EnableExtensions DisableDelayedExpansion
cd /d "%~dp0"
set "PY_CMD=py -3"
where py >nul 2>nul
if errorlevel 1 set "PY_CMD=python"
if "%~1"=="" (
    %PY_CMD% scrape_articles.py --dry-run
) else (
    %PY_CMD% scrape_articles.py --input-zip "%~f1" --dry-run
)
pause
