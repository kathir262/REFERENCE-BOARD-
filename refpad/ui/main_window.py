"""
Main Floating Window for RefPad.
Frameless, rounded corners, draggable, resizable, always-on-top picture-in-picture.
Houses both Line of Action mode and BeeRef infinite board mode.
"""
from typing import List, Optional
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QStackedWidget, QFileDialog, QMessageBox, QApplication
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QKeyEvent, QMouseEvent, QCursor
)
from PySide6.QtCore import Qt, QPoint, QRect, Signal

from refpad.engine.source_manager import SourceManager
from refpad.engine.session_engine import SessionEngine
from refpad.engine.audio import SoundCue
from refpad.models.item import RefItem
from refpad.ui.top_bar import TopBar
from refpad.ui.bottom_bar import BottomBar
from refpad.ui.action_view import ActionView
from refpad.ui.canvas_view import CanvasView

RESIZE_MARGIN = 8

class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        # Frameless and Always-on-top
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)

        self.resize(720, 560)
        self.setMinimumSize(420, 320)

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
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(1, 1, 1, 1)
        main_layout.setSpacing(0)

        # 1. Top Navigation & Header Bar
        self.top_bar = TopBar(self)
        main_layout.addWidget(self.top_bar)

        # 2. Central Stacked Views
        self.stacked_views = QStackedWidget(self)

        self.action_view = ActionView(self)
        self.canvas_view = CanvasView(self)

        self.stacked_views.addWidget(self.action_view)  # index 0: Line of Action
        self.stacked_views.addWidget(self.canvas_view)  # index 1: BeeRef Board

        main_layout.addWidget(self.stacked_views)

        # 3. Bottom Controls Bar
        self.bottom_bar = BottomBar(self)
        main_layout.addWidget(self.bottom_bar)

    def _connect_signals(self):
        # Top Bar
        self.top_bar.mode_changed.connect(self._on_mode_changed)
        self.top_bar.pin_toggled.connect(self._on_pin_toggled)
        self.top_bar.opacity_changed.connect(self._on_opacity_changed)
        self.top_bar.minimize_requested.connect(self.showMinimized)
        self.top_bar.close_requested.connect(self.close)
        self.top_bar.open_folder_requested.connect(self.open_folder_dialog)
        self.top_bar.open_pdf_requested.connect(self.open_pdf_dialog)

        # Drag & Drop onto views
        self.action_view.files_dropped.connect(self.handle_incoming_files)
        self.canvas_view.files_dropped.connect(self.handle_incoming_files)
        self.canvas_view.start_session_with_item.connect(self._on_start_session_with_item)

        # Bottom Bar Line of Action controls
        self.bottom_bar.play_pause_clicked.connect(self.session_engine.toggle_pause)
        self.bottom_bar.next_clicked.connect(self.session_engine.next_pose)
        self.bottom_bar.prev_clicked.connect(self.session_engine.prev_pose)
        self.bottom_bar.restart_clicked.connect(self.session_engine.restart_current_pose)
        self.bottom_bar.duration_selected.connect(self.session_engine.set_duration)
        self.bottom_bar.ladder_selected.connect(self.session_engine.set_ladder_mode)

        # Filter toggles
        self.bottom_bar.flip_clicked.connect(self._toggle_flip)
        self.bottom_bar.grayscale_clicked.connect(self._toggle_grayscale)
        self.bottom_bar.silhouette_clicked.connect(self._toggle_silhouette)

        # Canvas mode actions
        self.bottom_bar.fit_all_clicked.connect(self.canvas_view.fit_all_items)
        self.bottom_bar.auto_arrange_clicked.connect(lambda: self.canvas_view.auto_arrange_items())

        # Session Engine signals
        self.session_engine.tick.connect(self.action_view.timer_hud.update_time)
        self.session_engine.pose_changed.connect(self._on_pose_changed)
        self.session_engine.session_paused.connect(self._on_session_paused)
        self.session_engine.chime_requested.connect(self.sound_cue.play_chime)

    def _on_mode_changed(self, mode: str):
        if mode == 'action':
            self.stacked_views.setCurrentWidget(self.action_view)
            self.bottom_bar.set_mode('action')
        else:
            self.stacked_views.setCurrentWidget(self.canvas_view)
            self.bottom_bar.set_mode('canvas')

    def _on_pin_toggled(self, pinned: bool):
        flags = self.windowFlags()
        if pinned:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        else:
            flags &= ~Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.show()

    def _on_opacity_changed(self, opacity: float):
        self.setWindowOpacity(opacity)

    def _on_pose_changed(self, index: int, item: RefItem, duration: int):
        self.action_view.set_item(item)
        self.action_view.timer_hud.update_pose_info(index, len(self.source_manager.items), duration)
        # Update filter button states to reflect current item
        self.bottom_bar.btn_flip.setChecked(item.is_flipped_h)
        self.bottom_bar.btn_gray.setChecked(item.is_grayscale)
        self.bottom_bar.btn_silh.setChecked(item.is_silhouette)

    def _on_session_paused(self, is_paused: bool):
        self.bottom_bar.set_paused(is_paused)
        self.action_view.timer_hud.set_paused(is_paused)

    def _toggle_flip(self):
        item = self.session_engine.current_item
        if item:
            item.toggle_flip()
            self.action_view.refresh_transforms()
            self.bottom_bar.btn_flip.setChecked(item.is_flipped_h)

    def _toggle_grayscale(self):
        item = self.session_engine.current_item
        if item:
            item.toggle_grayscale()
            self.action_view.refresh_transforms()
            self.bottom_bar.btn_gray.setChecked(item.is_grayscale)

    def _toggle_silhouette(self):
        item = self.session_engine.current_item
        if item:
            item.toggle_silhouette()
            self.action_view.refresh_transforms()
            self.bottom_bar.btn_silh.setChecked(item.is_silhouette)

    def _on_start_session_with_item(self, target_item: RefItem):
        """When double clicking an item in BeeRef board, start session from it."""
        try:
            idx = self.source_manager.items.index(target_item)
            self.session_engine.current_index = idx
        except ValueError:
            pass
        self.top_bar.set_mode('action')
        self.session_engine.start_session()

    # Ingestion Handlers
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
        """Triggered when files or folders are dropped onto the window."""
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

        # 1. Update Line of Action session
        self.session_engine.set_items(items)

        # 2. Update BeeRef Canvas board
        self.canvas_view.add_ref_items(items, auto_tile=True)

    # Keyboard Express Keys for Artists
    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()

        if key == Qt.Key.Key_Tab:
            self.top_bar.toggle_mode()
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
        elif key == Qt.Key.Key_C:
            self._toggle_silhouette()
            event.accept()
            return
        elif key == Qt.Key.Key_T:
            self.top_bar.btn_pin.click()
            event.accept()
            return
        elif key == Qt.Key.Key_BracketLeft:
            new_val = max(20, self.top_bar.slider_opacity.value() - 10)
            self.top_bar.slider_opacity.setValue(new_val)
            event.accept()
            return
        elif key == Qt.Key.Key_BracketRight:
            new_val = min(100, self.top_bar.slider_opacity.value() + 10)
            self.top_bar.slider_opacity.setValue(new_val)
            event.accept()
            return

        super().keyPressEvent(event)

    # Window Resizing and Dragging
    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            edge = self._get_edge(event.pos())
            if edge:
                self.resizing_edge = edge
                self.resize_start_geometry = self.geometry()
                self.resize_start_mouse = event.globalPosition().toPoint()
            elif event.pos().y() <= self.top_bar.height() + 10:
                self.drag_position = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
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
            # Update cursor for edges
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

        # Sleek dark window background with subtle border
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setBrush(QBrush(QColor(18, 20, 24)))
        painter.setPen(QPen(QColor(255, 255, 255, 28), 1.2))
        painter.drawRoundedRect(rect, 10, 10)
