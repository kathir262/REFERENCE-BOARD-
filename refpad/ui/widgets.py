"""
Boutique modern UI components: Frosted glass buttons, Segmented Switch, Floating Pill.
"""
from typing import Callable, Optional
from PySide6.QtWidgets import QWidget, QPushButton, QHBoxLayout, QLabel
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QMouseEvent, QEnterEvent
from PySide6.QtCore import Qt, QRectF, Signal, Property, QPropertyAnimation, QEasingCurve

class GlassIconButton(QPushButton):
    def __init__(self, draw_fn: Callable, tooltip: str = "", parent=None):
        super().__init__(parent)
        self.draw_fn = draw_fn
        self.setToolTip(tooltip)
        self.setFixedSize(36, 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.is_hovered = False
        self.is_active = False

    def setActive(self, active: bool):
        self.is_active = active
        self.update()

    def enterEvent(self, event: QEnterEvent):
        self.is_hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.is_hovered = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = QRectF(2, 2, self.width() - 4, self.height() - 4)

        # Background fill
        if self.is_active:
            painter.setBrush(QBrush(QColor(126, 87, 246, 220)))  # Radiant purple
            painter.setPen(QPen(QColor(160, 130, 255, 180), 1.2))
        elif self.is_hovered:
            painter.setBrush(QBrush(QColor(255, 255, 255, 28)))
            painter.setPen(QPen(QColor(255, 255, 255, 45), 1))
        else:
            painter.setBrush(QBrush(QColor(255, 255, 255, 10)))
            painter.setPen(QPen(QColor(255, 255, 255, 16), 1))

        painter.drawRoundedRect(rect, 8, 8)

        # Icon
        icon_color = QColor(255, 255, 255) if (self.is_active or self.is_hovered) else QColor(200, 205, 215)
        self.draw_fn(painter, rect, icon_color)


class SegmentedPillSwitch(QWidget):
    """Sleek floating segmented switch for [ ⏱ Practice ] | [ 🖼 Board ]."""
    mode_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(34)
        self.current_mode = "action"  # 'action' or 'canvas'

        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)

        self.btn_action = QPushButton("⏱ Practice")
        self.btn_canvas = QPushButton("🖼 Board")

        for btn in (self.btn_action, self.btn_canvas):
            btn.setFixedHeight(28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            layout.addWidget(btn)

        self.btn_action.clicked.connect(lambda: self.set_mode("action"))
        self.btn_canvas.clicked.connect(lambda: self.set_mode("canvas"))

        self._update_styles()

    def set_mode(self, mode: str):
        self.current_mode = mode
        self._update_styles()
        self.mode_changed.emit(mode)

    def toggle_mode(self):
        new_mode = "canvas" if self.current_mode == "action" else "action"
        self.set_mode(new_mode)

    def _update_styles(self):
        is_action = (self.current_mode == "action")
        style_active = """
            QPushButton {
                background-color: #7e57f6;
                color: #ffffff;
                font-family: 'Segoe UI', -apple-system;
                font-size: 11px;
                font-weight: 700;
                border: none;
                border-radius: 6px;
                padding: 0 12px;
            }
        """
        style_inactive = """
            QPushButton {
                background-color: transparent;
                color: #8b949e;
                font-family: 'Segoe UI', -apple-system;
                font-size: 11px;
                font-weight: 500;
                border: none;
                border-radius: 6px;
                padding: 0 12px;
            }
            QPushButton:hover {
                color: #ffffff;
                background-color: rgba(255, 255, 255, 12);
            }
        """
        self.btn_action.setStyleSheet(style_active if is_action else style_inactive)
        self.btn_canvas.setStyleSheet(style_active if not is_action else style_inactive)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0, 0, self.width(), self.height())
        # Dark translucent frosted pill container
        painter.setBrush(QBrush(QColor(20, 22, 28, 225)))
        painter.setPen(QPen(QColor(255, 255, 255, 24), 1))
        painter.drawRoundedRect(rect, 8, 8)
