"""
Circular Countdown Timer HUD — fully theme-aware, zero hardcoded purple.
Draggable within the parent view.
"""
import math
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QBrush, QMouseEvent
from PySide6.QtCore import Qt, QRectF, QPointF
from refpad.ui.themes import get_current_theme


class TimerHUD(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)

        self.remaining_seconds: float = 120.0
        self.duration_seconds: int = 120
        self.fraction: float = 1.0
        self.pose_index: int = 0
        self.total_poses: int = 0
        self.is_paused: bool = True

        self.setFixedSize(130, 152)
        self.is_dragging = False
        self.drag_start_pos = QPointF(0, 0)

    def update_time(self, remaining: float, fraction: float):
        self.remaining_seconds = remaining
        self.fraction = max(0.0, min(1.0, fraction))
        self.update()

    def update_pose_info(self, index: int, total: int, duration: int):
        self.pose_index = index
        self.total_poses = total
        self.duration_seconds = duration
        self.update()

    def set_paused(self, paused: bool):
        self.is_paused = paused
        self.update()

    # --- Draggable HUD ---
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            self.is_dragging = True
            self.drag_start_pos = event.position()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        if self.is_dragging and self.parentWidget():
            delta = event.position() - self.drag_start_pos
            new_pos = self.pos() + delta.toPoint()
            pw = self.parentWidget().width()
            ph = self.parentWidget().height()
            nx = max(8, min(pw - self.width() - 8, new_pos.x()))
            ny = max(8, min(ph - self.height() - 8, new_pos.y()))
            self.move(nx, ny)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.is_dragging = False
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        theme = get_current_theme()

        # Card background
        bg_rect = QRectF(2, 2, self.width() - 4, self.height() - 4)
        painter.setBrush(QBrush(QColor(theme.bg_card)))
        painter.setPen(QPen(QColor(theme.border), 1.2))
        painter.drawRoundedRect(bg_rect, 12, 12)

        # Ring dimensions
        cx = self.width() / 2.0
        cy = 46.0
        radius = 31.0
        ring_rect = QRectF(cx - radius, cy - radius, radius * 2, radius * 2)

        # Track ring
        pen_track = QPen(QColor(theme.ring_track), 4.5)
        pen_track.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_track)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(ring_rect)

        # Active arc — use theme accent, override for urgent states
        if self.remaining_seconds <= 10.0:
            arc_color = QColor(220, 50, 50)     # urgent red (neutral, no purple)
        elif self.remaining_seconds <= 30.0:
            arc_color = QColor(220, 140, 30)    # warning amber
        elif self.is_paused:
            arc_color = QColor(theme.text_muted)
        else:
            arc_color = QColor(theme.accent)

        span_angle = int(-self.fraction * 360 * 16)
        pen_arc = QPen(arc_color, 4.8)
        pen_arc.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_arc)
        painter.drawArc(ring_rect, 90 * 16, span_angle)

        # Countdown text
        total_sec = max(0, math.ceil(int(self.remaining_seconds)) if self.remaining_seconds > 0 else 0)
        total_sec = max(0, int(math.ceil(self.remaining_seconds)))
        minutes = total_sec // 60
        seconds = total_sec % 60
        time_text = f"{minutes}:{seconds:02d}"

        painter.setPen(QColor(theme.text_primary))
        painter.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        painter.drawText(ring_rect, Qt.AlignmentFlag.AlignCenter, time_text)

        # Duration badge
        if self.duration_seconds >= 60:
            d = self.duration_seconds // 60
            badge_text = f"{d} {'MIN' if d == 1 else 'MINS'} POSE"
        else:
            badge_text = f"{self.duration_seconds}s POSE"

        badge_rect = QRectF(10, 86, self.width() - 20, 18)
        painter.setBrush(QBrush(QColor(theme.bg_card)))
        painter.setPen(QPen(QColor(theme.border), 1.0))
        painter.drawRoundedRect(badge_rect, 5, 5)
        painter.setPen(QColor(theme.text_primary))
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

        # Pose counter
        count_text = f"Pose {self.pose_index + 1} / {max(1, self.total_poses)}"
        painter.setPen(QColor(theme.text_muted))
        painter.setFont(QFont("Segoe UI", 8))
        painter.drawText(QRectF(10, 108, self.width() - 20, 16), Qt.AlignmentFlag.AlignCenter, count_text)

        # Paused label
        if self.is_paused:
            painter.setPen(QColor(theme.text_muted))
            painter.setFont(QFont("Segoe UI", 7, QFont.Weight.Bold))
            painter.drawText(QRectF(10, 126, self.width() - 20, 14), Qt.AlignmentFlag.AlignCenter, "PAUSED")
