@echo off
setlocal
rem Removes RefPad from this PC. Only RefPad's own files are deleted.
rem Your board, practice list and settings stay in %LOCALAPPDATA%\RefPad; delete that folder too if you want them gone.

set "APP=%~dp0"
if not exist "%APP%RefPad.exe" (
    echo This file must stay in the RefPad folder.
    pause
    exit /b 1
)
tasklist /FI "IMAGENAME eq RefPad.exe" 2>nul | find /I "RefPad.exe" >nul
if not errorlevel 1 (
    echo Please close RefPad first, then run this again.
    pause
    exit /b 1
)

echo Removing RefPad...
powershell -NoProfile -Command "foreach ($dir in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop'))) { Remove-Item -LiteralPath (Join-Path $dir 'RefPad.lnk') -ErrorAction SilentlyContinue }"
reg delete "HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\RefPad" /f >nul 2>&1
reg delete "HKCU\Software\Classes\RefPad.Board" /f >nul 2>&1
reg query "HKCU\Software\Classes\.refpad" /ve 2>nul | find "RefPad.Board" >nul && reg delete "HKCU\Software\Classes\.refpad" /f >nul 2>&1
rmdir /s /q "%APP%_internal"
del /q "%APP%RefPad.exe" "%APP%Install RefPad.cmd" 2>nul

rem This script removes itself and then the folder, but only if the folder is empty.
start "" /min powershell -NoProfile -WindowStyle Hidden -Command "Start-Sleep -Seconds 2; Remove-Item -LiteralPath (Join-Path '%APP%' 'Uninstall RefPad.cmd') -ErrorAction SilentlyContinue; try { [IO.Directory]::Delete('%APP%'.TrimEnd('\'), $false) } catch {}"
echo RefPad has been removed. Your board is still in %LOCALAPPDATA%\RefPad.
