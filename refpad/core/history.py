"""Practice history: poses drawn and minutes practised per day (kept on this PC only)."""
import json
import os
from datetime import date, timedelta

from refpad import paths

FILE = paths.DATA / "history.json"


def _load() -> dict:
    try:
        with open(FILE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(data: dict):
    tmp = FILE.with_suffix(".tmp")
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, FILE)
    except OSError:
        pass


def add(seconds: float, day: date = None):
    """One pose practised for `seconds`."""
    data = _load()
    d = data.setdefault((day or date.today()).isoformat(), {"poses": 0, "seconds": 0})
    d["poses"] += 1
    d["seconds"] += round(seconds)
    _save(data)


def clear():
    _save({})


def summary(today: date = None) -> dict:
    today = today or date.today()
    data = _load()

    def day(n):
        return data.get((today - timedelta(days=n)).isoformat(), {"poses": 0, "seconds": 0})

    week = [day(n) for n in range(7)]
    streak = 0
    n = 0 if day(0)["poses"] else 1   # today doesn't break the streak until it's over
    while day(n)["poses"]:
        streak += 1
        n += 1
    return {
        "today": day(0),
        "week": {"poses": sum(d["poses"] for d in week), "seconds": sum(d["seconds"] for d in week)},
        "total": {"poses": sum(d.get("poses", 0) for d in data.values()),
                  "seconds": sum(d.get("seconds", 0) for d in data.values())},
        "streak": streak,
        "days": [((today - timedelta(days=n)), day(n)) for n in range(13, -1, -1)],
    }
