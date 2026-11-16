@echo off
setlocal
cd /d "%~dp0"
rem Inspect only an independently prepared, stopped-writer SQLite COPY.
python -m scripts.bl001_stage_sqlite_dependency_inventory %*
exit /b %ERRORLEVEL%
