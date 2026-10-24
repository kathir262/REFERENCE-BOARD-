"""
Main Floating Window for RefPad (Modern Glass Aesthetic).
Full-bleed edge-to-edge canvas with floating auto-dimming glass dock,
segmented mode switcher, and multi-touch / tablet stylus integration.
"""
from typing import List, Optional
from PySide6.QtWidgets import (
    QWidget, QStackedWidget, QFileDialog, QMessageBox, QMenu, QApplication, QPushButton
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QKeyEvent, QMouseEvent, QCursor
)
from PySide6.QtCore import Qt, QPoint, QRect, Signal, QRectF

from refpad.engine.source_manager import SourceManager
from refpad.engine.session_engine import SessionEngine
from refpad.engine.audio import SoundCue
from refpad.models.item import RefItem
from refpad.ui.widgets import SegmentedPillSwitch
from refpad.ui.floating_dock import FloatingDock
from refpad.ui.action_view import ActionView
from refpad.ui.canvas_view import CanvasView

RESIZE_MARGIN = 10

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        # Frameless, Always-on-top, Translucent window
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)

        self.resize(760, 580)
        self.setMinimumSize(400, 300)

        # Core Engines
        self.source_manager = SourceManager()
        self.session_engine = SessionEngine(self)
        self.sound_cue = SoundCue(self)

        # Window Drag & Resize state
        self.drag_position: Optional[QPoint] = None
        self.resizing_edge: Optional[str] = None
        self.resize_start_geometry: Optional[QRect] = None
        self.resize_start_mouse: Optional[QPoint] = None

        self._init_ui()
        self._connect_signals()

    def _init_ui(self):
        # 1. Edge-to-Edge Central Stacked View
        self.stacked_views = QStackedWidget(self)
        self.action_view = ActionView(self)
        self.canvas_view = CanvasView(self)

        self.stacked_views.addWidget(self.action_view)  # index 0: Line of Action
        self.stacked_views.addWidget(self.canvas_view)  # index 1: BeeRef Board

        # 2. Floating Top Mode Switcher
        self.pill_switch = SegmentedPillSwitch(self)

        # 3. Floating Close & Min buttons (Top Right)
        self.btn_close = QPushButton("✕", self)
        self.btn_close.setFixedSize(26, 26)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.setStyleSheet("""
            QPushButton {
                background-color: rgba(20, 22, 28, 180);
                border: 1px solid rgba(255, 255, 255, 22);
                border-radius: 6px;
                color: #ff7b72;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #da3633;
                color: white;
            }
        """)
        self.btn_close.clicked.connect(self.close)

        self.btn_min = QPushButton("—", self)
        self.btn_min.setFixedSize(26, 26)
        self.btn_min.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_min.setStyleSheet("""
            QPushButton {
                background-color: rgba(20, 22, 28, 180);
                border: 1px solid rgba(255, 255, 255, 22);
                border-radius: 6px;
                color: #c9d1d9;
                font-size: 11px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 30);
                color: white;
            }
        """)
        self.btn_min.clicked.connect(self.showMinimized)

        # 4. Floating Glass Bottom Dock
        self.floating_dock = FloatingDock(self)

    def _connect_signals(self):
        # Top Mode Switch
        self.pill_switch.mode_changed.connect(self._on_mode_changed)

        # Activity detection wakes up the dock
        self.action_view.user_activity_detected.connect(self.floating_dock.wake_dock)
        self.canvas_view.user_activity_detected.connect(self.floating_dock.wake_dock)

        # Drag & Drop onto views
        self.action_view.files_dropped.connect(self.handle_incoming_files)
        self.canvas_view.files_dropped.connect(self.handle_incoming_files)
        self.canvas_view.start_session_with_item.connect(self._on_start_session_with_item)

        # Floating Dock actions
        self.floating_dock.play_pause_clicked.connect(self.session_engine.toggle_pause)
        self.floating_dock.next_clicked.connect(self.session_engine.next_pose)
        self.floating_dock.prev_clicked.connect(self.session_engine.prev_pose)
        self.floating_dock.duration_selected.connect(self.session_engine.set_duration)
        self.floating_dock.ladder_selected.connect(self.session_engine.set_ladder_mode)
        self.floating_dock.open_folder_requested.connect(self.open_folder_dialog)
        self.floating_dock.open_pdf_requested.connect(self.open_pdf_dialog)
        self.floating_dock.pin_toggled.connect(self._on_pin_toggled)

        # Filters
        self.floating_dock.flip_clicked.connect(self._toggle_flip)
        self.floating_dock.grayscale_clicked.connect(self._toggle_grayscale)

        # Canvas actions
        self.floating_dock.fit_all_clicked.connect(self.canvas_view.fit_all_items)
        self.floating_dock.auto_arrange_clicked.connect(lambda: self.canvas_view.auto_arrange_items())

        # Session Engine signals
        self.session_engine.tick.connect(self.action_view.timer_hud.update_time)
        self.session_engine.pose_changed.connect(self._on_pose_changed)
        self.session_engine.session_paused.connect(self._on_session_paused)
        self.session_engine.chime_requested.connect(self.sound_cue.play_chime)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        h = self.height()

        # Stack fills window completely
        self.stacked_views.setGeometry(0, 0, w, h)

        # Center Top Mode Switcher
        switch_w = self.pill_switch.sizeHint().width() + 10
        self.pill_switch.setGeometry(int((w - switch_w) / 2), 12, switch_w, 34)

        # Top-right window buttons
        self.btn_close.move(w - 36, 12)
        self.btn_min.move(w - 68, 12)

        # Center Bottom Floating Dock
        dock_w = self.floating_dock.sizeHint().width()
        self.floating_dock.setGeometry(int((w - dock_w) / 2), h - 60, dock_w, 48)

    def _on_mode_changed(self, mode: str):
        if mode == 'action':
            self.stacked_views.setCurrentWidget(self.action_view)
            self.floating_dock.set_mode('action')
        else:
            self.stacked_views.setCurrentWidget(self.canvas_view)
            self.floating_dock.set_mode('canvas')
        self.resizeEvent(None)

    def _on_pin_toggled(self, pinned: bool):
        flags = self.windowFlags()
        if pinned:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    def _on_pose_changed(self, index: int, item: RefItem, duration: int):
        self.action_view.set_item(item)
        self.action_view.timer_hud.update_pose_info(index, len(self.source_manager.items), duration)
        self.floating_dock.btn_flip.setActive(item.is_flipped_h)
        self.floating_dock.btn_gray.setActive(item.is_grayscale)

    def _on_session_paused(self, is_paused: bool):
        self.floating_dock.set_paused(is_paused)
        self.action_view.timer_hud.set_paused(is_paused)

    def _toggle_flip(self):
        item = self.session_engine.current_item
        if item:
            item.toggle_flip()
            self.action_view.refresh_transforms()
            self.floating_dock.btn_flip.setActive(item.is_flipped_h)

    def _toggle_grayscale(self):
        item = self.session_engine.current_item
        if item:
            item.toggle_grayscale()
            self.action_view.refresh_transforms()
            self.floating_dock.btn_gray.setActive(item.is_grayscale)

    def _on_start_session_with_item(self, target_item: RefItem):
        try:
            idx = self.source_manager.items.index(target_item)
            self.session_engine.current_index = idx
        except ValueError:
            pass
        self.pill_switch.set_mode('action')
        self.session_engine.start_session()

    def open_folder_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Image Reference Folder")
        if folder:
            items = self.source_manager.load_folder(folder, recursive=True, shuffle=True)
            self._apply_loaded_items(items)

    def open_pdf_dialog(self):
        pdf_path, _ = QFileDialog.getOpenFileName(self, "Open Art or Anatomy PDF", "", "PDF Files (*.pdf)")
        if pdf_path:
            items = self.source_manager.load_pdf(pdf_path)
            self._apply_loaded_items(items)

    def handle_incoming_files(self, paths: List[str]):
        import os
        if len(paths) == 1 and os.path.isdir(paths[0]):
            items = self.source_manager.load_folder(paths[0], recursive=True, shuffle=True)
        elif len(paths) == 1 and paths[0].lower().endswith('.pdf'):
            items = self.source_manager.load_pdf(paths[0])
        else:
            items = self.source_manager.add_files(paths)
        self._apply_loaded_items(items)

    def _apply_loaded_items(self, items: List[RefItem]):
        if not items:
            QMessageBox.information(self, "No Images Found", "No valid image files or PDF pages were found.")
            return

        self.session_engine.set_items(items)
        self.canvas_view.add_ref_items(items, auto_tile=True)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()

        if key == Qt.Key.Key_Tab:
            self.pill_switch.toggle_mode()
            event.accept()
            return
        elif key == Qt.Key.Key_Space:
            self.session_engine.toggle_pause()
            event.accept()
            return
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_D):
            self.session_engine.next_pose()
            event.accept()
            return
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_A):
            self.session_engine.prev_pose()
            event.accept()
            return
        elif key == Qt.Key.Key_R:
            self.session_engine.restart_current_pose()
            event.accept()
            return
        elif key == Qt.Key.Key_H:
            self._toggle_flip()
            event.accept()
            return
        elif key == Qt.Key.Key_G:
            self._toggle_grayscale()
            event.accept()
            return
        elif key == Qt.Key.Key_T:
            self.floating_dock.btn_pin.click()
            event.accept()
            return
        elif key == Qt.Key.Key_F:
            if self.pill_switch.current_mode == 'canvas':
                self.canvas_view.fit_all_items()
            else:
                self.action_view.zoom_factor = 1.0
                self.action_view.pan_offset = QPoint(0, 0)
                self.action_view.update()
            event.accept()
            return
        elif key == Qt.Key.Key_BracketLeft:
            op = max(0.2, self.windowOpacity() - 0.1)
            self.setWindowOpacity(op)
            event.accept()
            return
        elif key == Qt.Key.Key_BracketRight:
            op = min(1.0, self.windowOpacity() + 0.1)
            self.setWindowOpacity(op)
            event.accept()
            return

        super().keyPressEvent(event)

    # Window Resizing and Dragging
    def mousePressEvent(self, event: QMouseEvent):
        self.floating_dock.wake_dock()
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self._get_edge(event.pos())
            if edge:
                self.resizing_edge = edge
                self.resize_start_geometry = self.geometry()
                self.resize_start_mouse = event.globalPosition().toPoint()
            elif event.pos().y() <= 45 or event.modifiers() & Qt.KeyboardModifier.AltModifier:
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        self.floating_dock.wake_dock()
        if self.resizing_edge and self.resize_start_geometry and self.resize_start_mouse:
            diff = event.globalPosition().toPoint() - self.resize_start_mouse
            geo = QRect(self.resize_start_geometry)

            if "right" in self.resizing_edge:
                geo.setRight(geo.right() + diff.x())
            if "bottom" in self.resizing_edge:
                geo.setBottom(geo.bottom() + diff.y())
            if "left" in self.resizing_edge:
                geo.setLeft(geo.left() + diff.x())
            if "top" in self.resizing_edge:
                geo.setTop(geo.top() + diff.y())

            if geo.width() >= self.minimumWidth() and geo.height() >= self.minimumHeight():
                self.setGeometry(geo)
            event.accept()
            return
        elif self.drag_position:
            self.move(event.globalPosition().toPoint() - self.drag_position)
            event.accept()
            return
        else:
            edge = self._get_edge(event.pos())
            if edge in ("top_left", "bottom_right"):
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif edge in ("top_right", "bottom_left"):
                self.setCursor(Qt.CursorShape.SizeBDiagCursor)
            elif edge in ("left", "right"):
                self.setCursor(Qt.CursorShape.SizeHorCursor)
            elif edge in ("top", "bottom"):
                self.setCursor(Qt.CursorShape.SizeVerCursor)
            else:
                self.setCursor(Qt.CursorShape.ArrowCursor)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        self.drag_position = None
        self.resizing_edge = None
        self.resize_start_geometry = None
        self.resize_start_mouse = None
        super().mouseReleaseEvent(event)

    def _get_edge(self, pos: QPoint) -> Optional[str]:
        m = RESIZE_MARGIN
        w = self.width()
        h = self.height()
        x = pos.x()
        y = pos.y()

        on_left = x <= m
        on_right = x >= w - m
        on_top = y <= m
        on_bottom = y >= h - m

        if on_top and on_left:
            return "top_left"
        if on_top and on_right:
            return "top_right"
        if on_bottom and on_left:
            return "bottom_left"
        if on_bottom and on_right:
            return "bottom_right"
        if on_left:
            return "left"
        if on_right:
            return "right"
        if on_top:
            return "top"
        if on_bottom:
            return "bottom"
        return None

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.rect().adjusted(1, 1, -1, -1)
        # Deep slate background card with sleek rounded border
        painter.setBrush(QBrush(QColor(13, 14, 18)))
        painter.setPen(QPen(QColor(255, 255, 255, 30), 1.2))
        painter.drawRoundedRect(rect, 14, 14)
