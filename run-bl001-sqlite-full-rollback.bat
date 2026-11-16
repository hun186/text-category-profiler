@echo off
setlocal
cd /d "%~dp0"
rem Real SQLite page-limit failure on a PRIVATE temporary DB, never WorkPool.
python -m scripts.bl001_stage_sqlite_full_rollback %*
exit /b %ERRORLEVEL%
