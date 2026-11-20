@echo off
setlocal
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0lazyforensic.ps1" %*
exit /b %ERRORLEVEL%
