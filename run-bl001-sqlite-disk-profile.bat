@echo off
setlocal
cd /d "%~dp0"
rem Private tempfile SQLite disk checkpoint probe; no WorkPool or external DB path.
python -m scripts.bl001_stage_sqlite_disk_profile %*
exit /b %ERRORLEVEL%
