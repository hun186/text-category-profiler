@echo off
setlocal
cd /d "%~dp0"
REM Historical Stage 4 read-only inspection, not the official pipeline.
REM Default port 8060 avoids an already-running Stage 4 on port 8059.
python BertScript\Test_result_Vis.py --history-preview --workpool WorkPool -p 8060 %*
if errorlevel 1 (
    echo.
    echo Stage 4 history preview failed. Check dependencies and WorkPool path.
    pause
)
