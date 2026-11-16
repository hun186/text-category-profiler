@echo off
setlocal
cd /d "%~dp0"
rem Private SQLite reader/writer process test; NEVER accepts external WorkPool.
python -m scripts.bl001_stage_sqlite_reader_snapshot %*
exit /b %ERRORLEVEL%
