"""
Main Floating Window for RefPad.

Architecture:
  - Visible DRAG HANDLE at top (30px strip with grip dots) — click & drag to move window
  - ALL 4 edges + 4 corners resize via per-child event-filter intercept
  - Zero hardcoded purple — everything uses get_current_theme()
  - Full BeeRef operations: Save, Open, Paste, Align, Normalize, Export, Sticky Notes
  - Theme switcher: Black & White, Rose, Midnight, Paper
"""
import os
from typing import List, Optional
from PySide6.QtWidgets import (
    QWidget, QStackedWidget, QFileDialog, QMessageBox, QApplication, QPushButton, QLabel
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QKeyEvent, QMouseEvent, QPainterPath
)
from PySide6.QtCore import Qt, QPoint, QRect, QRectF, QEvent, Signal

from refpad.engine.source_manager import SourceManager
from refpad.engine.session_engine import SessionEngine
from refpad.engine.audio import SoundCue
from refpad.models.item import RefItem
from refpad.models.board import BoardManager, base64_to_pixmap
from refpad.ui.widgets import SegmentedPillSwitch
from refpad.ui.floating_dock import FloatingDock
from refpad.ui.action_view import ActionView
from refpad.ui.canvas_view import CanvasView
from refpad.ui.canvas_item import CanvasRefItem, CanvasTextItem
from refpad.ui.themes import get_current_theme, set_current_theme, THEMES

RESIZE_MARGIN = 10   # px from edge to trigger resize
DRAG_HANDLE_H = 32   # height of the top drag handle strip


class TitleBar(QWidget):
    """
    Visible drag handle at the top of the window.
    Thin strip with grip dots in the center, mode switch centered, close/min on right.
    """
    close_clicked = Signal()
    min_clicked = Signal()

    def __init__(self, pill_switch: SegmentedPillSwitch, parent=None):
        super().__init__(parent)
        self.setFixedHeight(DRAG_HANDLE_H)
        self.setMouseTracking(True)
        self.pill_switch = pill_switch

        # Close button
        self.btn_close = QPushButton("✕", self)
        self.btn_close.setFixedSize(22, 22)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.close_clicked.emit)

        # Minimize button
        self.btn_min = QPushButton("—", self)
        self.btn_min.setFixedSize(22, 22)
        self.btn_min.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_min.clicked.connect(self.min_clicked.emit)

    def apply_theme(self):
        theme = get_current_theme()
        base_btn = f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {theme.border};
                border-radius: 5px;
                color: {theme.text_muted};
                font-size: 10px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {theme.accent};
                color: {theme.bg_dark};
                border-color: {theme.accent};
            }}
        """
        self.btn_close.setStyleSheet(base_btn)
        self.btn_min.setStyleSheet(base_btn)
        self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w = self.width()
        # Close far right, min next to it
        self.btn_close.move(w - 28, 5)
        self.btn_min.move(w - 54, 5)

        # Pill switch centered in title bar
        sw = self.pill_switch.sizeHint().width() + 8
        self.pill_switch.setGeometry((w - sw) // 2, 1, sw, DRAG_HANDLE_H - 2)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        theme = get_current_theme()

        # Solid bar background
        painter.fillRect(self.rect(), QColor(theme.bg_card))

        # Bottom border line
        painter.setPen(QPen(QColor(theme.border), 1))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)

        # Grip dots (centered, left of switch)
        dot_col = QColor(theme.text_muted)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(dot_col))
        cx = 28
        cy = self.height() // 2
        for dx in (-5, 0, 5):
            for dy in (-3, 3):
                painter.drawEllipse(QRectF(cx + dx - 1.5, cy + dy - 1.5, 3, 3))


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.SubWindow
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.resize(780, 600)
        self.setMinimumSize(380, 280)

        # Core Engines
        self.source_manager = SourceManager()
        self.session_engine = SessionEngine(self)
        self.sound_cue = SoundCue(self)

        # Resize state
        self.resizing_edge: Optional[str] = None
        self.resize_start_geometry: Optional[QRect] = None
        self.resize_start_mouse: Optional[QPoint] = None

        # Drag state (from title bar only)
        self.is_dragging_window: bool = False
        self.drag_start_global: Optional[QPoint] = None
        self.drag_start_win_pos: Optional[QPoint] = None

        self.current_board_path: Optional[str] = None

        self._init_ui()
        self._connect_signals()
        self._install_all_event_filters()

    def _init_ui(self):
        # Mode switch pill lives inside the title bar
        self.pill_switch = SegmentedPillSwitch(self)

        # Title bar (drag handle)
        self.title_bar = TitleBar(self.pill_switch, self)
        self.title_bar.close_clicked.connect(self.close)
        self.title_bar.min_clicked.connect(self.showMinimized)

        # Central stacked views
        self.stacked_views = QStackedWidget(self)
        self.action_view = ActionView(self)
        self.canvas_view = CanvasView(self)
        self.stacked_views.addWidget(self.action_view)
        self.stacked_views.addWidget(self.canvas_view)

        # Floating bottom dock
        self.floating_dock = FloatingDock(self)

        # Apply theme to title bar
        self.title_bar.apply_theme()

    def _install_all_event_filters(self):
        """Install on every child so edge moves are captured everywhere."""
        self.title_bar.installEventFilter(self)
        self.stacked_views.installEventFilter(self)
        self.action_view.installEventFilter(self)
        self.canvas_view.installEventFilter(self)
        self.canvas_view.viewport().installEventFilter(self)
        self.floating_dock.installEventFilter(self)

    def _connect_signals(self):
        self.pill_switch.mode_changed.connect(self._on_mode_changed)

        self.action_view.user_activity_detected.connect(self.floating_dock.wake_dock)
        self.canvas_view.user_activity_detected.connect(self.floating_dock.wake_dock)

        self.action_view.files_dropped.connect(self.handle_incoming_files)
        self.canvas_view.files_dropped.connect(self.handle_incoming_files)
        self.canvas_view.start_session_with_item.connect(self._on_start_session_with_item)

        self.floating_dock.play_pause_clicked.connect(self.session_engine.toggle_pause)
        self.floating_dock.next_clicked.connect(self.session_engine.next_pose)
        self.floating_dock.prev_clicked.connect(self.session_engine.prev_pose)
        self.floating_dock.duration_selected.connect(self.session_engine.set_duration)
        self.floating_dock.ladder_selected.connect(self.session_engine.set_ladder_mode)
        self.floating_dock.open_folder_requested.connect(self.open_folder_dialog)
        self.floating_dock.open_pdf_requested.connect(self.open_pdf_dialog)
        self.floating_dock.save_board_requested.connect(self.save_board_dialog)
        self.floating_dock.open_board_requested.connect(self.open_board_dialog)
        self.floating_dock.export_image_requested.connect(self.export_board_dialog)
        self.floating_dock.paste_requested.connect(self.canvas_view.paste_from_clipboard)
        self.floating_dock.add_note_requested.connect(self.canvas_view.add_text_note)
        self.floating_dock.align_requested.connect(self.canvas_view.align_selected)
        self.floating_dock.normalize_requested.connect(self.canvas_view.normalize_selected)
        self.floating_dock.theme_changed.connect(self._on_theme_changed)
        self.floating_dock.pin_toggled.connect(self._on_pin_toggled)
        self.floating_dock.flip_clicked.connect(self._toggle_flip)
        self.floating_dock.grayscale_clicked.connect(self._toggle_grayscale)
        self.floating_dock.fit_all_clicked.connect(self.canvas_view.fit_all_items)
        self.floating_dock.auto_arrange_clicked.connect(lambda: self.canvas_view.auto_arrange_items())

        self.session_engine.tick.connect(self.action_view.timer_hud.update_time)
        self.session_engine.pose_changed.connect(self._on_pose_changed)
        self.session_engine.session_paused.connect(self._on_session_paused)
        self.session_engine.chime_requested.connect(self.sound_cue.play_chime)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        m = RESIZE_MARGIN  # leave perimeter for resize

        # Title bar full width at top
        self.title_bar.setGeometry(m, m, w - m * 2, DRAG_HANDLE_H)

        # Stacked views fill the rest (below title bar, above dock)
        content_top = m + DRAG_HANDLE_H
        content_h = h - content_top - 60 - m
        self.stacked_views.setGeometry(m, content_top, w - m * 2, content_h)

        # Dock centered at bottom
        dock_w = max(200, min(self.floating_dock.sizeHint().width(), w - m * 2))
        self.floating_dock.setGeometry((w - dock_w) // 2, h - 60, dock_w, 48)

    # ---------------------------------------------------------------
    # Event filter — runs on MainWindow itself AND all child widgets
    # to intercept edge/corner resize mouse events.
    # ---------------------------------------------------------------
    def eventFilter(self, watched, event: QEvent) -> bool:
        t = event.type()

        if t == QEvent.Type.MouseButtonPress:
            ev: QMouseEvent = event
            if ev.button() == Qt.MouseButton.LeftButton:
                global_pos = ev.globalPosition().toPoint()
                local_pos = self.mapFromGlobal(global_pos)
                edge = self._get_edge(local_pos)

                if edge:
                    # Start resize
                    self.resizing_edge = edge
                    self.resize_start_geometry = self.geometry()
                    self.resize_start_mouse = global_pos
                    self.setCursor(self._cursor_for_edge(edge))
                    return True

                # Title bar drag
                if watched is self.title_bar and not edge:
                    self.is_dragging_window = True
                    self.drag_start_global = global_pos
                    self.drag_start_win_pos = self.pos()
                    self.title_bar.setCursor(Qt.CursorShape.ClosedHandCursor)
                    return True

        elif t == QEvent.Type.MouseMove:
            ev: QMouseEvent = event
            global_pos = ev.globalPosition().toPoint()
            local_pos = self.mapFromGlobal(global_pos)

            if self.resizing_edge:
                self._perform_resize(global_pos)
                return True

            if self.is_dragging_window and self.drag_start_global and self.drag_start_win_pos:
                delta = global_pos - self.drag_start_global
                self.move(self.drag_start_win_pos + delta)
                return True

            # Update cursor shape even without pressing (on the outer widget only)
            if watched is self:
                edge = self._get_edge(local_pos)
                self.setCursor(self._cursor_for_edge(edge) if edge else Qt.CursorShape.ArrowCursor)

        elif t == QEvent.Type.MouseButtonRelease:
            if self.resizing_edge or self.is_dragging_window:
                self.resizing_edge = None
                self.resize_start_geometry = None
                self.resize_start_mouse = None
                self.is_dragging_window = False
                self.drag_start_global = None
                self.drag_start_win_pos = None
                self.setCursor(Qt.CursorShape.ArrowCursor)
                self.title_bar.setCursor(Qt.CursorShape.OpenHandCursor)
                return True

        return super().eventFilter(watched, event)

    def _get_edge(self, pos: QPoint) -> Optional[str]:
        m = RESIZE_MARGIN
        w, h = self.width(), self.height()
        x, y = pos.x(), pos.y()
        on_l = x <= m;  on_r = x >= w - m
        on_t = y <= m;  on_b = y >= h - m

        if on_t and on_l:  return "top_left"
        if on_t and on_r:  return "top_right"
        if on_b and on_l:  return "bottom_left"
        if on_b and on_r:  return "bottom_right"
        if on_l:           return "left"
        if on_r:           return "right"
        if on_t:           return "top"
        if on_b:           return "bottom"
        return None

    def _cursor_for_edge(self, edge: Optional[str]):
        if edge in ("top_left", "bottom_right"): return Qt.CursorShape.SizeFDiagCursor
        if edge in ("top_right", "bottom_left"): return Qt.CursorShape.SizeBDiagCursor
        if edge in ("left", "right"):            return Qt.CursorShape.SizeHorCursor
        if edge in ("top", "bottom"):            return Qt.CursorShape.SizeVerCursor
        return Qt.CursorShape.ArrowCursor

    def _perform_resize(self, global_pos: QPoint):
        if not (self.resizing_edge and self.resize_start_geometry and self.resize_start_mouse):
            return
        diff = global_pos - self.resize_start_mouse
        geo = QRect(self.resize_start_geometry)
        e = self.resizing_edge
        if "right"  in e: geo.setRight(geo.right()  + diff.x())
        if "bottom" in e: geo.setBottom(geo.bottom() + diff.y())
        if "left"   in e: geo.setLeft(geo.left()    + diff.x())
        if "top"    in e: geo.setTop(geo.top()      + diff.y())
        if geo.width() >= self.minimumWidth() and geo.height() >= self.minimumHeight():
            self.setGeometry(geo)

    # ---------------------------------------------------------------
    # Also handle mouse events directly on the MainWindow background
    # ---------------------------------------------------------------
    def mousePressEvent(self, event: QMouseEvent):
        # This fires when clicking the BORDER / BACKGROUND of the main window
        if event.button() == Qt.MouseButton.LeftButton:
            global_pos = event.globalPosition().toPoint()
            local_pos = event.pos()
            edge = self._get_edge(local_pos)
            if edge:
                self.resizing_edge = edge
                self.resize_start_geometry = self.geometry()
                self.resize_start_mouse = global_pos
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        global_pos = event.globalPosition().toPoint()
        if self.resizing_edge:
            self._perform_resize(global_pos)
            event.accept()
            return
        edge = self._get_edge(event.pos())
        self.setCursor(self._cursor_for_edge(edge) if edge else Qt.CursorShape.ArrowCursor)
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if self.resizing_edge:
            self.resizing_edge = None
            self.resize_start_geometry = None
            self.resize_start_mouse = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def contextMenuEvent(self, event):
        self.floating_dock._show_main_menu()
        event.accept()

    # ---------------------------------------------------------------
    # Mode & Theme
    # ---------------------------------------------------------------
    def _on_mode_changed(self, mode: str):
        if mode == 'action':
            self.stacked_views.setCurrentWidget(self.action_view)
            self.floating_dock.set_mode('action')
        else:
            self.stacked_views.setCurrentWidget(self.canvas_view)
            self.floating_dock.set_mode('canvas')

    def _on_theme_changed(self, theme_key: str):
        set_current_theme(theme_key)
        self.title_bar.apply_theme()
        self.floating_dock._apply_styles()
        self.pill_switch._update_styles()
        self.action_view.update()
        self.canvas_view.viewport().update()
        self.action_view.timer_hud.update()
        self.update()

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

    # ---------------------------------------------------------------
    # Board I/O
    # ---------------------------------------------------------------
    def save_board_dialog(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Save Reference Board",
            self.current_board_path or "moodboard.refpad",
            "RefPad Board (*.refpad);;BeeRef Board (*.bee)"
        )
        if file_path:
            items = [it for it in self.canvas_view.scene.items() if isinstance(it, CanvasRefItem)]
            notes = [it.toPlainText() for it in self.canvas_view.scene.items() if isinstance(it, CanvasTextItem)]
            ok = BoardManager.save_board(file_path, items, notes)
            if ok:
                self.current_board_path = file_path
                QMessageBox.information(self, "Saved", f"Board saved to {os.path.basename(file_path)}")

    def open_board_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Reference Board", "",
            "RefPad / BeeRef Board (*.refpad *.bee);;All Files (*.*)"
        )
        if not file_path:
            return
        data = BoardManager.load_board(file_path)
        if not data:
            QMessageBox.warning(self, "Error", "Failed to load board file.")
            return

        self.canvas_view.scene.clear()
        loaded_refs = []
        for item_data in data.get("items", []):
            ref = RefItem(
                source_type=item_data.get("source_type", "file"),
                file_path=item_data.get("file_path", ""),
                page_num=item_data.get("page_num", 0),
                name=item_data.get("name", ""),
                is_flipped_h=item_data.get("is_flipped_h", False),
                is_grayscale=item_data.get("is_grayscale", False)
            )
            if "embedded_data" in item_data:
                ref.in_memory_pixmap = base64_to_pixmap(item_data["embedded_data"])

            c_item = CanvasRefItem(ref)
            c_item.setPos(item_data.get("x", 0), item_data.get("y", 0))
            c_item.setScale(item_data.get("scale", 1.0))
            c_item.setRotation(item_data.get("rotation", 0.0))
            self.canvas_view.scene.addItem(c_item)
            loaded_refs.append(ref)

        for note_text in data.get("notes", []):
            self.canvas_view.add_text_note(note_text)

        self.source_manager.items = loaded_refs
        self.session_engine.set_items(loaded_refs)
        self.canvas_view.fit_all_items()
        self.current_board_path = file_path

    def export_board_dialog(self):
        file_path, _ = QFileDialog.getSaveFileName(
            self, "Export Board as Image", "moodboard.png",
            "PNG Image (*.png);;JPEG Image (*.jpg)"
        )
        if file_path:
            ok = self.canvas_view.export_canvas_image(file_path)
            if ok:
                QMessageBox.information(self, "Exported", f"Saved to {os.path.basename(file_path)}")

    def open_folder_dialog(self):
        folder = QFileDialog.getExistingDirectory(self, "Select Image Reference Folder")
        if folder:
            self._apply_loaded_items(self.source_manager.load_folder(folder, recursive=True, shuffle=True))

    def open_pdf_dialog(self):
        pdf_path, _ = QFileDialog.getOpenFileName(self, "Open PDF", "", "PDF Files (*.pdf)")
        if pdf_path:
            self._apply_loaded_items(self.source_manager.load_pdf(pdf_path))

    def handle_incoming_files(self, paths: List[str]):
        if len(paths) == 1 and os.path.isdir(paths[0]):
            items = self.source_manager.load_folder(paths[0], recursive=True, shuffle=True)
        elif len(paths) == 1 and paths[0].lower().endswith(('.refpad', '.bee')):
            self.open_board_dialog()
            return
        elif len(paths) == 1 and paths[0].lower().endswith('.pdf'):
            items = self.source_manager.load_pdf(paths[0])
        else:
            items = self.source_manager.add_files(paths)
        self._apply_loaded_items(items)

    def _apply_loaded_items(self, items: List[RefItem]):
        if not items:
            QMessageBox.information(self, "No Images Found", "No valid images or PDF pages found.")
            return
        self.session_engine.set_items(items)
        self.canvas_view.add_ref_items(items, auto_tile=True)

    # ---------------------------------------------------------------
    # Keyboard Shortcuts
    # ---------------------------------------------------------------
    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier

        if ctrl and key == Qt.Key.Key_S:
            self.save_board_dialog(); return
        if ctrl and key == Qt.Key.Key_O:
            self.open_board_dialog(); return
        if ctrl and key == Qt.Key.Key_E:
            self.export_board_dialog(); return

        if key == Qt.Key.Key_Tab:
            self.pill_switch.toggle_mode()
        elif key == Qt.Key.Key_Space:
            self.session_engine.toggle_pause()
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_D):
            self.session_engine.next_pose()
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_A):
            self.session_engine.prev_pose()
        elif key == Qt.Key.Key_R:
            self.session_engine.restart_current_pose()
        elif key == Qt.Key.Key_H:
            self._toggle_flip()
        elif key == Qt.Key.Key_G:
            self._toggle_grayscale()
        elif key == Qt.Key.Key_T:
            self.floating_dock.btn_pin.click()
        elif key == Qt.Key.Key_F:
            if self.pill_switch.current_mode == 'canvas':
                self.canvas_view.fit_all_items()
            else:
                self.action_view.zoom_factor = 1.0
                self.action_view.pan_offset = QPoint(0, 0)
                self.action_view.update()
        elif key == Qt.Key.Key_BracketLeft:
            self.setWindowOpacity(max(0.2, self.windowOpacity() - 0.1))
        elif key == Qt.Key.Key_BracketRight:
            self.setWindowOpacity(min(1.0, self.windowOpacity() + 0.1))
        else:
            super().keyPressEvent(event)

    # ---------------------------------------------------------------
    # Paint: outer rounded border frame
    # ---------------------------------------------------------------
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        theme = get_current_theme()
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setBrush(QBrush(QColor(theme.bg_dark)))
        painter.setPen(QPen(QColor(theme.border), 1.5))
        painter.drawRoundedRect(QRectF(rect), 12, 12)
