"""
Boutique UI widgets: GlassIconButton, SegmentedPillSwitch.
ALL colors come from the active theme — zero hardcoded purple.
"""
from typing import Callable
from PySide6.QtWidgets import QWidget, QPushButton, QHBoxLayout
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QEnterEvent
from PySide6.QtCore import Qt, QRectF, Signal

from refpad.ui.themes import get_current_theme


class GlassIconButton(QPushButton):
    def __init__(self, draw_fn: Callable, tooltip: str = "", parent=None):
        super().__init__(parent)
        self.draw_fn = draw_fn
        self.setToolTip(tooltip)
        self.setFixedSize(36, 36)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlat(True)
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
        theme = get_current_theme()
        rect = QRectF(2, 2, self.width() - 4, self.height() - 4)

        if self.is_active:
            # Active: use accent fill (white in B&W, rose in rose theme, etc.)
            painter.setBrush(QBrush(QColor(theme.accent)))
            painter.setPen(QPen(QColor(theme.accent), 1))
        elif self.is_hovered:
            painter.setBrush(QBrush(QColor(theme.accent + "30")))
            painter.setPen(QPen(QColor(theme.accent), 1))
        else:
            painter.setBrush(QBrush(QColor(255, 255, 255, 8)))
            painter.setPen(QPen(QColor(theme.border), 1))

        painter.drawRoundedRect(rect, 8, 8)

        # Icon color: dark on active (so white icon on white bg is visible), else accent
        if self.is_active:
            icon_color = QColor(theme.bg_dark)
        else:
            icon_color = QColor(theme.text_primary if self.is_hovered else theme.text_muted)

        self.draw_fn(painter, rect, icon_color)


class SegmentedPillSwitch(QWidget):
    """Mode switcher: [ Practice ] [ Board ] — fully theme-aware."""
    mode_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(34)
        self.current_mode = "action"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)

        self.btn_action = QPushButton("Practice")
        self.btn_canvas = QPushButton("Board")

        for btn in (self.btn_action, self.btn_canvas):
            btn.setFixedHeight(28)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFlat(True)
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
        theme = get_current_theme()
        is_action = (self.current_mode == "action")

        # Determine text color on active button — needs contrast with accent
        # For white accent (B&W theme), text should be dark
        accent_is_light = self._is_light_color(theme.accent)
        active_text = theme.bg_dark if accent_is_light else theme.text_primary

        style_active = f"""
            QPushButton {{
                background-color: {theme.accent};
                color: {active_text};
                font-family: 'Segoe UI', -apple-system;
                font-size: 11px;
                font-weight: 700;
                border: none;
                border-radius: 6px;
                padding: 0 14px;
            }}
        """
        style_inactive = f"""
            QPushButton {{
                background-color: transparent;
                color: {theme.text_muted};
                font-family: 'Segoe UI', -apple-system;
                font-size: 11px;
                font-weight: 500;
                border: none;
                border-radius: 6px;
                padding: 0 14px;
            }}
            QPushButton:hover {{
                color: {theme.text_primary};
                background-color: {theme.border};
            }}
        """
        self.btn_action.setStyleSheet(style_active if is_action else style_inactive)
        self.btn_canvas.setStyleSheet(style_active if not is_action else style_inactive)

    def _is_light_color(self, hex_color: str) -> bool:
        """Returns True if the hex color is visually light (needs dark text on top)."""
        hex_color = hex_color.lstrip('#')
        if len(hex_color) < 6:
            return False
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        return luminance > 0.55

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        theme = get_current_theme()
        rect = QRectF(0, 0, self.width(), self.height())
        painter.setBrush(QBrush(QColor(theme.bg_card)))
        painter.setPen(QPen(QColor(theme.border), 1))
        painter.drawRoundedRect(rect, 8, 8)
