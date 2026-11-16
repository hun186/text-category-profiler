@echo off
setlocal
cd /d "%~dp0"
rem Private temporary SQLite cross-process lock/retry and killed lock-holder test.
rem Never accepts a WorkPool or production DB path.
python -m scripts.bl001_stage_sqlite_lock_acceptance %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" echo [BL-001 SQLite lock/retry] FAIL or BLOCKED - see JSON result above.
exit /b %RC%
