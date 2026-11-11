"""The practice countdown: each pose stays up for the chosen time, then the next one shows."""
import math
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


class PracticeTimer(QObject):
    tick = Signal()                 # remaining time changed
    runningChanged = Signal(bool)

    def __init__(self, state):
        super().__init__()
        self.state = state
        self.running = False
        self.remaining_ms = state.interval * 1000
        self._clock = QElapsedTimer()
        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._on_tick)
        state.poseChanged.connect(self.restart)
        state.practiceChanged.connect(self._on_list_changed)

    @property
    def total_ms(self) -> int:
        return self.state.interval * 1000

    @property
    def progress(self) -> float:
        """0 at the start of a pose, 1 when it is over."""
        return 1 - self.remaining_ms / max(1, self.total_ms)

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
        if self.running:
            self._clock.restart()
        self.tick.emit()

    def set_interval(self, sec: int):
        self.state.interval = sec
        self.state.schedule_save()
        self.restart()

    def _on_list_changed(self):
        if not self.state.practice:
            self.pause()
            self.restart()

    def _consume(self):
        self.remaining_ms -= self._clock.restart()

    def _on_tick(self):
        self._consume()
        if self.remaining_ms <= 0:
            if settings["chime"]:
                play_chime()
            self.state.next_pose()     # emits poseChanged -> restart()
            if self.remaining_ms <= 0:  # only one pose: start it again
                self.restart()
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
