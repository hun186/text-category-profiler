@echo off
setlocal
cd /d "%~dp0"
REM Jaal-only view: no WorkPool rename, classifier, or Stage 4 handoff.
REM Requires Python/Dash/Jaal dependencies in the active environment.
python BertScript\Test_result_Vis.py --viewer-only -p 8059 %*
if errorlevel 1 (
  echo.
  echo Jaal viewer failed. Check the Python environment and port 8059.
  pause
)
