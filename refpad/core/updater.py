"""Updates RefPad for Windows from GitHub Releases.

1. check(): one HTTPS request to api.github.com lists the releases and finds the newest
   "RefPad-<version>-windows-x64.zip" that comes with a matching ".sha256" checksum file.
2. download(): downloads the zip from GitHub, checks its size and SHA-256 checksum, and unpacks it
   next to the installed copy (never anywhere else).
3. install_and_restart(): a small PowerShell script waits for RefPad to close, swaps the folders, and starts
   the new version. If anything goes wrong it puts the old version back, so you are never left without RefPad.

Nothing about you or your files is sent; GitHub only sees an ordinary web request.
Your board and settings live in %LOCALAPPDATA%\\RefPad, outside the program folder, so updates never touch them.
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from refpad import GITHUB_REPO, __version__, paths

API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases?per_page=20"
RELEASES_PAGE = f"https://github.com/{GITHUB_REPO}/releases"
ASSET_RE = re.compile(r"^RefPad-(\d+)\.(\d+)\.(\d+)-windows-x64\.zip$", re.IGNORECASE)
ALLOWED_HOSTS = ("github.com", "api.github.com", "objects.githubusercontent.com",
                 "release-assets.githubusercontent.com", "github-releases.githubusercontent.com")
USER_AGENT = f"RefPad-Updater/{__version__}"
EXE_NAME = "RefPad.exe"
MAX_ZIP_BYTES = 400 * 1024 * 1024


def parse_version(text: str) -> tuple:
    m = re.match(r"^\s*v?(\d+)\.(\d+)(?:\.(\d+))?", text or "")
    return (int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)) if m else (0, 0, 0)


def version_text(v: tuple) -> str:
    return ".".join(str(x) for x in v)


@dataclass
class Release:
    version: tuple
    notes: str
    zip_url: str
    zip_size: int
    sha_url: str
    page_url: str

    @property
    def version_text(self) -> str:
        return version_text(self.version)


class UpdateError(Exception):
    pass


def _check_host(url: str):
    u = urllib.parse.urlparse(url)
    host = (u.hostname or "").lower()
    if u.scheme != "https" or not any(host == h or host.endswith("." + h) for h in ALLOWED_HOSTS):
        raise UpdateError("The update came from an unexpected address, so it was not used.")


def _open(url: str, timeout: float = 15):
    _check_host(url)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/vnd.github+json"})
    resp = urllib.request.urlopen(req, timeout=timeout)
    _check_host(resp.geturl())   # after redirects
    return resp


def pick_release(releases: list, current: tuple):
    """The newest release newer than `current` that has a Windows zip and its checksum (or None)."""
    best = None
    for rel in releases if isinstance(releases, list) else []:
        if not isinstance(rel, dict) or rel.get("draft") or rel.get("prerelease"):
            continue
        assets = {a.get("name", ""): a for a in rel.get("assets", []) if isinstance(a, dict)}
        for name, asset in assets.items():
            m = ASSET_RE.match(name)
            sha = assets.get(name + ".sha256")
            if not m or sha is None:
                continue   # never offer an update that can't be verified
            v = tuple(int(x) for x in m.groups())
            if v > current and (best is None or v > best.version):
                best = Release(v, rel.get("body") or "", asset.get("browser_download_url", ""),
                               int(asset.get("size") or 0), sha.get("browser_download_url", ""),
                               rel.get("html_url") or RELEASES_PAGE)
    return best


def check():
    """Newest available update, or None when RefPad is up to date. Raises UpdateError when offline."""
    try:
        with _open(API_URL) as resp:
            data = json.loads(resp.read(4 * 1024 * 1024).decode("utf-8"))
    except UpdateError:
        raise
    except Exception as e:
        raise UpdateError("Couldn't reach GitHub. Check your internet connection.") from e
    return pick_release(data, parse_version(__version__))


# ----------------------------------------------------------------------------- installing

def can_self_update() -> bool:
    """True when running the packaged app from a folder we may replace."""
    if not paths.is_frozen() or paths.is_store_app():
        return False
    app = paths.install_dir()
    if not (app / EXE_NAME).exists():
        return False
    # The update replaces the whole folder, so only do it when the folder holds nothing but RefPad
    # (never e.g. a Desktop or Downloads folder that RefPad was unpacked into directly).
    ours = {EXE_NAME.lower(), "_internal", "install refpad.cmd", "uninstall refpad.cmd"}
    try:
        if any(p.name.lower() not in ours for p in app.iterdir()):
            return False
    except OSError:
        return False
    try:
        with tempfile.TemporaryFile(dir=app.parent):
            pass
        with tempfile.TemporaryFile(dir=app):
            pass
        return True
    except OSError:
        return False


def _staging() -> Path:
    app = paths.install_dir()
    return app.parent / (app.name + ".update")


def _expected_sha(text: str) -> str:
    m = re.search(r"\b([0-9a-fA-F]{64})\b", text)
    if not m:
        raise UpdateError("The update's checksum file is not valid.")
    return m.group(1).lower()


def download(rel: Release, progress=None, cancelled=lambda: False) -> Path:
    """Downloads and verifies the update; returns the unpacked new program folder. Runs on a worker thread."""
    if rel.zip_size and rel.zip_size > MAX_ZIP_BYTES:
        raise UpdateError("The update is unexpectedly large, so it was not downloaded.")
    try:
        with _open(rel.sha_url) as resp:
            expected = _expected_sha(resp.read(4096).decode("utf-8", "replace"))
        paths.UPDATES.mkdir(parents=True, exist_ok=True)
        zip_path = paths.UPDATES / f"RefPad-{rel.version_text}.zip"
        digest = hashlib.sha256()
        got = 0
        with _open(rel.zip_url, timeout=30) as resp, open(zip_path, "wb") as out:
            total = int(resp.headers.get("Content-Length") or rel.zip_size or 0)
            while True:
                if cancelled():
                    raise UpdateError("Download cancelled.")
                chunk = resp.read(256 * 1024)
                if not chunk:
                    break
                got += len(chunk)
                if got > MAX_ZIP_BYTES:
                    raise UpdateError("The update is unexpectedly large, so it was not downloaded.")
                digest.update(chunk)
                out.write(chunk)
                if progress:
                    progress(got, total)
    except UpdateError:
        raise
    except Exception as e:
        raise UpdateError("The download didn't finish. Check your internet connection and try again.") from e

    if rel.zip_size and got != rel.zip_size:
        zip_path.unlink(missing_ok=True)
        raise UpdateError("The download is incomplete. Please try again.")
    if digest.hexdigest() != expected:
        zip_path.unlink(missing_ok=True)
        raise UpdateError("The download doesn't match its checksum, so it was not installed.")

    staging = _staging()
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    root = staging.resolve()
    try:
        with zipfile.ZipFile(zip_path) as z:
            for member in z.infolist():
                target = (staging / member.filename).resolve()
                if root not in target.parents and target != root:
                    raise UpdateError("The update contains unsafe file names, so it was not installed.")
            z.extractall(staging)
    except zipfile.BadZipFile as e:
        shutil.rmtree(staging, ignore_errors=True)
        raise UpdateError("The update file is damaged.") from e
    finally:
        zip_path.unlink(missing_ok=True)

    candidates = [p.parent for p in staging.rglob(EXE_NAME)]
    if len(candidates) != 1 or not (candidates[0] / "_internal").is_dir():
        shutil.rmtree(staging, ignore_errors=True)
        raise UpdateError("The update doesn't contain RefPad.exe.")
    return candidates[0]


def _ps(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def install_and_restart(new_dir: Path):
    """Starts the swap script; the caller must quit RefPad straight after."""
    app = paths.install_dir()
    old = app.parent / (app.name + ".old")
    paths.UPDATES.mkdir(parents=True, exist_ok=True)
    script = paths.UPDATES / "apply-update.ps1"
    log = paths.UPDATES / "update.log"
    script.write_text(f"""# Written by RefPad: replaces the program folder once RefPad has closed.
$ErrorActionPreference = 'Stop'
$app = {_ps(app)}
$new = {_ps(new_dir)}
$old = {_ps(old)}
$staging = {_ps(_staging())}
$log = {_ps(log)}
function Log($m) {{ Add-Content -LiteralPath $log -Value ((Get-Date -Format s) + ' ' + $m) }}
Log 'waiting for RefPad to close'
Wait-Process -Id {os.getpid()} -Timeout 60 -ErrorAction SilentlyContinue
Start-Sleep -Milliseconds 400
$moved = $false
for ($i = 0; $i -lt 30 -and -not $moved; $i++) {{
    try {{
        if (Test-Path -LiteralPath $old) {{ Remove-Item -LiteralPath $old -Recurse -Force }}
        Rename-Item -LiteralPath $app -NewName (Split-Path $old -Leaf)
        $moved = $true
    }} catch {{ Start-Sleep -Milliseconds 500 }}
}}
$ok = $false
if ($moved) {{
    try {{ Move-Item -LiteralPath $new -Destination $app; $ok = $true }}
    catch {{ Log ('move failed: ' + $_); Rename-Item -LiteralPath $old -NewName (Split-Path $app -Leaf) }}
}} else {{ Log 'program folder is in use' }}
$flag = '--update-failed'
if ($ok) {{ $flag = '--updated' }}
Start-Process -FilePath (Join-Path $app {_ps(EXE_NAME)}) -ArgumentList $flag
if ($ok) {{
    Start-Sleep -Seconds 3
    Remove-Item -LiteralPath $old -Recurse -Force -ErrorAction SilentlyContinue
}}
Remove-Item -LiteralPath $staging -Recurse -Force -ErrorAction SilentlyContinue
""", encoding="utf-8-sig")
    cmd = ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(script)]
    # A hidden console (not a detached process: PowerShell may not start without one), in its own process
    # group, and outside any job RefPad runs in, so it keeps going after RefPad has closed.
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    breakaway = 0x01000000   # CREATE_BREAKAWAY_FROM_JOB
    kw = dict(cwd=str(paths.UPDATES), close_fds=True, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
              stderr=subprocess.DEVNULL)
    try:
        subprocess.Popen(cmd, creationflags=flags | breakaway, **kw)
    except OSError:   # the job doesn't allow breaking away
        subprocess.Popen(cmd, creationflags=flags, **kw)


def cleanup_leftovers():
    """Removes folders left by an interrupted update (run at start-up)."""
    if not paths.is_frozen():
        return
    app = paths.install_dir()
    for leftover in (app.parent / (app.name + ".old"), app.parent / (app.name + ".update")):
        if leftover.exists():
            shutil.rmtree(leftover, ignore_errors=True)


def due_for_check(last_check: float) -> bool:
    return time.time() - (last_check or 0) > 20 * 3600


def refresh_install_record():
    """Keeps "Settings > Apps" showing the right version after an in-app update."""
    if not paths.is_frozen() or os.name != "nt":
        return
    try:
        import winreg
        key = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\RefPad"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_READ | winreg.KEY_SET_VALUE) as k:
            location, _ = winreg.QueryValueEx(k, "InstallLocation")
            if os.path.normcase(os.path.abspath(location)) == os.path.normcase(str(paths.install_dir())):
                winreg.SetValueEx(k, "DisplayVersion", 0, winreg.REG_SZ, __version__)
    except OSError:
        pass
