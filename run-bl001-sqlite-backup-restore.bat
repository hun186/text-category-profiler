@echo off
setlocal
cd /d "%~dp0"
rem Always creates source/backup/restored SQLite in private TemporaryDirectory.
python -m scripts.bl001_stage_sqlite_backup_restore %*
exit /b %ERRORLEVEL%
