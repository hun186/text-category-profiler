@echo off
setlocal
cd /d "%~dp0"
rem Metadata-only WorkPool observation; never reads SQLite or modifies data.
rem Usage: run-bl001-workpool-readonly-inventory.bat --workpool "D:\...\WorkPool"
rem Exit 0 = OBSERVED_METADATA_ONLY (NOT deployment PASS); 1 = REVIEW_REQUIRED; 2 = UNVERIFIABLE.
python -m scripts.bl001_workpool_readonly_inventory %*
exit /b %ERRORLEVEL%
