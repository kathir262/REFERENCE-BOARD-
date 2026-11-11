@echo off
setlocal
rem Installs RefPad for this Windows user (no administrator rights needed):
rem copies it to %LOCALAPPDATA%\Programs\RefPad, adds Start menu and desktop shortcuts,
rem and an entry in Settings > Apps so it can be uninstalled like any other app.

set "SRC=%~dp0"
set "DEST=%LOCALAPPDATA%\Programs\RefPad"

if not exist "%SRC%RefPad.exe" (
    echo RefPad.exe was not found next to this file. Unzip the whole download first.
    pause
    exit /b 1
)
tasklist /FI "IMAGENAME eq RefPad.exe" 2>nul | find /I "RefPad.exe" >nul
if not errorlevel 1 (
    echo Please close RefPad first, then run this again.
    pause
    exit /b 1
)

if /I "%SRC%"=="%DEST%\" goto shortcuts
echo Installing RefPad to %DEST% ...
robocopy "%SRC%." "%DEST%" /MIR /NFL /NDL /NJH /NJS /NP >nul
if errorlevel 8 (
    echo Copying failed. Is the disk full?
    pause
    exit /b 1
)

:shortcuts
powershell -NoProfile -ExecutionPolicy Bypass -Command "$ws = New-Object -ComObject WScript.Shell; $app = Join-Path $env:LOCALAPPDATA 'Programs\RefPad'; foreach ($dir in @([Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop'))) { $l = $ws.CreateShortcut((Join-Path $dir 'RefPad.lnk')); $l.TargetPath = Join-Path $app 'RefPad.exe'; $l.WorkingDirectory = $app; $l.Description = 'Reference board, gesture practice and PDF reader'; $l.Save() }"

set "KEY=HKCU\Software\Microsoft\Windows\CurrentVersion\Uninstall\RefPad"
reg add "%KEY%" /v DisplayName /d "RefPad" /f >nul
reg add "%KEY%" /v DisplayIcon /d "%DEST%\RefPad.exe" /f >nul
reg add "%KEY%" /v Publisher /d "RefPad" /f >nul
reg add "%KEY%" /v InstallLocation /d "%DEST%" /f >nul
reg add "%KEY%" /v UninstallString /d "\"%DEST%\Uninstall RefPad.cmd\"" /f >nul
reg add "%KEY%" /v NoModify /t REG_DWORD /d 1 /f >nul
reg add "%KEY%" /v NoRepair /t REG_DWORD /d 1 /f >nul

echo RefPad is installed. Starting it now...
start "" "%DEST%\RefPad.exe"
