@echo off
setlocal
cd /d "%~dp0"
rem KI-012 metadata-only inventory; --db MUST reference a separate QUIESCENT COPY.
rem This script never drops, vacuums, migrates or repairs any SQLite table.
python -m scripts.bl001_stage_sqlite_candidate_inventory %*
set "RC=%ERRORLEVEL%"
if "%RC%"=="1" echo [KI-012] REVIEW_REQUIRED: candidate names alone do not prove an orphan.
if "%RC%"=="2" echo [KI-012] UNVERIFIABLE: no safe conclusion; check offline copy/schema.
exit /b %RC%
