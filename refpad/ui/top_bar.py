"""
Top Navigation and Header Bar:
- Mode Switcher (Line of Action vs BeeRef Board)
- Drag Handle for moving the floating window
- Source indicator badge
- Pin / Always-on-top toggle
- Opacity slider
- Minimize / Close
"""
from PySide6.QtWidgets import QWidget, QHBoxLayout, QPushButton, QLabel, QSlider, QFrame
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QBrush, QPen
from PySide6.QtCore import Qt, Signal, QPointF

class TopBar(QWidget):
    mode_changed = Signal(str)         # 'action' or 'canvas'
    pin_toggled = Signal(bool)         # is_always_on_top
    opacity_changed = Signal(float)    # 0.2 to 1.0
    minimize_requested = Signal()
    close_requested = Signal()
    open_folder_requested = Signal()
    open_pdf_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(46)
        self.active_mode = 'action'
        self.is_pinned = True

        self._init_ui()

    def _init_ui(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 6, 12, 6)
        layout.setSpacing(8)

        # Mode Switcher Pills
        self.btn_action = QPushButton("⏱ Practice (Line of Action)")
        self.btn_canvas = QPushButton("🖼 Board (BeeRef)")

        for btn in (self.btn_action, self.btn_canvas):
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setFixedHeight(30)

        self.btn_action.setChecked(True)
        self.btn_action.clicked.connect(lambda: self.set_mode('action'))
        self.btn_canvas.clicked.connect(lambda: self.set_mode('canvas'))

        layout.addWidget(self.btn_action)
        layout.addWidget(self.btn_canvas)

        # Separator
        sep1 = QFrame()
        sep1.setFrameShape(QFrame.Shape.VLine)
        sep1.setStyleSheet("color: rgba(255, 255, 255, 30);")
        layout.addWidget(sep1)

        # Source Button / Label
        self.btn_load_folder = QPushButton("📁 Folder")
        self.btn_load_folder.setToolTip("Load a folder of image references")
        self.btn_load_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_load_folder.setFixedHeight(30)
        self.btn_load_folder.clicked.connect(self.open_folder_requested.emit)
        layout.addWidget(self.btn_load_folder)

        self.btn_load_pdf = QPushButton("📄 PDF")
        self.btn_load_pdf.setToolTip("Load an art or anatomy PDF book")
        self.btn_load_pdf.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_load_pdf.setFixedHeight(30)
        self.btn_load_pdf.clicked.connect(self.open_pdf_requested.emit)
        layout.addWidget(self.btn_load_pdf)

        # Spacer to allow dragging empty region
        layout.addStretch()

        # Opacity Slider
        lbl_opacity = QLabel("Opacity")
        lbl_opacity.setStyleSheet("color: #8b949e; font-size: 11px;")
        layout.addWidget(lbl_opacity)

        self.slider_opacity = QSlider(Qt.Orientation.Horizontal)
        self.slider_opacity.setRange(20, 100)
        self.slider_opacity.setValue(100)
        self.slider_opacity.setFixedWidth(70)
        self.slider_opacity.setToolTip("Adjust window transparency (20% - 100%)")
        self.slider_opacity.valueChanged.connect(lambda val: self.opacity_changed.emit(val / 100.0))
        layout.addWidget(self.slider_opacity)

        # Always-On-Top Pin Button
        self.btn_pin = QPushButton("📌")
        self.btn_pin.setToolTip("Toggle Always On Top")
        self.btn_pin.setCheckable(True)
        self.btn_pin.setChecked(True)
        self.btn_pin.setFixedSize(30, 30)
        self.btn_pin.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pin.clicked.connect(self._toggle_pin)
        layout.addWidget(self.btn_pin)

        # Minimize Button
        btn_min = QPushButton("—")
        btn_min.setFixedSize(28, 28)
        btn_min.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_min.setStyleSheet("QPushButton { border-radius: 6px; font-weight: bold; }")
        btn_min.clicked.connect(self.minimize_requested.emit)
        layout.addWidget(btn_min)

        # Close Button
        btn_close = QPushButton("✕")
        btn_close.setFixedSize(28, 28)
        btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_close.setStyleSheet("QPushButton { border-radius: 6px; color: #ff7b72; font-weight: bold; } QPushButton:hover { background-color: #da3633; color: white; }")
        btn_close.clicked.connect(self.close_requested.emit)
        layout.addWidget(btn_close)

        self._update_styles()

    def set_mode(self, mode: str):
        self.active_mode = mode
        self.btn_action.setChecked(mode == 'action')
        self.btn_canvas.setChecked(mode == 'canvas')
        self._update_styles()
        self.mode_changed.emit(mode)

    def toggle_mode(self):
        new_mode = 'canvas' if self.active_mode == 'action' else 'action'
        self.set_mode(new_mode)

    def _toggle_pin(self):
        self.is_pinned = self.btn_pin.isChecked()
        self.pin_toggled.emit(self.is_pinned)

    def _update_styles(self):
        base_btn = """
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
                font-weight: 600;
            }
        """
        self.setStyleSheet(base_btn)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(22, 24, 29, 240))
        painter.setPen(QPen(QColor(255, 255, 255, 15), 1))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
