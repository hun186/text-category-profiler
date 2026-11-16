@echo off
setlocal
cd /d "%~dp0"
rem KI-012 private cross-process overlap/orphan acceptance only.
rem Never accepts a real database path or changes production WorkPool.
python -m scripts.bl001_stage_sqlite_overlap_acceptance %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" echo [KI-012 overlap/orphan] FAIL or BLOCKED - see JSON.
exit /b %RC%
