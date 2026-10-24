"""
Line of Action Session Engine: Timer, warm-up ladder, auto-advance state machine.
"""
from typing import List, Optional, Tuple
from PySide6.QtCore import QObject, QTimer, Signal
from refpad.models.item import RefItem

class SessionEngine(QObject):
    # Signals
    tick = Signal(float, float)              # (remaining_seconds, fraction_remaining 0.0 to 1.0)
    pose_changed = Signal(int, object, int)  # (current_index, current_RefItem, duration_seconds)
    session_paused = Signal(bool)            # (is_paused)
    session_ended = Signal()
    chime_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.items: List[RefItem] = []
        self.current_index: int = 0
        self.default_duration: int = 120  # default 2 minutes (120s)
        self.current_pose_duration: int = 120
        self.time_remaining: float = 120.0
        self.is_paused: bool = True
        self.is_running: bool = False

        # Class / Warm-up Ladder Mode
        # Format: List of (duration_seconds, count_of_poses)
        # e.g., [(30, 5), (60, 5), (300, 2)]
        self.is_ladder_mode: bool = False
        self.ladder_schedule: List[int] = []  # flattened list of durations per pose
        self.ladder_index: int = 0

        # High-frequency timer for smooth radial animation (10 updates per second)
        self.timer = QTimer(self)
        self.timer.setInterval(100)  # 100ms
        self.timer.timeout.connect(self._on_tick)

    def set_items(self, items: List[RefItem]):
        self.items = items
        self.current_index = 0
        if self.items:
            self._prepare_pose(self.current_index)

    def set_duration(self, seconds: int):
        self.is_ladder_mode = False
        self.default_duration = max(5, seconds)
        self.current_pose_duration = self.default_duration
        self.time_remaining = float(self.current_pose_duration)
        if self.items:
            item = self.items[self.current_index]
            self.pose_changed.emit(self.current_index, item, self.current_pose_duration)
            self.tick.emit(self.time_remaining, 1.0)

    def set_ladder_mode(self, ladder_spec: List[Tuple[int, int]]):
        """Set up a warm-up ladder like [(30, 5), (60, 5), (300, 2)]."""
        self.is_ladder_mode = True
        self.ladder_schedule = []
        for duration, count in ladder_spec:
            self.ladder_schedule.extend([duration] * count)
        self.ladder_index = 0
        self.current_index = 0
        if self.items:
            self._prepare_pose(self.current_index)

    def start_session(self):
        if not self.items:
            return
        self.is_running = True
        self.is_paused = False
        self._prepare_pose(self.current_index)
        self.timer.start()
        self.session_paused.emit(False)

    def toggle_pause(self):
        if not self.is_running:
            self.start_session()
            return
        self.is_paused = not self.is_paused
        self.session_paused.emit(self.is_paused)

    def pause(self):
        self.is_paused = True
        self.session_paused.emit(True)

    def resume(self):
        if not self.is_running:
            self.start_session()
        else:
            self.is_paused = False
            self.session_paused.emit(False)

    def next_pose(self):
        if not self.items:
            return
        if self.current_index + 1 < len(self.items):
            self.current_index += 1
            if self.is_ladder_mode and self.ladder_index + 1 < len(self.ladder_schedule):
                self.ladder_index += 1
            self._prepare_pose(self.current_index)
        else:
            # End of session
            self.timer.stop()
            self.is_running = False
            self.is_paused = True
            self.session_ended.emit()

    def prev_pose(self):
        if not self.items:
            return
        if self.current_index > 0:
            self.current_index -= 1
            if self.is_ladder_mode and self.ladder_index > 0:
                self.ladder_index -= 1
            self._prepare_pose(self.current_index)

    def restart_current_pose(self):
        self.time_remaining = float(self.current_pose_duration)
        fraction = 1.0
        self.tick.emit(self.time_remaining, fraction)

    def _prepare_pose(self, index: int):
        if not self.items or index >= len(self.items):
            return

        if self.is_ladder_mode and self.ladder_schedule:
            if self.ladder_index < len(self.ladder_schedule):
                self.current_pose_duration = self.ladder_schedule[self.ladder_index]
            else:
                self.current_pose_duration = self.ladder_schedule[-1]
        else:
            self.current_pose_duration = self.default_duration

        self.time_remaining = float(self.current_pose_duration)
        item = self.items[index]
        self.pose_changed.emit(index, item, self.current_pose_duration)
        self.tick.emit(self.time_remaining, 1.0)

    def _on_tick(self):
        if self.is_paused or not self.is_running:
            return

        self.time_remaining -= 0.1
        if self.time_remaining <= 0:
            self.time_remaining = 0
            self.tick.emit(0.0, 0.0)
            self.chime_requested.emit()
            self.next_pose()
        else:
            fraction = max(0.0, min(1.0, self.time_remaining / self.current_pose_duration))
            self.tick.emit(self.time_remaining, fraction)

    @property
    def current_item(self) -> Optional[RefItem]:
        if self.items and 0 <= self.current_index < len(self.items):
            return self.items[self.current_index]
        return None
