@echo off
setlocal
cd /d "%~dp0"
rem Use two independently prepared quiescent offline copies ONLY.
python -m scripts.bl001_stage_sqlite_candidate_diff %*
exit /b %ERRORLEVEL%
