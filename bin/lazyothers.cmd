@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0lazyothers.ps1" %*
exit /b %ERRORLEVEL%
