@echo off
setlocal EnableDelayedExpansion
echo ========================================================
echo  Reference Board - One-Click Desktop Installation
echo ========================================================
echo.

set "TARGET_DIR=%LOCALAPPDATA%\Programs\ReferenceBoard"
if not exist "%TARGET_DIR%" mkdir "%TARGET_DIR%"

if exist "dist\ReferenceBoard.exe" (
    echo Installing ReferenceBoard.exe to %TARGET_DIR%...
    copy /Y "dist\ReferenceBoard.exe" "%TARGET_DIR%\ReferenceBoard.exe" >nul
) else (
    echo Standalone executable not found in dist. Launching via Python...
    start "" py -3.12 run.py
    exit /b 0
)

echo Creating Desktop and Start Menu Shortcuts...
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $d = [Environment]::GetFolderPath('Desktop'); $s1 = $ws.CreateShortcut(\"$d\Reference Board.lnk\"); $s1.TargetPath = \"$env:LOCALAPPDATA\Programs\ReferenceBoard\ReferenceBoard.exe\"; $s1.Save(); $p = [Environment]::GetFolderPath('Programs'); $s2 = $ws.CreateShortcut(\"$p\Reference Board.lnk\"); $s2.TargetPath = \"$env:LOCALAPPDATA\Programs\ReferenceBoard\ReferenceBoard.exe\"; $s2.Save()"

echo.
echo ========================================================
echo  Installation Complete!
echo  Desktop shortcut created. Launching Reference Board...
echo ========================================================
echo.
start "" "%TARGET_DIR%\ReferenceBoard.exe"
