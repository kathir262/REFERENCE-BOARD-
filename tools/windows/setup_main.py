"""RefPad Setup: one file to double-click. Installs RefPad for this Windows user (no administrator rights):

- puts the app in %LOCALAPPDATA%\\Programs\\RefPad (replacing an older copy, keeping your boards and settings),
- adds Start menu and desktop shortcuts and an entry in Settings > Apps,
- lets you double-click .refpad board files to open them in RefPad,
- then starts RefPad.

Built by tools/build_windows.py, which packs the release zip inside this installer.
"""
import ctypes
import os
import shutil
import subprocess
import sys
import time
import winreg
import zipfile
from pathlib import Path

TITLE = "RefPad Setup"
MB_OK, MB_OKCANCEL, MB_RETRYCANCEL = 0x0, 0x1, 0x5
ICON_INFO, ICON_WARN, ICON_ERROR = 0x40, 0x30, 0x10
IDOK, IDRETRY = 1, 4
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
UNINSTALL_KEY = "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\RefPad"
CLASSES = "Software\\Classes"


def ask(text: str, flags: int) -> int:
    return ctypes.windll.user32.MessageBoxW(None, text, TITLE, flags | 0x00010000)   # MB_SETFOREGROUND


def bundled(name: str) -> Path:
    return Path(getattr(sys, "_MEIPASS", Path(__file__).parent)) / name


def refpad_running() -> bool:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq RefPad.exe", "/NH"], capture_output=True, text=True,
                         creationflags=NO_WINDOW).stdout
    return "RefPad.exe" in out


def remove_tree(p: Path):
    if p.exists():
        shutil.rmtree(p, ignore_errors=True)


def extract(zip_path: Path, into: Path) -> Path:
    remove_tree(into)
    into.mkdir(parents=True)
    root = into.resolve()
    with zipfile.ZipFile(zip_path) as z:
        for m in z.infolist():
            target = (into / m.filename).resolve()
            if root not in target.parents and target != root:
                raise RuntimeError("The installer is damaged (unsafe file names).")
        z.extractall(into)
    app = into / "RefPad"
    if not (app / "RefPad.exe").exists():
        raise RuntimeError("The installer is damaged (RefPad.exe is missing).")
    return app


def swap_in(new: Path, dest: Path):
    """Replaces the installed folder; puts the old one back if anything fails."""
    old = dest.parent / "RefPad.old"
    remove_tree(old)
    if dest.exists():
        for _ in range(20):
            try:
                dest.rename(old)
                break
            except OSError:
                time.sleep(0.5)
        else:
            raise RuntimeError("The RefPad folder is in use. Close RefPad (and any File Explorer window showing "
                               "that folder), then run Setup again.")
    try:
        new.rename(dest)
    except OSError:
        if old.exists() and not dest.exists():
            old.rename(dest)
        raise
    remove_tree(old)


def _ps_quote(s) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def shortcuts(dest: Path, folders=None):
    """Start menu and desktop shortcuts (or into `folders`, used by the tests)."""
    where = ", ".join(_ps_quote(f) for f in folders) if folders else \
        "[Environment]::GetFolderPath('Programs'), [Environment]::GetFolderPath('Desktop')"
    ps = ("$ws = New-Object -ComObject WScript.Shell; "
          f"foreach ($d in @({where})) {{ "
          "$l = $ws.CreateShortcut((Join-Path $d 'RefPad.lnk')); "
          f"$l.TargetPath = {_ps_quote(dest / 'RefPad.exe')}; $l.WorkingDirectory = {_ps_quote(dest)}; "
          "$l.Description = 'Reference board, gesture practice and PDF reader'; $l.Save() }")
    subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps],
                   creationflags=NO_WINDOW, check=False)


def register(dest: Path, version: str):
    exe = str(dest / "RefPad.exe")
    size_kb = sum(f.stat().st_size for f in dest.rglob("*") if f.is_file()) // 1024
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as k:
        for name, value in (("DisplayName", "RefPad"), ("DisplayVersion", version), ("Publisher", "RefPad"),
                            ("DisplayIcon", exe), ("InstallLocation", str(dest)),
                            ("UninstallString", f'"{dest / "Uninstall RefPad.cmd"}"')):
            winreg.SetValueEx(k, name, 0, winreg.REG_SZ, value)
        for name, value in (("NoModify", 1), ("NoRepair", 1), ("EstimatedSize", size_kb)):
            winreg.SetValueEx(k, name, 0, winreg.REG_DWORD, value)
    # Double-clicking a .refpad board file opens it in RefPad.
    for sub, value in ((".refpad", "RefPad.Board"), ("RefPad.Board", "RefPad board"),
                       ("RefPad.Board\\DefaultIcon", f'"{exe}",0'),
                       ("RefPad.Board\\shell\\open\\command", f'"{exe}" "%1"')):
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, CLASSES + "\\" + sub) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, value)
    ctypes.windll.shell32.SHChangeNotify(0x08000000, 0, None, None)   # tell Explorer about the file type


def main():
    version = bundled("version.txt").read_text(encoding="utf-8").strip()
    dest = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData/Local") / "Programs" / "RefPad"
    if ask(f"Install RefPad {version} on this PC?\n\n"
           f"It goes in {dest}, with shortcuts in the Start menu and on the desktop. "
           "Your boards and settings are kept.", MB_OKCANCEL | ICON_INFO) != IDOK:
        return 0
    while refpad_running():
        if ask("RefPad is open. Please close it, then click Retry.", MB_RETRYCANCEL | ICON_WARN) != IDRETRY:
            return 0
    staging = dest.parent / "RefPad.setup"
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        new = extract(bundled("RefPad.zip"), staging)
        swap_in(new, dest)
        shortcuts(dest)
        register(dest, version)
    except Exception as e:
        ask(f"RefPad couldn't be installed.\n\n{e}", MB_OK | ICON_ERROR)
        return 1
    finally:
        remove_tree(staging)
    subprocess.Popen([str(dest / "RefPad.exe")], cwd=str(dest), close_fds=True,
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
