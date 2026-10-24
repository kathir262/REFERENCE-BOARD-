"""
Circular Countdown Timer HUD overlay widget (Line of Action style).
Renders smooth anti-aliased ring, remaining time, and pose info badge.
"""
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QPainter, QColor, QPen, QFont, QBrush
from PySide6.QtCore import Qt, QRectF, QPointF

class TimerHUD(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, False)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        
        self.remaining_seconds: float = 120.0
        self.duration_seconds: int = 120
        self.fraction: float = 1.0  # 1.0 down to 0.0
        self.pose_index: int = 0
        self.total_poses: int = 0
        self.is_paused: bool = True

        self.setFixedSize(140, 160)

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

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # Translucent pill background card
        bg_rect = QRectF(4, 4, self.width() - 8, self.height() - 8)
        painter.setBrush(QBrush(QColor(24, 26, 32, 215)))
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1.2))
        painter.drawRoundedRect(bg_rect, 14, 14)

        # Circular progress ring dimensions
        center_x = self.width() / 2.0
        center_y = 52.0
        radius = 36.0
        ring_rect = QRectF(center_x - radius, center_y - radius, radius * 2, radius * 2)

        # Background track
        pen_track = QPen(QColor(255, 255, 255, 35), 4.5)
        pen_track.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_track)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawEllipse(ring_rect)

        # Foreground active progress arc (starts at 12 o'clock = 90 deg, moves clockwise)
        # Note: Qt angles are in 1/16th of a degree, counter-clockwise
        span_angle = int(-self.fraction * 360 * 16)
        start_angle = 90 * 16

        # Color changes as time runs low: Purple/Cyan -> Orange -> Red when < 10s
        if self.remaining_seconds <= 10.0:
            arc_color = QColor(248, 81, 73)      # Alert red
        elif self.remaining_seconds <= 30.0:
            arc_color = QColor(240, 136, 62)     # Warning orange
        elif self.is_paused:
            arc_color = QColor(139, 148, 158)    # Paused muted gray
        else:
            arc_color = QColor(126, 87, 246)     # Radiant purple/violet (like reference image)

        pen_arc = QPen(arc_color, 5.0)
        pen_arc.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen_arc)
        painter.drawArc(ring_rect, start_angle, span_angle)

        # Center Digital Countdown: "MM:SS" or "SS"
        total_sec = max(0, int(math_ceil(self.remaining_seconds)))
        minutes = total_sec // 60
        seconds = total_sec % 60
        time_text = f"{minutes}:{seconds:02d}"

        painter.setPen(QColor(245, 245, 250))
        font = QFont("Segoe UI", 13, QFont.Weight.Bold)
        painter.setFont(font)
        painter.drawText(ring_rect, Qt.AlignmentFlag.AlignCenter, time_text)

        # Pose Duration badge (e.g., "2 MINUTE POSE" or "45s POSE")
        if self.duration_seconds >= 60:
            dur_mins = self.duration_seconds // 60
            unit = "MIN" if dur_mins == 1 else "MINS"
            badge_text = f"{dur_mins} {unit} POSE"
        else:
            badge_text = f"{self.duration_seconds}s POSE"

        badge_rect = QRectF(10, 96, self.width() - 20, 20)
        painter.setBrush(QBrush(QColor(255, 255, 255, 18)))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(badge_rect, 6, 6)

        painter.setPen(QColor(200, 210, 230))
        font_badge = QFont("Segoe UI", 8, QFont.Weight.DemiBold)
        font_badge.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 0.5)
        painter.setFont(font_badge)
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, badge_text)

        # Pose Count / Total: "Pose 3 of 20"
        count_text = f"Pose {self.pose_index + 1} of {max(1, self.total_poses)}"
        painter.setPen(QColor(130, 140, 155))
        font_count = QFont("Segoe UI", 8)
        painter.setFont(font_count)
        painter.drawText(QRectF(10, 122, self.width() - 20, 16), Qt.AlignmentFlag.AlignCenter, count_text)

        # Paused indicator badge if paused
        if self.is_paused:
            paused_rect = QRectF(10, 138, self.width() - 20, 14)
            painter.setPen(QColor(230, 180, 80))
            font_p = QFont("Segoe UI", 7, QFont.Weight.Bold)
            painter.setFont(font_p)
            painter.drawText(paused_rect, Qt.AlignmentFlag.AlignCenter, "PAUSED (Space)")

def math_ceil(val: float) -> int:
    import math
    return int(math.ceil(val))
