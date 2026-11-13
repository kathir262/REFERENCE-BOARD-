"""The practice countdown: each pose stays up for the chosen time, then the next one shows."""
import math
import re
import struct
import wave

from PySide6.QtCore import QElapsedTimer, QObject, QTimer, Signal

from refpad import paths
from refpad.settings import settings

TICK_MS = 50


def interval_label(sec: int) -> str:
    return f"{sec} sec" if sec < 60 else f"{sec // 60} min"


def clock(ms: int) -> str:
    s = max(0, math.ceil(ms / 1000))
    return f"{s // 60}:{s % 60:02d}"


# Ready-made classes: (name, plan)
CLASSES = (
    ("Warm-up · 10 min", "10x30s, 5x1m"),
    ("Class · 30 min", "10x30s, 5x1m, 5x2m, 2x5m"),
    ("Class · 60 min", "10x30s, 5x1m, 5x2m, 3x5m, 1x10m, 1x15m"),
)


def parse_plan(text: str):
    """'10x30s, 5x1m' -> [30]*10 + [60]*5 (seconds per pose). None if it can't be read."""
    plan = []
    for part in re.split(r"[,;+]+", text or ""):
        part = part.strip()
        if not part:
            continue
        m = re.fullmatch(r"(\d+)\s*[x×*]\s*(\d+(?:[.,]\d+)?)\s*(s|sec|secs|seconds?|m|min|mins|minutes?)?", part, re.I)
        if not m:
            return None
        count = int(m.group(1))
        amount = float(m.group(2).replace(",", "."))
        unit = (m.group(3) or ("s" if amount > 10 else "m")).lower()
        sec = round(amount * 60) if unit.startswith("m") else round(amount)
        if not (1 <= count <= 200 and 5 <= sec <= 3600):
            return None
        plan += [sec] * count
    return plan or None


def plan_text(plan) -> str:
    out, i = [], 0
    while i < len(plan):
        j = i
        while j < len(plan) and plan[j] == plan[i]:
            j += 1
        sec = plan[i]
        out.append(f"{j - i}×" + (f"{sec}s" if sec < 60 or sec % 60 else f"{sec // 60}m"))
        i = j
    return ", ".join(out)


class PracticeTimer(QObject):
    tick = Signal()                 # remaining time changed
    runningChanged = Signal(bool)
    phaseChanged = Signal()         # memory mode: the pose was hidden or shown again
    classChanged = Signal()         # a class started, moved on or ended

    def __init__(self, state):
        super().__init__()
        self.state = state
        self.running = False
        self.plan = None            # seconds per pose while a class runs, else None
        self.plan_pos = 0
        self.plan_name = ""
        self.memory = bool(settings["memory_mode"])
        self.phase = "look"         # memory mode: "look" at the pose, then "draw" it from memory
        self._pose_ms = 0           # time actually spent on the pose that is showing
        self._pose_total = 0
        self.remaining_ms = self.total_ms
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._on_tick)
        state.poseChanged.connect(self._on_pose_changed)
        state.practiceChanged.connect(self._on_list_changed)

    @property
    def total_ms(self) -> int:
        if self.plan:
            return self.plan[min(self.plan_pos, len(self.plan) - 1)] * 1000
        return self.state.interval * 1000

    @property
    def progress(self) -> float:
        """0 at the start of a pose, 1 when it is over."""
        return 1 - self.remaining_ms / max(1, self.total_ms)

    @property
    def hidden(self) -> bool:
        """Memory mode: the pose is covered while you draw it from memory."""
        return self.memory and self.phase == "draw"

    def start(self):
        if self.running or not self.state.practice:
            return
        self.running = True
        self._clock.start()
        self._timer.start()
        self.runningChanged.emit(True)

    def pause(self):
        if not self.running:
            return
        self._consume()
        self.running = False
        self._timer.stop()
        self.runningChanged.emit(False)
        self.tick.emit()

    def toggle(self):
        self.pause() if self.running else self.start()

    def restart(self):
        """Full time again for the pose that is showing."""
        self.remaining_ms = self.total_ms
        self._pose_total = self.total_ms
        if self.running:
            self._clock.restart()
        self.tick.emit()

    def set_interval(self, sec: int):
        self.state.interval = sec
        self.state.schedule_save()
        if not self.plan:
            self.restart()

    def set_memory(self, on: bool):
        self.memory = on
        settings["memory_mode"] = on
        if not on and self.phase == "draw":
            self.phase = "look"
            self.phaseChanged.emit()

    # classes ------------------------------------------------------------------

    def start_class(self, plan, name: str):
        self.plan, self.plan_pos, self.plan_name = list(plan), 0, name
        self.phase = "look"
        self.phaseChanged.emit()
        self.restart()
        self.classChanged.emit()
        self.start()

    def stop_class(self):
        if self.plan is None:
            return
        self.plan = None
        self.restart()
        self.classChanged.emit()

    def advance(self):
        """Next pose (when the time is up, or the Next button): also moves a class on."""
        if self.plan is not None:
            self.plan_pos += 1
            if self.plan_pos >= len(self.plan):
                return self._finish_class()
            self.classChanged.emit()
        before = self.state.practice_index
        self.state.next_pose()            # emits poseChanged -> _on_pose_changed
        if self.state.practice_index == before:
            self._on_pose_changed()       # only one pose: start it again

    def _finish_class(self):
        poses, minutes = len(self.plan), sum(self.plan) / 60
        name = self.plan_name
        self._log_pose()
        self.pause()
        self.plan = None
        self.phase = "look"
        self.phaseChanged.emit()
        self.restart()
        self.classChanged.emit()
        self.state.notify(f"{name or 'Class'} finished · {poses} poses · {minutes:g} min. Well done!")

    # internals ------------------------------------------------------------------

    def _log_pose(self):
        from refpad.core import history
        if self._pose_ms >= max(5000, 0.5 * max(1, self._pose_total)):
            history.add(self._pose_ms / 1000)
        self._pose_ms = 0

    def _on_pose_changed(self):
        self._log_pose()
        if self.phase != "look":
            self.phase = "look"
            self.phaseChanged.emit()
        self.restart()

    def _on_list_changed(self):
        if not self.state.practice:
            self.pause()
            self.stop_class()
            self.restart()

    def _consume(self):
        dt = self._clock.restart()
        self.remaining_ms -= dt
        self._pose_ms += dt

    def _on_tick(self):
        self._consume()
        if self.remaining_ms <= 0:
            if settings["chime"]:
                play_chime()
            if self.memory and self.phase == "look":
                self.phase = "draw"   # hide the pose: now draw it from memory, for the same time
                self.remaining_ms = self.total_ms
                self.phaseChanged.emit()
            else:
                self.advance()
        self.tick.emit()


_chime_file = None


def play_chime():
    """A soft two-note chime (generated once, played without blocking)."""
    global _chime_file
    try:
        import winsound
    except ImportError:
        return
    try:
        if _chime_file is None:
            _chime_file = paths.DATA / "chime.wav"
            if not _chime_file.exists():
                _write_chime(_chime_file)
        winsound.PlaySound(str(_chime_file), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
    except Exception:
        pass


def _write_chime(path):
    rate = 22050
    frames = bytearray()
    total = int(rate * 0.7)
    for i in range(total):
        t = i / rate
        v = 0.0
        for freq, start in ((880.0, 0.0), (1318.5, 0.12)):
            if t >= start:
                tt = t - start
                v += math.sin(2 * math.pi * freq * tt) * math.exp(-tt * 7) * 0.22
        frames += struct.pack("<h", int(max(-1, min(1, v)) * 32767))
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
