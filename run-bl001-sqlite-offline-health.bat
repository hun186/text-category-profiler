@echo off
setlocal
cd /d "%~dp0"
rem Bounded readonly quick_check on detached quiescent SQLite COPY; no live WorkPool.
python -m scripts.bl001_stage_sqlite_offline_health %*
exit /b %ERRORLEVEL%
