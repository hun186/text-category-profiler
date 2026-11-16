@echo off
setlocal
cd /d "%~dp0"
rem Private SQLite checks plus isolated TCFMain self-test.
rem Optional: --real-port 8050 loads the local model in disposable TCFMain self-test.
rem Exit 2 is PASS_PARTIAL_NO_REAL_MODEL, NOT full acceptance.
python -m scripts.bl001_stage_sqlite_release_preflight %*
exit /b %ERRORLEVEL%
