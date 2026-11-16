@echo off
setlocal
cd /d "%~dp0"
rem Offline QUIESCENT SQLite copy only, metadata-only; no cleanup operation.
python -m scripts.bl001_stage_sqlite_candidate_triage %*
exit /b %ERRORLEVEL%
