@echo off
setlocal
cd /d "%~dp0"
rem PRIVATE temp SQLite WAL backup check only; no external DB arguments.
python -m scripts.bl001_stage_sqlite_wal_backup %*
exit /b %ERRORLEVEL%
