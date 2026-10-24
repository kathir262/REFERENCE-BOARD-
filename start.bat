@echo off
cd /d "%~dp0"
py -3.12 run.py %*
if errorlevel 1 (
    echo.
    echo Failed to start RefPad with Python 3.12. Trying default python...
    python run.py %*
)
pause
