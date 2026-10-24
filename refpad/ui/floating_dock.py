"""
Floating Glass Toolbar / Dock:
Integrated with Full BeeRef Operations, Menu Bar (☰), Mode Toggle, Theme Switcher, and auto-dim.
Zero hardcoded purple — 100% theme-aware.
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
from refpad.ui.themes import get_current_theme, set_current_theme, THEMES

class FloatingDock(QWidget):
    play_pause_clicked = Signal()
    next_clicked = Signal()
    prev_clicked = Signal()
    flip_clicked = Signal()
    grayscale_clicked = Signal()
    duration_selected = Signal(int)
    ladder_selected = Signal(list)
    open_folder_requested = Signal()
    open_pdf_requested = Signal()
    save_board_requested = Signal()
    open_board_requested = Signal()
    export_image_requested = Signal()
    paste_requested = Signal()
    add_note_requested = Signal()
    align_requested = Signal(str)
    normalize_requested = Signal(str)
    theme_changed = Signal(str)
    pin_toggled = Signal(bool)
    fit_all_clicked = Signal()
    auto_arrange_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self.is_paused = True
        self.is_pinned = True
        self.mode = "action"

        self.opacity_effect = QGraphicsOpacityEffect(self)
        self.opacity_effect.setOpacity(0.96)
        self.setGraphicsEffect(self.opacity_effect)

        self.fade_anim = QPropertyAnimation(self.opacity_effect, b"opacity")
        self.fade_anim.setDuration(250)
        self.fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self.idle_timer = QTimer(self)
        self.idle_timer.setInterval(4000)
        self.idle_timer.timeout.connect(self._dim_dock)

        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(6)

        # 0. Menu Bar Button (☰ All BeeRef & App Options)
        self.btn_menu = QPushButton("☰")
        self.btn_menu.setFixedSize(34, 34)
        self.btn_menu.setToolTip("Main Menu (File, Edit, Arrange, Themes, Window)")
        self.btn_menu.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_menu.clicked.connect(self._show_main_menu)
        layout.addWidget(self.btn_menu)

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

        # 2. Timer Duration Pill Button
        self.btn_duration = QPushButton("2 min ▾")
        self.btn_duration.setFixedHeight(34)
        self.btn_duration.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_duration.setToolTip("Select Pose Duration or Warm-up Sequence")
        self.btn_duration.clicked.connect(self._show_duration_menu)
        layout.addWidget(self.btn_duration)

        # Separator
        self.sep = QFrame()
        self.sep.setFrameShape(QFrame.Shape.VLine)
        layout.addWidget(self.sep)

        # 3. Artist Power Tools: Flip, Grayscale
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
        self.btn_fit.setToolTip("Fit All References (F)")
        self.btn_fit.clicked.connect(self.fit_all_clicked.emit)

        self.btn_grid = QPushButton("⊞ Pack")
        self.btn_grid.setFixedHeight(34)
        self.btn_grid.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_grid.setToolTip("Pack & Tile References into Neat Grid (P)")
        self.btn_grid.clicked.connect(self.auto_arrange_clicked.emit)

        layout.addWidget(self.btn_fit)
        layout.addWidget(self.btn_grid)

        # Separator 2
        self.sep2 = QFrame()
        self.sep2.setFrameShape(QFrame.Shape.VLine)
        layout.addWidget(self.sep2)

        # 5. Quick Sources: PDF, Folder, Save
        self.btn_pdf = QPushButton("📄")
        self.btn_pdf.setFixedSize(34, 34)
        self.btn_pdf.setToolTip("Open Art or Anatomy PDF Book")
        self.btn_pdf.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pdf.clicked.connect(self.open_pdf_requested.emit)
        layout.addWidget(self.btn_pdf)

        self.btn_folder = QPushButton("📁")
        self.btn_folder.setFixedSize(34, 34)
        self.btn_folder.setToolTip("Open Image/PDF Folder")
        self.btn_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_folder.clicked.connect(self.open_folder_requested.emit)
        layout.addWidget(self.btn_folder)

        self.btn_save = QPushButton("💾")
        self.btn_save.setFixedSize(34, 34)
        self.btn_save.setToolTip("Save Board File (.refpad / .bee) (Ctrl+S)")
        self.btn_save.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_save.clicked.connect(self.save_board_requested.emit)
        layout.addWidget(self.btn_save)

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

    def _show_main_menu(self):
        """Full BeeRef Menu: File, Edit, Arrange, Themes, Window."""
        menu = QMenu(self)
        self._style_menu(menu)

        menu_file = menu.addMenu("📁 File")
        self._style_menu(menu_file)
        menu_file.addAction("Open Reference Board (.refpad / .bee)... (Ctrl+O)", self.open_board_requested.emit)
        menu_file.addAction("Save Reference Board (Ctrl+S)", self.save_board_requested.emit)
        menu_file.addSeparator()
        menu_file.addAction("Open PDF Reference Book...", self.open_pdf_requested.emit)
        menu_file.addAction("Open Image / PDF Folder...", self.open_folder_requested.emit)
        menu_file.addSeparator()
        menu_file.addAction("Export Reference Board as Image... (Ctrl+E)", self.export_image_requested.emit)

        menu_edit = menu.addMenu("✏️ Edit")
        self._style_menu(menu_edit)
        menu_edit.addAction("Paste Image from Clipboard (Ctrl+V)", self.paste_requested.emit)
        menu_edit.addAction("Add Sticky Text Note (Ctrl+N)", self.add_note_requested.emit)

        menu_arrange = menu.addMenu("📐 Arrange & Align")
        self._style_menu(menu_arrange)
        menu_arrange.addAction("Pack & Auto-Tile (P)", self.auto_arrange_clicked.emit)
        menu_arrange.addSeparator()
        menu_arrange.addAction("Align Left", lambda: self.align_requested.emit('left'))
        menu_arrange.addAction("Align Right", lambda: self.align_requested.emit('right'))
        menu_arrange.addAction("Align Top", lambda: self.align_requested.emit('top'))
        menu_arrange.addAction("Align Bottom", lambda: self.align_requested.emit('bottom'))
        menu_arrange.addAction("Align Center Horizontal (Row)", lambda: self.align_requested.emit('center_h'))
        menu_arrange.addAction("Align Center Vertical (Column)", lambda: self.align_requested.emit('center_v'))
        menu_arrange.addSeparator()
        menu_arrange.addAction("Normalize Height (Same Height)", lambda: self.normalize_requested.emit('height'))
        menu_arrange.addAction("Normalize Width (Same Width)", lambda: self.normalize_requested.emit('width'))

        menu_themes = menu.addMenu("🎨 Themes")
        self._style_menu(menu_themes)
        for key, pal in THEMES.items():
            action = menu_themes.addAction(pal.name)
            action.triggered.connect(lambda chk=False, k=key: self._select_theme(k))

        menu.addSeparator()
        menu.addAction("Fit All in View (F)", self.fit_all_clicked.emit)

        menu.exec(self.btn_menu.mapToGlobal(self.btn_menu.rect().bottomLeft()))

    def _select_theme(self, key: str):
        set_current_theme(key)
        self._apply_styles()
        self.theme_changed.emit(key)
        self.update()

    def _show_duration_menu(self):
        menu = QMenu(self)
        self._style_menu(menu)

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
        action_ladder = menu.addAction("Warm-up Ladder (30s → 1m → 5m)")
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
        self.fade_anim.setEndValue(0.18)
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

    def _style_menu(self, menu: QMenu):
        theme = get_current_theme()
        menu.setStyleSheet(f"""
            QMenu {{
                background-color: {theme.bg_card};
                color: {theme.text_primary};
                border: 1px solid {theme.border};
                border-radius: 8px;
                padding: 4px;
            }}
            QMenu::item {{
                padding: 6px 18px;
                border-radius: 4px;
                font-family: 'Segoe UI', -apple-system;
                font-size: 11px;
            }}
            QMenu::item:selected {{
                background-color: {theme.accent};
                color: {theme.bg_dark};
            }}
            QMenu::separator {{
                height: 1px;
                background: {theme.border};
                margin: 4px 6px;
            }}
        """)

    def _apply_styles(self):
        theme = get_current_theme()
        btn_style = f"""
            QPushButton {{
                background-color: {theme.bg_card};
                border: 1px solid {theme.border};
                border-radius: 8px;
                color: {theme.text_primary};
                font-family: 'Segoe UI', -apple-system;
                font-size: 11px;
                font-weight: 600;
                padding: 0 10px;
            }}
            QPushButton:hover {{
                background-color: {theme.accent};
                color: {theme.bg_dark};
                border-color: {theme.accent};
            }}
        """
        self.btn_menu.setStyleSheet(btn_style)
        self.btn_duration.setStyleSheet(btn_style)
        self.btn_fit.setStyleSheet(btn_style)
        self.btn_grid.setStyleSheet(btn_style)
        self.btn_pdf.setStyleSheet(btn_style)
        self.btn_folder.setStyleSheet(btn_style)
        self.btn_save.setStyleSheet(btn_style)
        self.sep.setStyleSheet(f"color: {theme.border}; margin: 6px 2px;")
        self.sep2.setStyleSheet(f"color: {theme.border}; margin: 6px 2px;")
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(0, 0, self.width(), self.height())
        theme = get_current_theme()
        painter.setBrush(QBrush(QColor(theme.bg_card)))
        painter.setPen(QPen(QColor(theme.border), 1.2))
        painter.drawRoundedRect(rect, 14, 14)
