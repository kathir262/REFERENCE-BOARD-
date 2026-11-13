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


_store_app = None


def is_store_app() -> bool:
    """True when RefPad runs as the Microsoft Store (MSIX) package. Store copies are updated by the Store."""
    global _store_app
    if _store_app is None:
        _store_app = False
        if os.name == "nt" and is_frozen():
            try:
                import ctypes
                length = ctypes.c_uint32(0)
                # 15700 = APPMODEL_ERROR_NO_PACKAGE: a normal (unpackaged) program.
                rc = ctypes.windll.kernel32.GetCurrentPackageFullName(ctypes.byref(length), None)
                _store_app = rc != 15700
            except (AttributeError, OSError):
                _store_app = False
    return _store_app


def install_dir() -> Path:
    """Folder that holds RefPad.exe (only meaningful when frozen)."""
    return Path(sys.executable).resolve().parent


def resource(rel: str) -> Path:
    """A file shipped with the app (icon, privacy policy)."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / rel
