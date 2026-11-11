@echo off
setlocal
cd /d "%~dp0"
rem BL-001: check Stage-local TSV/XLSX/SQLite with private test fixtures only.
rem No model run, WorkPool rename, or production database access.
rem Requires pandas and xlsxwriter in the current Python environment.
python -m scripts.bl001_stage_writer_check %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" echo [BL-001 stage writer] FAIL or BLOCKED - see checks above.
exit /b %RC%
