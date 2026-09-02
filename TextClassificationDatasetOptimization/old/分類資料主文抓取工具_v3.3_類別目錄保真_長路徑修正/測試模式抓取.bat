@echo off
call "%~dp0run_scraper.bat" "%~1" test
exit /b %ERRORLEVEL%
