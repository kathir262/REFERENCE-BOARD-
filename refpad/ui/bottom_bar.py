"""
Bottom Floating Controls Bar:
- Line of Action playback (Play/Pause, Prev, Next, Restart)
- Interval Picker (30s, 1m, 2m, 3m, 5m, Warm-up Ladder)
- Artist quick tools (Flip H, Grayscale, Silhouette)
- Mode-aware quick actions
"""
from typing import List, Tuple
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QComboBox, QLabel, QFrame
from PySide6.QtGui import QColor, QFont, QPainter, QBrush, QPen
from PySide6.QtCore import Qt, Signal

class BottomBar(QWidget):
    play_pause_clicked = Signal()
    next_clicked = Signal()
    prev_clicked = Signal()
    restart_clicked = Signal()
    flip_clicked = Signal()
    grayscale_clicked = Signal()
    silhouette_clicked = Signal()
    duration_selected = Signal(int)             # seconds
    ladder_selected = Signal(list)             # list of (sec, count)
    fit_all_clicked = Signal()
    auto_arrange_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(48)
        self.is_paused = True
        self.mode = 'action'
        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 6, 14, 6)
        layout.setSpacing(8)

        # 1. Line of Action Playback Controls
        self.btn_prev = QPushButton("⏮ Prev")
        self.btn_prev.setToolTip("Previous pose (Left Arrow)")
        self.btn_prev.clicked.connect(self.prev_clicked.emit)

        self.btn_play = QPushButton("▶ Play")
        self.btn_play.setToolTip("Play / Pause timer (Space)")
        self.btn_play.setStyleSheet("font-weight: bold;")
        self.btn_play.clicked.connect(self.play_pause_clicked.emit)

        self.btn_next = QPushButton("Next ⏭")
        self.btn_next.setToolTip("Next pose (Right Arrow)")
        self.btn_next.clicked.connect(self.next_clicked.emit)

        self.btn_restart = QPushButton("↺")
        self.btn_restart.setToolTip("Restart current pose timer (R)")
        self.btn_restart.setFixedWidth(28)
        self.btn_restart.clicked.connect(self.restart_clicked.emit)

        layout.addWidget(self.btn_prev)
        layout.addWidget(self.btn_play)
        layout.addWidget(self.btn_next)
        layout.addWidget(self.btn_restart)

        # Separator
        self.sep_timer = QFrame()
        self.sep_timer.setFrameShape(QFrame.Shape.VLine)
        self.sep_timer.setStyleSheet("color: rgba(255, 255, 255, 30);")
        layout.addWidget(self.sep_timer)

        # Timer Duration Dropdown
        self.combo_timer = QComboBox()
        self.combo_timer.addItem("30 sec", 30)
        self.combo_timer.addItem("45 sec", 45)
        self.combo_timer.addItem("1 min", 60)
        self.combo_timer.addItem("2 min", 120)
        self.combo_timer.addItem("3 min", 180)
        self.combo_timer.addItem("5 min", 300)
        self.combo_timer.addItem("10 min", 600)
        self.combo_timer.addItem("🔥 Warm-up Ladder (30s->1m->5m)", "ladder_standard")
        self.combo_timer.setCurrentIndex(3)  # default 2 min
        self.combo_timer.setToolTip("Select pose duration or warm-up sequence")
        self.combo_timer.currentIndexChanged.connect(self._on_timer_changed)
        layout.addWidget(self.combo_timer)

        # Spacer
        layout.addStretch()

        # 2. Artist Tools: Flip, Grayscale, Silhouette
        self.btn_flip = QPushButton("⇄ Flip (H)")
        self.btn_flip.setCheckable(True)
        self.btn_flip.setToolTip("Mirror horizontally to check anatomy / balance")
        self.btn_flip.clicked.connect(self.flip_clicked.emit)

        self.btn_gray = QPushButton("◑ B&W (G)")
        self.btn_gray.setCheckable(True)
        self.btn_gray.setToolTip("Grayscale mode to study tonal values")
        self.btn_gray.clicked.connect(self.grayscale_clicked.emit)

        self.btn_silh = QPushButton("▲ Silh (C)")
        self.btn_silh.setCheckable(True)
        self.btn_silh.setToolTip("High contrast silhouette mode")
        self.btn_silh.clicked.connect(self.silhouette_clicked.emit)

        layout.addWidget(self.btn_flip)
        layout.addWidget(self.btn_gray)
        layout.addWidget(self.btn_silh)

        # 3. Canvas Specific Controls (BeeRef mode)
        self.btn_fit = QPushButton("⛶ Fit All")
        self.btn_fit.setToolTip("Center and fit all images in view")
        self.btn_fit.clicked.connect(self.fit_all_clicked.emit)

        self.btn_arrange = QPushButton("⊞ Tile Grid")
        self.btn_arrange.setToolTip("Neatly tile images in a grid")
        self.btn_arrange.clicked.connect(self.auto_arrange_clicked.emit)

        layout.addWidget(self.btn_fit)
        layout.addWidget(self.btn_arrange)

        # General styling
        for w in (self.btn_prev, self.btn_play, self.btn_next, self.btn_restart,
                 self.btn_flip, self.btn_gray, self.btn_silh, self.btn_fit, self.btn_arrange):
            w.setFixedHeight(30)
            w.setCursor(Qt.CursorShape.PointingHandCursor)

        self._update_styles()
        self.set_mode('action')

    def set_mode(self, mode: str):
        self.mode = mode
        is_action = (mode == 'action')

        # Action mode widgets
        self.btn_prev.setVisible(is_action)
        self.btn_play.setVisible(is_action)
        self.btn_next.setVisible(is_action)
        self.btn_restart.setVisible(is_action)
        self.sep_timer.setVisible(is_action)
        self.combo_timer.setVisible(is_action)

        # Canvas mode widgets
        self.btn_fit.setVisible(not is_action)
        self.btn_arrange.setVisible(not is_action)

    def set_paused(self, paused: bool):
        self.is_paused = paused
        if paused:
            self.btn_play.setText("▶ Play")
            self.btn_play.setStyleSheet("background-color: #238636; color: white; font-weight: bold;")
        else:
            self.btn_play.setText("⏸ Pause")
            self.btn_play.setStyleSheet("background-color: #f0883e; color: black; font-weight: bold;")

    def _on_timer_changed(self, index: int):
        val = self.combo_timer.currentData()
        if val == "ladder_standard":
            # 5 x 30s -> 5 x 1m -> 2 x 5m
            ladder = [(30, 5), (60, 5), (300, 2)]
            self.ladder_selected.emit(ladder)
        else:
            self.duration_selected.emit(int(val))

    def _update_styles(self):
        style = """
            QPushButton {
                background-color: rgba(255, 255, 255, 12);
                border: 1px solid rgba(255, 255, 255, 22);
                border-radius: 6px;
                color: #c9d1d9;
                font-family: 'Segoe UI';
                font-size: 11px;
                padding: 0 10px;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 24);
                color: #ffffff;
            }
            QPushButton:checked {
                background-color: #7e57f6;
                border-color: #906bf9;
                color: #ffffff;
            }
            QComboBox {
                background-color: #21262d;
                border: 1px solid rgba(255, 255, 255, 25);
                border-radius: 6px;
                color: #c9d1d9;
                font-size: 11px;
                padding: 2px 8px;
                min-width: 90px;
                height: 26px;
            }
            QComboBox QAbstractItemView {
                background-color: #161b22;
                color: #c9d1d9;
                selection-background-color: #7e57f6;
                border: 1px solid #30363d;
            }
        """
        self.setStyleSheet(style)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(22, 24, 29, 240))
        painter.setPen(QPen(QColor(255, 255, 255, 15), 1))
        painter.drawLine(0, 0, self.width(), 0)
