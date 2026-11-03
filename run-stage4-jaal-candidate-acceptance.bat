@echo off
setlocal EnableExtensions
cd /d "%~dp0"
set "PYCOMMAND="
py -3.11 -c "import sys; assert sys.version_info >= (3,11)" >nul 2>nul
if not errorlevel 1 set "PYCOMMAND=py -3.11"
if not defined PYCOMMAND (
    python -c "import sys; assert sys.version_info >= (3,11)" >nul 2>nul
    if not errorlevel 1 set "PYCOMMAND=python"
)
if not defined PYCOMMAND (
    echo Python 3.11+ not found. Install Python with the official Windows launcher.
    echo No production dependency or model data was changed.
    pause
    exit /b 1
)
set "VENV=%TEMP%\jaal_stage4_candidate_3e935585_311"
if not exist "%VENV%\Scripts\python.exe" (
    %PYCOMMAND% -m venv "%VENV%"
    if errorlevel 1 goto :failed
)
set "PYTHON=%VENV%\Scripts\python.exe"
set "PYTHONUTF8=1"
set "JAAL_STAGE4_COMMUNITY_CANDIDATE=1"
echo.
echo Installing isolated graph-only dependencies and exact reviewed candidate...
"%PYTHON%" -m pip install --disable-pip-version-check dash dash-bootstrap-components dash-cytoscape jaal pandas psutil GPUtil numpy opencc-python-reimplemented scipy setproctitle version-parser colorama tqdm pymongo elasticsearch pytz
if errorlevel 1 goto :failed
"%PYTHON%" -m pip install --disable-pip-version-check "jaal-topology-viewer @ git+https://github.com/hun186/jaal-topology-viewer.git@d8ece317dee554d3e286f4a92c6f8ff52a39266b"
if errorlevel 1 goto :failed
echo.
echo Candidate provenance check...
"%PYTHON%" -c "from BertScript.jaal_original_mount import _community_candidate_enabled; assert _community_candidate_enabled()"
if errorlevel 1 goto :failed
echo.
echo Launching Stage 4 candidate desktop acceptance on 127.0.0.1:8098...
"%PYTHON%" tools\stage4_candidate_desktop_acceptance.py --port 8098
set "RESULT=%ERRORLEVEL%"
pause
exit /b %RESULT%
:failed
echo.
echo Candidate-only setup failed. Production requirements and model data are unchanged.
pause
exit /b 1
