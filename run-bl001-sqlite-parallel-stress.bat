@echo off
setlocal
cd /d "%~dp0"
rem Private temp SQLite and bounded local subprocesses ONLY.
python -m scripts.bl001_stage_sqlite_parallel_stress %*
exit /b %ERRORLEVEL%
