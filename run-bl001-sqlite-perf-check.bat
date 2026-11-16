@echo off
setlocal
cd /d "%~dp0"
rem PRIVATE TEMPFILE ONLY. Defaults 1000 rows x 2 rounds. Never pass a DB path.
python -m scripts.bl001_stage_sqlite_performance_profile %*
exit /b %ERRORLEVEL%
