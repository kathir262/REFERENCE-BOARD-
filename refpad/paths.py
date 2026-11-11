"""Where RefPad keeps its files.

Program files live wherever RefPad was installed (the updater replaces that folder).
Your board, practice list and settings live separately in %LOCALAPPDATA%\\RefPad, so updates never touch them.
"""
import os
import sys
from pathlib import Path


def _data_dir() -> Path:
    override = os.environ.get("REFPAD_DATA_DIR")  # used by the tests
    if override:
        d = Path(override)
    else:
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        d = Path(base) / "RefPad"
    d.mkdir(parents=True, exist_ok=True)
    return d


DATA = _data_dir()
BOARD = DATA / "board"
IMG = BOARD / "img"
STATE_FILE = BOARD / "state.json"
SETTINGS_FILE = DATA / "settings.json"
UPDATES = DATA / "updates"
IMG.mkdir(parents=True, exist_ok=True)


def is_frozen() -> bool:
    """True when running as the packaged RefPad.exe, False when running from source."""
    return bool(getattr(sys, "frozen", False))


def install_dir() -> Path:
    """Folder that holds RefPad.exe (only meaningful when frozen)."""
    return Path(sys.executable).resolve().parent


def resource(rel: str) -> Path:
    """A file shipped with the app (icon, privacy policy)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / rel
