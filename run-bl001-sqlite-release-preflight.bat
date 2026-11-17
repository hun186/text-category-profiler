@echo off
setlocal
cd /d "%~dp0"
rem Private SQLite checks plus isolated TCFMain self-test.
rem Optional: --real-port 8050 runs a REAL model in a disposable TCFMain self-test.
rem This opt-in now COPIES all checkpoint-* model bytes to a temporary folder.
rem Ensure adequate free local disk space; original model and WorkPool are not test targets.
rem Exit 2 is PASS_PARTIAL_NO_REAL_MODEL, NOT full acceptance.
python -m scripts.bl001_stage_sqlite_release_preflight %*
exit /b %ERRORLEVEL%
