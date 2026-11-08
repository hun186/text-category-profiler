@echo off
setlocal
cd /d "%~dp0"
rem Stage 4 read-only preflight, defaults to full Stage 4 PytorchMMBERT.
rem Examples:
rem   run-stage4-doctor.bat
rem   run-stage4-doctor.bat --mode viewer --probe-jaal
rem   run-stage4-doctor.bat --mode full --model-type PytorchXLM --workpool D:\WorkPool
python BertScript\Test_result_Vis.py --doctor %*
set "RC=%ERRORLEVEL%"
if not "%RC%"=="0" echo [Stage 4 doctor] FAIL - see the reported checks above.
exit /b %RC%
