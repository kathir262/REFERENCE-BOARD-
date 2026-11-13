"""Small JSON settings file (window placement, timer interval, update preferences)."""
import json
import os

from refpad import paths

DEFAULTS = {
    "geometry": None,          # [x, y, w, h] of the normal window
    "maximized": False,
    "float_geometry": None,    # [x, y, w, h] of the small always-on-top window
    "float_opacity": 1.0,
    "float_mode": False,
    "chime": True,             # soft sound when the pose changes
    "auto_update": True,       # check GitHub for a new version at most once a day
    "last_update_check": 0.0,
    "skip_version": "",
    "recent_boards": [],       # board files, most recent first
    "board_bg": "dark",        # board and practice background: dark, grey or light
    "class_plan": "",          # last practice class, e.g. "10x30s, 5x1m"
    "memory_mode": False,      # practice: draw each pose from memory after it hides
}


class Settings:
    def __init__(self):
        self._data = dict(DEFAULTS)
        try:
            with open(paths.SETTINGS_FILE, encoding="utf-8") as f:
                loaded = json.load(f)
            if isinstance(loaded, dict):
                self._data.update({k: v for k, v in loaded.items() if k in DEFAULTS})
        except (OSError, ValueError):
            pass

    def __getitem__(self, key):
        return self._data.get(key, DEFAULTS.get(key))

    def __setitem__(self, key, value):
        if self._data.get(key) != value:
            self._data[key] = value
            self.save()

    def save(self):
        tmp = paths.SETTINGS_FILE.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=1)
            os.replace(tmp, paths.SETTINGS_FILE)
        except OSError:
            pass


settings = Settings()
