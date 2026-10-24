"""
Main Floating Window for RefPad.
Features:
- Native Windows 60FPS drag & resize (startSystemMove / startSystemResize) across all 4 edges and corners.
- Clearly visible, prominent Mode Switcher (Line of Action Practice vs BeeRef Board).
- Complete PDF and Folder support with dedicated file pickers (PDFs always visible).
- Zero hardcoded purple — 100% theme-aware.
"""
import os
from typing import List, Optional
from PySide6.QtWidgets import (
    QWidget, QStackedWidget, QFileDialog, QMessageBox, QApplication, QPushButton,
    QHBoxLayout, QVBoxLayout, QLabel, QFrame
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QKeyEvent, QMouseEvent, QCursor, QFont
)
from PySide6.QtCore import Qt, QPoint, QRect, QRectF, QEvent, Signal

from refpad.engine.source_manager import SourceManager
from refpad.engine.session_engine import SessionEngine
from refpad.engine.audio import SoundCue
from refpad.models.item import RefItem
from refpad.models.board import BoardManager, base64_to_pixmap
from refpad.ui.floating_dock import FloatingDock
from refpad.ui.action_view import ActionView
from refpad.ui.canvas_view import CanvasView
from refpad.ui.canvas_item import CanvasRefItem, CanvasTextItem
from refpad.ui.themes import get_current_theme, set_current_theme, THEMES

RESIZE_MARGIN = 12

class TitleBar(QWidget):
    """
    Main header bar of RefPad:
    - Left: Grip icon + 'RefPad' title (click-drag to move window anywhere)
    - Center: Prominent Mode Switcher ([ Practice Mode ]  [ BeeRef Board ])
    - Right: Open PDF, Open Files, Open Folder, Minimize, Close
    """
    mode_switched = Signal(str)
    open_pdf_requested = Signal()
    open_files_requested = Signal()
    open_folder_requested = Signal()
    close_clicked = Signal()
    min_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(40)
        self.setMouseTracking(True)
        self.active_mode = "action"

        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 4, 10, 4)
        layout.setSpacing(8)

        # 1. Left: Drag Grip Handle
        self.lbl_title = QLabel("⠿ RefPad")
        self.lbl_title.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))
        self.lbl_title.setToolTip("Click and drag to move window anywhere on your screen")
        self.lbl_title.setCursor(Qt.CursorShape.SizeAllCursor)
        layout.addWidget(self.lbl_title)

        layout.addSpacing(6)

        # 2. Center: Mode Switcher (Line of Action vs BeeRef Board)
        self.mode_container = QWidget()
        mode_layout = QHBoxLayout(self.mode_container)
        mode_layout.setContentsMargins(2, 2, 2, 2)
        mode_layout.setSpacing(2)

        self.btn_action = QPushButton("⏱ Practice (Line of Action)")
        self.btn_canvas = QPushButton("🖼 BeeRef Board")

        for b in (self.btn_action, self.btn_canvas):
            b.setFixedHeight(28)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setCheckable(True)
            mode_layout.addWidget(b)

        self.btn_action.setChecked(True)
        self.btn_action.clicked.connect(lambda: self.set_mode("action"))
        self.btn_canvas.clicked.connect(lambda: self.set_mode("canvas"))

        layout.addWidget(self.mode_container)

        layout.addStretch()

        # 3. Right: Quick Loaders & Window buttons
        self.btn_pdf = QPushButton("📄 PDF")
        self.btn_pdf.setToolTip("Open Art or Anatomy PDF Book")
        self.btn_pdf.setFixedHeight(26)
        self.btn_pdf.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_pdf.clicked.connect(self.open_pdf_requested.emit)
        layout.addWidget(self.btn_pdf)

        self.btn_files = QPushButton("🖼 Files")
        self.btn_files.setToolTip("Open Reference Images or PDF Files (All formats visible)")
        self.btn_files.setFixedHeight(26)
        self.btn_files.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_files.clicked.connect(self.open_files_requested.emit)
        layout.addWidget(self.btn_files)

        self.btn_folder = QPushButton("📁 Folder")
        self.btn_folder.setToolTip("Open Image/PDF Reference Folder")
        self.btn_folder.setFixedHeight(26)
        self.btn_folder.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_folder.clicked.connect(self.open_folder_requested.emit)
        layout.addWidget(self.btn_folder)

        layout.addSpacing(4)

        # Minimize
        self.btn_min = QPushButton("—")
        self.btn_min.setFixedSize(24, 24)
        self.btn_min.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_min.clicked.connect(self.min_clicked.emit)
        layout.addWidget(self.btn_min)

        # Close
        self.btn_close = QPushButton("✕")
        self.btn_close.setFixedSize(24, 24)
        self.btn_close.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_close.clicked.connect(self.close_clicked.emit)
        layout.addWidget(self.btn_close)

        self.apply_theme()

    def set_mode(self, mode: str):
        self.active_mode = mode
        self.btn_action.setChecked(mode == "action")
        self.btn_canvas.setChecked(mode == "canvas")
        self.apply_theme()
        self.mode_switched.emit(mode)

    def toggle_mode(self):
        new_mode = "canvas" if self.active_mode == "action" else "action"
        self.set_mode(new_mode)

    def apply_theme(self):
        theme = get_current_theme()
        self.lbl_title.setStyleSheet(f"color: {theme.accent};")

        # Container pill
        self.mode_container.setStyleSheet(f"""
            QWidget {{
                background-color: {theme.bg_dark};
                border: 1px solid {theme.border};
                border-radius: 6px;
            }}
        """)

        # Active / Inactive mode buttons
        is_action = (self.active_mode == "action")
        act_active = f"background-color: {theme.accent}; color: {theme.bg_dark}; font-weight: bold; border-radius: 4px; padding: 0 10px;"
        act_inactive = f"background: transparent; color: {theme.text_muted}; font-weight: 500; border: none; border-radius: 4px; padding: 0 10px;"

        self.btn_action.setStyleSheet(act_active if is_action else act_inactive)
        self.btn_canvas.setStyleSheet(act_active if not is_action else act_inactive)

        btn_style = f"""
            QPushButton {{
                background-color: {theme.bg_card};
                border: 1px solid {theme.border};
                border-radius: 5px;
                color: {theme.text_primary};
                font-family: 'Segoe UI', -apple-system;
                font-size: 11px;
                font-weight: 600;
                padding: 0 8px;
            }}
            QPushButton:hover {{
                background-color: {theme.accent};
                color: {theme.bg_dark};
            }}
        """
        self.btn_pdf.setStyleSheet(btn_style)
        self.btn_files.setStyleSheet(btn_style)
        self.btn_folder.setStyleSheet(btn_style)

        close_style = f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {theme.border};
                border-radius: 5px;
                color: {theme.text_muted};
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: #e11d48;
                color: #ffffff;
                border-color: #e11d48;
            }}
        """
        self.btn_close.setStyleSheet(close_style)

        min_style = f"""
            QPushButton {{
                background: transparent;
                border: 1px solid {theme.border};
                border-radius: 5px;
                color: {theme.text_muted};
                font-size: 11px;
                font-weight: bold;
            }}
            QPushButton:hover {{
                background: {theme.accent};
                color: {theme.bg_dark};
            }}
        """
        self.btn_min.setStyleSheet(min_style)
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        # Native Windows 60FPS Drag & Move
        if event.button() == Qt.MouseButton.LeftButton:
            win = self.window()
            if win and win.windowHandle():
                win.windowHandle().startSystemMove()
                event.accept()
                return
        super().mousePressEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        theme = get_current_theme()
        painter.fillRect(self.rect(), QColor(theme.bg_card))
        painter.setPen(QPen(QColor(theme.border), 1))
        painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()

        # Native Windows Frameless Window with Always-on-top
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
        self.setMouseTracking(True)
        self.resize(800, 620)
        self.setMinimumSize(420, 320)

        # Core Engines
        self.source_manager = SourceManager()
        self.session_engine = SessionEngine(self)
        self.sound_cue = SoundCue(self)

        self.current_board_path: Optional[str] = None

        self._init_ui()
        self._connect_signals()

        # Install event filter to capture edge resize everywhere
        self.installEventFilter(self)
        self.stacked_views.installEventFilter(self)
        self.action_view.installEventFilter(self)
        self.canvas_view.viewport().installEventFilter(self)
        self.floating_dock.installEventFilter(self)

    def _init_ui(self):
        # Main layout
        self.root_layout = QVBoxLayout(self)
        self.root_layout.setContentsMargins(1, 1, 1, 1)
        self.root_layout.setSpacing(0)

        # 1. Header Bar with Grip Drag & Mode Switcher
        self.title_bar = TitleBar(self)
        self.root_layout.addWidget(self.title_bar)

        # 2. Central Content Container
        self.center_container = QWidget(self)
        self.center_layout = QVBoxLayout(self.center_container)
        self.center_layout.setContentsMargins(0, 0, 0, 0)
        self.center_layout.setSpacing(0)

        self.stacked_views = QStackedWidget(self.center_container)
        self.action_view = ActionView(self)
        self.canvas_view = CanvasView(self)
        self.stacked_views.addWidget(self.action_view)  # 0: Practice
        self.stacked_views.addWidget(self.canvas_view)  # 1: BeeRef Board
        self.center_layout.addWidget(self.stacked_views)

        self.root_layout.addWidget(self.center_container, 1)

        # 3. Floating Bottom Dock
        self.floating_dock = FloatingDock(self)

    def _connect_signals(self):
        # Title bar actions
        self.title_bar.mode_switched.connect(self._on_mode_changed)
        self.title_bar.open_pdf_requested.connect(self.open_pdf_dialog)
        self.title_bar.open_files_requested.connect(self.open_files_dialog)
        self.title_bar.open_folder_requested.connect(self.open_folder_dialog)
        self.title_bar.min_clicked.connect(self.showMinimized)
        self.title_bar.close_clicked.connect(self.close)

        # Views
        self.action_view.user_activity_detected.connect(self.floating_dock.wake_dock)
        self.canvas_view.user_activity_detected.connect(self.floating_dock.wake_dock)
        self.action_view.files_dropped.connect(self.handle_incoming_files)
        self.canvas_view.files_dropped.connect(self.handle_incoming_files)
        self.canvas_view.start_session_with_item.connect(self._on_start_session_with_item)

        # Dock actions
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

        # Session Engine
        self.session_engine.tick.connect(self.action_view.timer_hud.update_time)
        self.session_engine.pose_changed.connect(self._on_pose_changed)
        self.session_engine.session_paused.connect(self._on_session_paused)
        self.session_engine.chime_requested.connect(self.sound_cue.play_chime)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        w, h = self.width(), self.height()
        # Position floating dock centered at bottom
        dock_w = max(240, min(self.floating_dock.sizeHint().width(), w - 24))
        self.floating_dock.setGeometry((w - dock_w) // 2, h - 56, dock_w, 48)

    # --- Native Windows Edge Resizing & Dragging ---
    def _get_edge_flags(self, pos: QPoint) -> Optional[Qt.Edge]:
        m = RESIZE_MARGIN
        w, h = self.width(), self.height()
        x, y = pos.x(), pos.y()

        on_l = x <= m
        on_r = x >= w - m
        on_t = y <= m
        on_b = y >= h - m

        edges = None
        if on_t and on_l: edges = Qt.Edge.TopEdge | Qt.Edge.LeftEdge
        elif on_t and on_r: edges = Qt.Edge.TopEdge | Qt.Edge.RightEdge
        elif on_b and on_l: edges = Qt.Edge.BottomEdge | Qt.Edge.LeftEdge
        elif on_b and on_r: edges = Qt.Edge.BottomEdge | Qt.Edge.RightEdge
        elif on_l: edges = Qt.Edge.LeftEdge
        elif on_r: edges = Qt.Edge.RightEdge
        elif on_t: edges = Qt.Edge.TopEdge
        elif on_b: edges = Qt.Edge.BottomEdge
        return edges

    def _update_cursor_for_edges(self, edges: Optional[Qt.Edge]):
        if not edges:
            self.setCursor(Qt.CursorShape.ArrowCursor)
            return

        if edges in (Qt.Edge.TopEdge | Qt.Edge.LeftEdge, Qt.Edge.BottomEdge | Qt.Edge.RightEdge):
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif edges in (Qt.Edge.TopEdge | Qt.Edge.RightEdge, Qt.Edge.BottomEdge | Qt.Edge.LeftEdge):
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif edges in (Qt.Edge.LeftEdge, Qt.Edge.RightEdge):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        elif edges in (Qt.Edge.TopEdge, Qt.Edge.BottomEdge):
            self.setCursor(Qt.CursorShape.SizeVerCursor)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)

    def eventFilter(self, watched, event: QEvent) -> bool:
        t = event.type()
        if t == QEvent.Type.MouseMove:
            m_event: QMouseEvent = event
            local_pos = self.mapFromGlobal(m_event.globalPosition().toPoint())
            edges = self._get_edge_flags(local_pos)
            if edges:
                self._update_cursor_for_edges(edges)
            else:
                if watched is self:
                    self.setCursor(Qt.CursorShape.ArrowCursor)

        elif t == QEvent.Type.MouseButtonPress:
            m_event: QMouseEvent = event
            if m_event.button() == Qt.MouseButton.LeftButton:
                local_pos = self.mapFromGlobal(m_event.globalPosition().toPoint())
                edges = self._get_edge_flags(local_pos)
                if edges and self.windowHandle():
                    # Native 60FPS Windows OS Resize
                    self.windowHandle().startSystemResize(edges)
                    return True

        return super().eventFilter(watched, event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton:
            edges = self._get_edge_flags(event.pos())
            if edges and self.windowHandle():
                self.windowHandle().startSystemResize(edges)
                event.accept()
                return
        super().mousePressEvent(event)

    # --- Mode & Theme Management ---
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
        self.title_bar.set_mode('action')
        self.session_engine.start_session()

    # --- File & PDF Ingestion Dialogs ---
    def open_files_dialog(self):
        """File picker where BOTH images and PDF books are fully visible and selectable."""
        files, _ = QFileDialog.getOpenFileNames(
            self, "Open Reference Images or PDF Books", "",
            "All Supported (*.pdf *.png *.jpg *.jpeg *.webp *.bmp);;PDF Books (*.pdf);;Images (*.png *.jpg *.jpeg *.webp *.bmp);;All Files (*.*)"
        )
        if files:
            self.handle_incoming_files(files)

    def open_pdf_dialog(self):
        """Dedicated PDF Book loader."""
        pdf_path, _ = QFileDialog.getOpenFileName(
            self, "Open Art or Anatomy PDF Book", "",
            "PDF Files (*.pdf);;All Files (*.*)"
        )
        if pdf_path:
            self.handle_incoming_files([pdf_path])

    def open_folder_dialog(self):
        """Folder crawler for images and PDFs."""
        folder = QFileDialog.getExistingDirectory(self, "Select Reference Folder (Contains Images or PDFs)")
        if folder:
            items = self.source_manager.load_folder(folder, recursive=True, shuffle=False)
            self._apply_loaded_items(items)

    def handle_incoming_files(self, paths: List[str]):
        """Handles dropped files, folders, or PDF books."""
        if not paths:
            return

        if len(paths) == 1 and os.path.isdir(paths[0]):
            items = self.source_manager.load_folder(paths[0], recursive=True, shuffle=False)
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
            QMessageBox.information(self, "No References Found", "No valid image files or PDF pages were found.")
            return

        # 1. Update practice session
        self.session_engine.set_items(items)

        # 2. Add to BeeRef infinite canvas
        self.canvas_view.add_ref_items(items, auto_tile=True)

    # --- BeeRef Board File I/O ---
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

    # Context menu
    def contextMenuEvent(self, event):
        self.floating_dock._show_main_menu()
        event.accept()

    # Keyboard Express Keys
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
            self.title_bar.toggle_mode()
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
            if self.title_bar.active_mode == 'canvas':
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

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        theme = get_current_theme()
        rect = self.rect().adjusted(1, 1, -1, -1)
        painter.setBrush(QBrush(QColor(theme.bg_dark)))
        painter.setPen(QPen(QColor(theme.border), 1.5))
        painter.drawRoundedRect(QRectF(rect), 10, 10)
