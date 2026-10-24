"""
Boutique Circular Countdown Timer HUD (Line of Action).
Frosted glass card, gradient vector arc, micro-typography, draggable position.
"""
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import (
    QPainter, QColor, QPen, QFont, QBrush, QConicalGradient, QMouseEvent
)
from PySide6.QtCore import Qt, QRectF, QPointF

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

        self.setFixedSize(130, 150)

        # Allow dragging HUD inside parent view
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
            # Constrain within parent
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

        # 1. Frosted glass card backing
        bg_rect = QRectF(2, 2, self.width() - 4, self.height() - 4)
        painter.setBrush(QBrush(QColor(16, 18, 24, 225)))
        painter.setPen(QPen(QColor(255, 255, 255, 25), 1.2))
        painter.drawRoundedRect(bg_rect, 14, 14)

        # 2. Ring geometry
        center_x = self.width() / 2.0
        center_y = 48.0
        radius = 32.0
        ring_rect = QRectF(center_x - radius, center_y - radius, radius * 2, radius * 2)

        # Background track
        pen_track = QPen(QColor(255, 255, 255, 28), 4.5)
        pen_track.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_track)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(ring_rect)

        # Active countdown arc
        span_angle = int(-self.fraction * 360 * 16)
        start_angle = 90 * 16

        if self.remaining_seconds <= 10.0:
            arc_color = QColor(255, 85, 85)     # Glowing alert red
        elif self.remaining_seconds <= 30.0:
            arc_color = QColor(255, 160, 50)    # Warning orange
        elif self.is_paused:
            arc_color = QColor(130, 140, 155)   # Muted slate
        else:
            arc_color = QColor(126, 87, 246)    # Radiant electric violet

        pen_arc = QPen(arc_color, 4.8)
        pen_arc.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_arc)
        painter.drawArc(ring_rect, start_angle, span_angle)

        # 3. Center Digital Countdown: "MM:SS"
        total_sec = max(0, int(math_ceil(self.remaining_seconds)))
        minutes = total_sec // 60
        seconds = total_sec % 60
        time_text = f"{minutes}:{seconds:02d}"

        painter.setPen(QColor(245, 248, 255))
        font_digits = QFont("Segoe UI", 13, QFont.Weight.Bold)
        font_digits.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
        painter.setFont(font_digits)
        painter.drawText(ring_rect, Qt.AlignmentFlag.AlignCenter, time_text)

        # 4. Pose Duration micro-badge (e.g. "2 MIN POSE")
        if self.duration_seconds >= 60:
            dur_mins = self.duration_seconds // 60
            unit = "MIN" if dur_mins == 1 else "MINS"
            badge_text = f"{dur_mins} {unit} POSE"
        else:
            badge_text = f"{self.duration_seconds}s POSE"

        badge_rect = QRectF(10, 88, self.width() - 20, 18)
        painter.setBrush(QBrush(QColor(126, 87, 246, 35)))
        painter.setPen(QPen(QColor(126, 87, 246, 80), 0.8))
        painter.drawRoundedRect(badge_rect, 5, 5)

        painter.setPen(QColor(180, 160, 255))
        font_badge = QFont("Segoe UI", 8, QFont.Weight.DemiBold)
        font_badge.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.4)
        painter.setFont(font_badge)
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

        # 5. Pose Counter: "Pose 3 of 20"
        count_text = f"Pose {self.pose_index + 1} / {max(1, self.total_poses)}"
        painter.setPen(QColor(140, 150, 165))
        font_count = QFont("Segoe UI", 8)
        painter.setFont(font_count)
        painter.drawText(QRectF(10, 110, self.width() - 20, 16), Qt.AlignmentFlag.AlignCenter, count_text)

        # 6. Paused Pill
        if self.is_paused:
            paused_rect = QRectF(12, 128, self.width() - 24, 14)
            painter.setPen(QColor(245, 180, 70))
            font_p = QFont("Segoe UI", 7, QFont.Weight.Bold)
            painter.setFont(font_p)
            painter.drawText(paused_rect, Qt.AlignmentFlag.AlignCenter, "PAUSED (Space)")

def math_ceil(val: float) -> int:
    import math
    return int(math.ceil(val))
