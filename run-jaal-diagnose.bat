@echo off
setlocal
cd /d "%~dp0" || exit /b 1
echo ===== Jaal Read-Only Environment and AttributeError Diagnosis =====
echo Uses the Python environment running this BAT file.
echo No port is opened. No model or WorkPool task is executed.
python -m BertScript.jaal_runtime_diagnostics --root "TW Affairs"
set "RC=%ERRORLEVEL%"
echo.
if not "%RC%"=="0" (
  echo JAAL_DIAGNOSE_FAILED. Review the full traceback above.
  echo Share the exception type, missing attribute, and package versions.
  echo Check or redact local paths before sharing the log.
) else (
  echo JAAL_DIAGNOSE_PASS. The build stage worked in this interpreter.
)
echo.
pause
exit /b %RC%
