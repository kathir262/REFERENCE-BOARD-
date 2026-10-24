"""
Floating Glass Toolbar / Dock:
Modern floating pill dock with frosted glass aesthetics and auto-fade.
"""
from typing import Callable, List, Tuple
from PySide6.QtWidgets import (
    QWidget, QHBoxLayout, QPushButton, QMenu, QSlider, QFrame, QGraphicsOpacityEffect
)
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QAction, QFont
from PySide6.QtCore import Qt, Signal, QRectF, QPropertyAnimation, QEasingCurve, QTimer

from refpad.ui.icons import (
    draw_play_icon, draw_pause_icon, draw_skip_next_icon, draw_skip_prev_icon,
    draw_flip_icon, draw_grayscale_icon, draw_pin_icon
)
from refpad.ui.widgets import GlassIconButton

class FloatingDock(QWidget):
    play_pause_clicked = Signal()
    next_clicked = Signal()
    prev_clicked = Signal()
    flip_clicked = Signal()
    grayscale_clicked = Signal()
    silhouette_clicked = Signal()
    duration_selected = Signal(int)
    ladder_selected = Signal(list)
    open_folder_requested = Signal()
    open_pdf_requested = Signal()
    pin_toggled = Signal(bool)
    opacity_changed = Signal(float)
    fit_all_clicked = Signal()
    auto_arrange_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self.is_paused = True
        self.is_pinned = True
        self.mode = "action"

        # Smooth auto-fade effect
        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(0.95)
        self.setGraphicsEffect(self.opacity_effect)

        self.fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_anim.setDuration(250)
        self.fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        # Idle timer to auto-dim when artist is drawing
        self.idle_timer = QTimer(self)
        self.idle_timer.setInterval(3500)
        self.idle_timer.timeout.connect(self._dim_dock)

        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(6)

        # 1. Line of Action Playback Icons
        self.btn_prev = GlassIconButton(draw_skip_prev_icon, "Previous Pose (Left Arrow / A)")
        self.btn_prev.clicked.connect(self.prev_clicked.emit)

        self.btn_play = GlassIconButton(draw_play_icon, "Play / Pause Timer (Space)")
        self.btn_play.clicked.connect(self.play_pause_clicked.emit)

        self.btn_next = GlassIconButton(draw_skip_next_icon, "Next Pose (Right Arrow / D)")
        self.btn_next.clicked.connect(self.next_clicked.emit)

        layout.addWidget(self.btn_prev)
        layout.addWidget(self.btn_play)
        layout.addWidget(self.btn_next)

        # 2. Timer Duration Pill Button (opens popup menu)
        self.btn_duration = QPushButton("2 min ▾")
        self.btn_duration.setFixedHeight(34)
        self.btn_duration.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_duration.setToolTip("Select Pose Duration or Warm-up Sequence")
        self.btn_duration.clicked.connect(self._show_duration_menu)
        layout.addWidget(self.btn_duration)

        # Separator
        self.sep = QFrame()
        self.sep.setFrameShape(QFrame.Shape.VLine)
        self.sep.setStyleSheet("color: rgba(255, 255, 255, 25); margin: 6px 2px;")
        layout.addWidget(self.sep)

        # 3. Artist Power Tools: Flip, Grayscale, Silhouette
        self.btn_flip = GlassIconButton(draw_flip_icon, "Mirror Horizontally (H)")
        self.btn_flip.clicked.connect(self.flip_clicked.emit)

        self.btn_gray = GlassIconButton(draw_grayscale_icon, "Grayscale / Tonal Value (G)")
        self.btn_gray.clicked.connect(self.grayscale_clicked.emit)

        layout.addWidget(self.btn_flip)
        layout.addWidget(self.btn_gray)

        # 4. Canvas Tools (BeeRef Mode)
        self.btn_fit = QPushButton("⛶ Fit")
        self.btn_fit.setFixedHeight(34)
        self.btn_fit.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_fit.setToolTip("Fit All References in View (F)")
        self.btn_fit.clicked.connect(self.fit_all_clicked.emit)

        self.btn_grid = QPushButton("⊞ Tile")
        self.btn_grid.setFixedHeight(34)
        self.btn_grid.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_grid.setToolTip("Auto-Tile Grid")
        self.btn_grid.clicked.connect(self.auto_arrange_clicked.emit)

        layout.addWidget(self.btn_fit)
        layout.addWidget(self.btn_grid)

        # Separator
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.Shape.VLine)
        sep2.setStyleSheet("color: rgba(255, 255, 255, 25); margin: 6px 2px;")
        layout.addWidget(sep2)

        # 5. Ingestion Buttons: Folder, PDF
        self.btn_folder = QPushButton("📁")
        self.btn_folder.setFixedSize(34, 34)
        self.btn_folder.setToolTip("Open Image Folder")
        self.btn_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_folder.clicked.connect(self.open_folder_requested.emit)
        layout.addWidget(self.btn_folder)

        self.btn_pdf = QPushButton("📄")
        self.btn_pdf.setFixedSize(34, 34)
        self.btn_pdf.setToolTip("Open Art or Anatomy PDF")
        self.btn_pdf.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pdf.clicked.connect(self.open_pdf_requested.emit)
        layout.addWidget(self.btn_pdf)

        # 6. Always-on-top Pin
        self.btn_pin = GlassIconButton(
            lambda p, r, c: draw_pin_icon(p, r, c, self.is_pinned),
            "Always On Top (T)"
        )
        self.btn_pin.setActive(True)
        self.btn_pin.clicked.connect(self._toggle_pin)
        layout.addWidget(self.btn_pin)

        self._apply_styles()
        self.set_mode("action")

    def set_mode(self, mode: str):
        self.mode = mode
        is_action = (mode == "action")

        self.btn_prev.setVisible(is_action)
        self.btn_play.setVisible(is_action)
        self.btn_next.setVisible(is_action)
        self.btn_duration.setVisible(is_action)
        self.sep.setVisible(is_action)

        self.btn_fit.setVisible(not is_action)
        self.btn_grid.setVisible(not is_action)
        self.adjustSize()

    def set_paused(self, paused: bool):
        self.is_paused = paused
        if paused:
            self.btn_play.draw_fn = draw_play_icon
            self.btn_play.setToolTip("Play Timer (Space)")
        else:
            self.btn_play.draw_fn = draw_pause_icon
            self.btn_play.setToolTip("Pause Timer (Space)")
        self.btn_play.update()

    def _toggle_pin(self):
        self.is_pinned = not self.is_pinned
        self.btn_pin.setActive(self.is_pinned)
        self.pin_toggled.emit(self.is_pinned)

    def _show_duration_menu(self):
        menu = QMenu(self)
        menu.setStyleSheet("""
            QMenu {
                background-color: #1a1c23;
                color: #e6edf3;
                border: 1px solid rgba(255, 255, 255, 30);
                border-radius: 8px;
                padding: 4px;
            }
            QMenu::item {
                padding: 6px 18px;
                border-radius: 4px;
                font-family: 'Segoe UI', -apple-system;
                font-size: 11px;
            }
            QMenu::item:selected {
                background-color: #7e57f6;
                color: #ffffff;
            }
        """)

        options = [
            ("30 seconds", 30),
            ("45 seconds", 45),
            ("1 minute", 60),
            ("2 minutes", 120),
            ("3 minutes", 180),
            ("5 minutes", 300),
            ("10 minutes", 600),
        ]

        for label, sec in options:
            action = menu.addAction(label)
            action.triggered.connect(lambda chk=False, s=sec, l=label: self._set_duration(s, l))

        menu.addSeparator()
        action_ladder = menu.addAction("🔥 Warm-up Ladder (30s → 1m → 5m)")
        action_ladder.triggered.connect(self._set_ladder)

        menu.exec(self.btn_duration.mapToGlobal(self.btn_duration.rect().bottomLeft()))

    def _set_duration(self, seconds: int, label: str):
        self.btn_duration.setText(label.split()[0] + " " + label.split()[1][:3] + " ▾")
        self.duration_selected.emit(seconds)

    def _set_ladder(self):
        self.btn_duration.setText("Ladder ▾")
        self.ladder_selected.emit([(30, 5), (60, 5), (300, 2)])

    def _dim_dock(self):
        self.fade_anim.stop()
        self.fade_anim.setStartValue(self.opacity_effect.opacity())
        self.fade_anim.setEndValue(0.20)  # Gentle ghosting so artist sees art unobstructed
        self.fade_anim.start()

    def wake_dock(self):
        self.idle_timer.start()
        self.fade_anim.stop()
        self.fade_anim.setStartValue(self.opacity_effect.opacity())
        self.fade_anim.setEndValue(0.96)
        self.fade_anim.start()

    def enterEvent(self, event):
        self.wake_dock()
        super().enterEvent(event)

    def _apply_styles(self):
        btn_style = """
            QPushButton {
                background-color: rgba(255, 255, 255, 10);
                border: 1px solid rgba(255, 255, 255, 20);
                border-radius: 8px;
                color: #e6edf3;
                font-family: 'Segoe UI', -apple-system;
                font-size: 11px;
                font-weight: 600;
                padding: 0 10px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 24);
                color: #ffffff;
                border-color: rgba(255, 255, 255, 40);
            }
        """
        self.btn_duration.setStyleSheet(btn_style)
        self.btn_fit.setStyleSheet(btn_style)
        self.btn_grid.setStyleSheet(btn_style)
        self.btn_folder.setStyleSheet(btn_style)
        self.btn_pdf.setStyleSheet(btn_style)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0, 0, self.width(), self.height())
        # Frosted glass floating pill background with subtle glow border
        painter.setBrush(QBrush(QColor(16, 18, 24, 235)))
        painter.setPen(QPen(QColor(255, 255, 255, 28), 1.2))
        painter.drawRoundedRect(rect, 14, 14)
