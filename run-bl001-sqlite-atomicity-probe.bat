@echo off
setlocal
cd /d "%~dp0"
rem Only a private temp SQLite writer-kill diagnostic; never accepts a DB path.
rem FAIL_ATOMICITY is a detected safety gap, not a crashed test harness.
python -m scripts.bl001_stage_sqlite_atomicity_probe %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" echo [BL-001 SQLite atomicity] FAIL_ATOMICITY or BLOCKED - see JSON result.
exit /b %RC%
