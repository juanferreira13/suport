@echo off
cd /d "%~dp0"
"%~dp0..\..\sistema\python\python.exe" main.py %*
pause
