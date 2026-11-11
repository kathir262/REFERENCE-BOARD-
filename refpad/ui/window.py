"""RefPad's window. It has two looks, like the Android app:

- the full window: top bar with Board / Practice / PDF, tools in a floating bar at the bottom;
- "Float on top": a small always-on-top window to keep next to your drawing app, with compact controls
  and adjustable see-through.

Every tool is a QAction, so keyboard shortcuts, toolbar buttons and the "More" menus share one state.
"""
import ctypes
import os
import time
from pathlib import Path

from PySide6.QtCore import QEvent, QPoint, QRect, Qt, QTimer
from PySide6.QtGui import QAction, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (QApplication, QDialog, QFileDialog, QHBoxLayout, QLabel, QPushButton, QSizeGrip,
                               QStackedWidget, QToolButton,
                               QVBoxLayout, QWidget)

from refpad import __version__, paths
from refpad.core import images, updater
from refpad.core import boards
from refpad.core.importer import split_paths
from refpad.core.store import BOARD, INTERVALS, PDF, PRACTICE
from refpad.core.timer import clock, interval_label
from refpad.settings import settings
from refpad.ui import theme
from refpad.ui.board_files import BoardFiles
from refpad.ui.board_view import BoardView
from refpad.ui.pdf_pages import PdfPagesDialog
from refpad.ui.dialogs import AboutDialog, UpdateDialog
from refpad.ui.pdf_view import PdfView
from refpad.ui.practice_view import PracticeView
from refpad.ui.widgets import (AdaptiveToolbar, EmptyState, Hud, IconButton, Segments, StatusChip, ToolButton, header,
                               item, make_action, menu)

IMAGE_FILTER = "Pictures (*.png *.jpg *.jpeg *.jfif *.webp *.bmp *.gif *.tif *.tiff *.tga);;All files (*.*)"
PDF_FILTER = "PDF files (*.pdf)"
OPACITIES = (1.0, 0.85, 0.7, 0.55)
EDGE = 5   # resize border of the floating window


class Content(QWidget):
    """The views plus what floats over them (tool bar, empty card, status chip)."""

    def __init__(self, win):
        super().__init__()
        self.win = win

    def resizeEvent(self, e):
        self.win.layout_overlays()

    def chip_bottom(self):
        return self.win.chip_bottom()


class Dock(QWidget):
    """Bottom tool row of the floating window."""

    def __init__(self, win):
        super().__init__()
        self.win = win

    def resizeEvent(self, e):
        self.win.fit_dock()


class MainWindow(QWidget):
    def __init__(self, state, timer, engine, importer):
        super().__init__()
        self.state, self.timer, self.engine, self.importer = state, timer, engine, importer
        self.float_mode = False
        self.pinned = False
        self.setWindowTitle("RefPad")
        self.setWindowIcon(QIcon(str(paths.resource("refpad/assets/refpad.ico"))))
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setMinimumSize(340, 300)
        self.files = BoardFiles(self, state)
        self._build_actions()
        self._build_ui()
        self._connect()
        self._restore_geometry(False)
        if settings["float_mode"]:
            self.set_float(True, initial=True)
        self._apply_mode(state.mode)
        QTimer.singleShot(7000, self._auto_check_updates)

    # ================================================================== actions

    def _act(self, *args, **kw) -> QAction:
        a = make_action(self, *args, **kw)
        self.addAction(a)   # shortcuts work anywhere in the window
        return a

    def _build_actions(self):
        A = self._act
        # Board
        self.a_image = A("Image", "image", lambda: self.pick_images(BOARD), "Ctrl+I", "Add images to the board", accent=True)
        self.a_pdf = A("PDF", "pdf", lambda: self.pick_pdf(None), tip="Add a PDF", accent=True)
        self.a_open_any = A("Open", "folder", self.open_any, "Ctrl+O", "Open a board (or a PDF in the PDF reader)")
        self.a_new_board = A("New board", "add", lambda: self.files.new_board(), "Ctrl+N")
        self.a_save = A("Save board", "copy", lambda: self.files.save(), "Ctrl+S")
        self.a_save_as = A("Save board as…", "copy", lambda: self.files.save_as(), "Ctrl+Shift+S")
        self.a_flip = A("Flip", "flip", self.flip_selected, "H", "Flip horizontally", checkable=True)
        self.a_bw = A("B&W", "bw", self.bw_selected, "G", "Black & white", checkable=True)
        self.a_rotate = A("Rotate", "rotate", lambda: self.rotate_selected(1), "R", "Rotate right")
        self.a_rotate_left = A("Rotate left", "rotate_left", lambda: self.rotate_selected(-1), "Shift+R")
        self.a_copy = A("Copy", "copy", self.copy_selected, "Ctrl+C", "Copy image")
        self.a_paste = A("Paste", "paste", self.paste, "Ctrl+V", "Paste images")
        self.a_delete = A("Delete", "delete", self.delete_selected, ["Del", "Backspace"], danger=True)
        self.a_arrange = A("Arrange", "arrange", self.arrange, "Ctrl+Shift+A", "Arrange in rows")
        self.a_fit = A("Fit", "fit", self.fit, ["F", "1"], "Fit to window")
        self.a_select_all = A("Select all", "arrange", lambda: self.board.select_all(), "Ctrl+A")
        self.a_front = A("Bring to front", "arrange", lambda: self.state.bring_to_front(self.board.selected), "PgUp")
        self.a_back = A("Send to back", "arrange", lambda: self.state.send_to_back(self.board.selected), "PgDown")
        self.a_zoom_in = A("Zoom in", "zoom", lambda: self.zoom(1.25), ["Ctrl+=", "Ctrl++", "+"])
        self.a_zoom_out = A("Zoom out", "zoom", lambda: self.zoom(0.8), ["Ctrl+-", "-"])
        # Practice
        self.a_prev = A("Prev", "prev", self.state.prev_pose, ["Left", "A"], "Previous pose")
        self.a_play = A("Play", "play", self.timer.toggle, "Space", "Play or pause", accent=True)
        self.a_next = A("Next", "next", self.state.next_pose, ["Right", "D"], "Next pose")
        self.a_p_flip = A("Flip", "flip", self.toggle_practice_flip, "H", "Flip horizontally", checkable=True)
        self.a_p_bw = A("B&W", "bw", self.toggle_practice_bw, "G", "Black & white", checkable=True)
        self.a_interval = A("1 min", "timer", self.show_interval_menu, tip="Time per pose")
        self.a_p_add = A("Add", "add", lambda: self.show_practice_menu(), tip="Add poses", accent=True)
        self.a_restart = A("Restart pose", "reset", self.timer.restart, "Home")
        # PDF
        self.a_open = A("Open", "pdf", lambda: self.pick_pdf(PDF), tip="Open a PDF", accent=True)
        self.a_recent = A("Recent", "history", self.show_recent_menu, tip="Recent PDFs")
        self.a_page_prev = A("Prev", "page_up", lambda: self.pdf.prev_page(), tip="Previous page")
        self.a_page_next = A("Next", "page_down", lambda: self.pdf.next_page(), tip="Next page")
        self.a_to_board = A("To board", "image", lambda: self.page_to_board(self.pdf.current_page), tip="Add this page to the board")
        self.a_pdf_practise = A("Practise", "timer", lambda: self.practise_from(self.pdf.current_page), tip="Practise from this page")
        # Window
        self.a_mode = [A(t, "image", lambda m=m: self.state.set_mode(m), k) for t, m, k in
                       (("Board", BOARD, "Ctrl+1"), ("Practice", PRACTICE, "Ctrl+2"), ("PDF", PDF, "Ctrl+3"))]
        self.a_float = A("Float on top", "float", self.toggle_float, "Ctrl+T", "Small window that stays on top of other apps")
        self.a_pin = A("Keep window on top", "float", self.toggle_pin, "Ctrl+Shift+T", checkable=True)
        self.a_fullscreen = A("Full screen", "open_full", self.toggle_fullscreen, "F11")
        self.a_about = A("About RefPad and privacy", "info", self.show_about, "F1")
        self.a_updates = A("Check for updates…", "reset", self.show_about)
        self.a_chime = A("Chime when the pose changes", "timer", self.toggle_chime, checkable=True)
        self.a_chime.setChecked(bool(settings["chime"]))
        self.board_actions = [self.a_image, self.a_flip, self.a_bw, self.a_rotate, self.a_rotate_left, self.a_copy,
                              self.a_delete, self.a_arrange, self.a_select_all, self.a_front, self.a_back]
        self.practice_actions = [self.a_prev, self.a_play, self.a_next, self.a_p_flip, self.a_p_bw, self.a_interval,
                                 self.a_p_add, self.a_restart]
        self.pdf_actions = [self.a_open, self.a_recent, self.a_page_prev, self.a_page_next, self.a_to_board, self.a_pdf_practise]

    # ================================================================== layout

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        self.root_layout = root

        # Top bar (full window)
        self.top = QWidget(objectName="TopBar")
        self.top.setFixedHeight(60)
        tl = QHBoxLayout(self.top)
        tl.setContentsMargins(16, 0, 10, 0)
        tl.setSpacing(6)
        self.logo = logo = QLabel()
        logo.setPixmap(QPixmap(str(paths.resource("refpad/assets/icon-128.png"))).scaled(
            30, 30, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        self.title = QPushButton("Untitled board", objectName="BoardName")
        self.title.setCursor(Qt.CursorShape.PointingHandCursor)
        self.title.setToolTip("Boards: new, open, save, recent")
        self.segments = Segments(compact=False)
        self.hud = Hud(compact=False)
        self.btn_add = IconButton("add", "Add images or PDFs", 40, theme.ACCENT)
        self.btn_float = IconButton("float", "Float on top of other apps  (Ctrl+T)", 40)
        self.btn_menu = IconButton("more", "More", 40)
        tl.addWidget(logo)
        tl.addWidget(self.title)
        tl.addSpacing(14)
        tl.addWidget(self.segments)
        tl.addStretch(1)
        tl.addWidget(self.hud)
        tl.addStretch(1)
        tl.addWidget(self.btn_add)
        tl.addWidget(self.btn_float)
        tl.addWidget(self.btn_menu)
        root.addWidget(self.top)

        # Header of the floating window
        self.fheader = QWidget(objectName="FloatHeader")
        self.fheader.setFixedHeight(46)
        fl = QHBoxLayout(self.fheader)
        fl.setContentsMargins(4, 0, 4, 0)
        fl.setSpacing(2)
        self.grip = IconButton("drag", "Drag to move", 30, theme.MUTED)
        self.grip.setCursor(Qt.CursorShape.SizeAllCursor)
        self.segments_c = Segments(compact=True)
        self.btn_add_c = IconButton("add", "Add", 32, theme.ACCENT)
        self.btn_menu_c = IconButton("more", "More", 32)
        self.btn_opacity = IconButton("opacity", "See-through", 32)
        self.btn_full = IconButton("open_full", "Back to the full window  (Ctrl+T)", 32)
        self.btn_min = IconButton("minimize", "Minimise", 32)
        self.btn_close = IconButton("close", "Close RefPad", 32)
        self.btn_close.setObjectName("WindowClose")
        fl.addWidget(self.grip)
        fl.addWidget(self.segments_c)
        fl.addStretch(1)
        for b in (self.btn_add_c, self.btn_menu_c, self.btn_opacity, self.btn_full, self.btn_min, self.btn_close):
            fl.addWidget(b)
        self.fheader.hide()
        root.addWidget(self.fheader)

        # Content: the three views and what floats over them
        self.content = Content(self)
        self.stack = QStackedWidget(self.content)
        self.board = BoardView(self.state)
        self.practice = PracticeView(self.state, self.timer, self.engine)
        self.pdf = PdfView(self.state, self.engine)
        for v in (self.board, self.practice, self.pdf):
            self.stack.addWidget(v)
        self.empty = EmptyState(self.content)
        self.chip = StatusChip(self.content)
        self.page_label = QLabel("", objectName="PageLabel")
        self.page_label_c = QLabel("", objectName="PageLabel")
        self.hud_c = Hud(compact=True)
        self.bars = {m: self._toolbar(False, m) for m in (BOARD, PRACTICE, PDF)}
        root.addWidget(self.content, 1)

        # Bottom row of the floating window
        self.dock = Dock(self)
        dl = QHBoxLayout(self.dock)
        dl.setContentsMargins(0, 0, 0, 0)
        dl.setSpacing(0)
        self.dock_bars = {m: self._toolbar(True, m) for m in (BOARD, PRACTICE, PDF)}
        for bar in self.dock_bars.values():
            dl.addWidget(bar, 1)
        grip = QSizeGrip(self.dock)
        grip.setFixedSize(18, 18)
        dl.addWidget(grip, 0, Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight)
        self.dock.hide()
        root.addWidget(self.dock)

    def _toolbar(self, compact: bool, mode: str) -> AdaptiveToolbar:
        tb = AdaptiveToolbar(compact, floating=not compact, parent=None if compact else self.content)

        def T(action, rank=None, accent=False, danger=False):
            return tb.add(ToolButton(action, compact, accent, danger), rank)

        if mode == BOARD:
            T(self.a_image, accent=True)
            T(self.a_pdf, accent=True)
            tb.add_separator()
            T(self.a_flip, 6)
            T(self.a_bw, 5)
            T(self.a_rotate, 4)
            T(self.a_copy, 1)
            T(self.a_paste, 2)
            T(self.a_delete, 7, danger=True)
            tb.add_separator()
            T(self.a_arrange, 0)
            T(self.a_fit, 3)
        elif mode == PRACTICE:
            if compact:
                tb.add(self.hud_c)
            else:   # the timer moves here when the top bar has no room for it
                self.hud_t = Hud(compact=True)
                tb.add(self.hud_t)
                tb.set_off(self.hud_t, True)
            T(self.a_prev, None if compact else 5)   # last to go; the arrow keys always work
            T(self.a_play, accent=True)
            T(self.a_next, None if compact else 6)
            tb.add_separator()
            T(self.a_p_flip, 2)
            T(self.a_p_bw, 1)
            tb.add_separator()
            T(self.a_interval, 3)
            T(self.a_p_add, 0, accent=True)
        else:
            T(self.a_open, 4, accent=True)
            T(self.a_recent, 2)
            tb.add_separator()
            T(self.a_page_prev)
            tb.add(self.page_label_c if compact else self.page_label)
            T(self.a_page_next)
            tb.add_separator()
            T(self.a_fit, 3)
            T(self.a_to_board, 1)
            T(self.a_pdf_practise, 0)
        tb.finish()
        tb.hide()
        return tb

    def layout_overlays(self):
        w, h = self.content.width(), self.content.height()
        self.stack.setGeometry(0, 0, w, h)
        bar = None if self.float_mode else self.bars.get(self.state.mode)
        pad_bottom = 0
        for m, b in self.bars.items():
            if b is not bar and not b.isHidden():
                b.hide()
        if bar is not None:
            bw = bar.fit(max(200, w - 16))
            bh = bar.sizeHint().height()
            bar.setGeometry((w - bw) // 2, h - bh + 2, bw, bh)
            bar.show()
            bar.raise_()
            pad_bottom = bh - 14
        self._pad_bottom = pad_bottom
        self.board.pad_bottom = pad_bottom
        self.practice.pad_bottom = pad_bottom
        self.pdf.set_padding(0, pad_bottom)
        if not self.empty.isHidden():
            self.empty.place(w, h, 0, pad_bottom)
        self.chip.reposition()

    def chip_bottom(self) -> int:
        return self.content.height() - getattr(self, "_pad_bottom", 0) - 14

    def fit_dock(self):
        bar = self.dock_bars.get(self.state.mode)
        if bar is not None and self.float_mode:
            bar.fit(max(120, self.dock.width() - 20))

    # ================================================================== header fitting

    def _fit_headers(self):
        """Drops the least important parts of the header when the window is narrow, so nothing overlaps,
        and keeps the window from getting narrower than the leanest header."""
        if getattr(self, "_fitting", False) or not hasattr(self, "fheader"):
            return
        self._fitting = True
        try:
            if self.float_mode:
                levels = (
                    lambda: None,
                    lambda: self.btn_opacity.hide(),
                    lambda: self.btn_min.hide(),
                    lambda: self.btn_full.hide(),
                    lambda: self.grip.hide(),
                )
                for b in (self.btn_opacity, self.btn_min, self.btn_full, self.grip):
                    b.show()
                row = self.fheader
            else:
                levels = (
                    lambda: None,
                    lambda: (setattr(self.segments, "show_counts", False), self.segments.refresh_counts()),
                    lambda: self.hud.set_short(True),
                    lambda: self.title.hide(),
                    lambda: self.segments.set_compact(True),
                    lambda: self.btn_float.hide(),
                    lambda: self.logo.hide(),
                    lambda: self.hud.hide(),
                )
                practice_hud = self.state.mode == PRACTICE
                self.hud.setVisible(practice_hud)
                self.segments.show_counts = True
                self.segments.refresh_counts()
                self.segments.set_compact(False)
                self.hud.set_short(False)
                for w in (self.title, self.btn_float, self.logo):
                    w.show()
                row = self.top
            lay = row.layout()
            avail = row.width()
            fitted = False
            for apply in levels:
                apply()
                lay.invalidate()
                need = lay.sizeHint().width()
                if need <= avail:
                    fitted = True
                    break
            if not self.float_mode:
                in_bar = self.state.mode == PRACTICE and self.hud.isHidden()
                if in_bar != (not getattr(self.hud_t, "_off", True)):
                    self.bars[PRACTICE].set_off(self.hud_t, not in_bar)
                    QTimer.singleShot(0, self.layout_overlays)
            # The leanest header decides how narrow the window may get.
            lean = need if not fitted else self._lean_width(levels, lay) if avail > 0 else need
            self.setMinimumWidth(max(300, lean + 2 * (EDGE if self.float_mode else 0)))
        finally:
            self._fitting = False

    def _lean_width(self, levels, lay):
        """Width of the header with every optional part dropped (measured without showing it)."""
        key = (self.float_mode, self.hud.isVisibleTo(self.top), len(self.state.items) > 0)
        cache = self.__dict__.setdefault("_lean_cache", {})
        if key not in cache:
            state = [(w, w.isVisibleTo(w.parentWidget())) for w in
                     (self.btn_opacity, self.btn_min, self.btn_full, self.grip, self.title, self.btn_float, self.logo,
                      self.hud)]
            pose_vis = self.hud.pose.isVisibleTo(self.hud)
            compact = self.segments._compact
            show_counts = self.segments.show_counts
            for apply in levels:
                apply()
            lay.invalidate()
            cache[key] = lay.sizeHint().width()
            for w, vis in state:
                w.setVisible(vis)
            self.hud.pose.setVisible(pose_vis)
            self.segments.set_compact(compact)
            self.segments.show_counts = show_counts
            self.segments.refresh_counts()
            lay.invalidate()
        return cache[key]

    # ================================================================== signals

    def _connect(self):
        st = self.state
        self.segments.modeClicked.connect(st.set_mode)
        self.segments_c.modeClicked.connect(st.set_mode)
        self.btn_add.clicked.connect(lambda: self.show_add_menu(self.btn_add))
        self.btn_add_c.clicked.connect(lambda: self.show_add_menu(self.btn_add_c))
        self.btn_float.clicked.connect(self.toggle_float)
        self.btn_full.clicked.connect(self.toggle_float)
        self.btn_menu.clicked.connect(lambda: self.show_main_menu(self.btn_menu))
        self.title.clicked.connect(lambda: self.show_boards_menu(self.title))
        self.state.boardFileChanged.connect(self._sync_title)
        self.state.task.connect(lambda text, stop: self.chip.show_message(text, True, stop, "STOP"))
        self.btn_menu_c.clicked.connect(lambda: self.show_main_menu(self.btn_menu_c))
        self.btn_opacity.clicked.connect(self.cycle_opacity)
        self.btn_min.clicked.connect(self.showMinimized)
        self.btn_close.clicked.connect(self.close)
        self.grip.pressed.connect(self._system_move)
        self.fheader.installEventFilter(self)
        self.top.installEventFilter(self)

        st.modeChanged.connect(self._apply_mode)
        st.boardChanged.connect(self._sync_board)
        st.practiceChanged.connect(self._sync_practice)
        st.poseChanged.connect(self._sync_practice)
        st.docsChanged.connect(self._sync_pdf)
        st.status.connect(lambda text, busy, undo: self.chip.show_message(text, busy, undo))
        self.board.selectionChanged.connect(self._sync_board)
        self.board.contextRequested.connect(self._board_context)
        self.practice.contextRequested.connect(lambda pos: self.show_practice_menu(at=pos.toPoint()))
        self.pdf.contextRequested.connect(lambda page, pos: self.show_pdf_menu(at=pos.toPoint(), page=page))
        self.pdf.pageChanged.connect(self._sync_pdf)
        self.timer.tick.connect(self._sync_hud)
        self.timer.runningChanged.connect(lambda _r: self._sync_practice())

    def eventFilter(self, obj, e):
        if e.type() == QEvent.Type.Resize and obj in (self.top, self.fheader):
            self._fit_headers()
            return False
        if obj is self.fheader and e.type() == QEvent.Type.MouseButtonPress and e.button() == Qt.MouseButton.LeftButton:
            self._system_move()
            return True
        if obj is self.fheader and e.type() == QEvent.Type.MouseButtonDblClick:
            return True
        return super().eventFilter(obj, e)

    # ================================================================== mode & state sync

    def _apply_mode(self, mode: str):
        self.segments.set_mode(mode)
        self.segments_c.set_mode(mode)
        view = {BOARD: self.board, PRACTICE: self.practice, PDF: self.pdf}[mode]
        self.stack.setCurrentWidget(view)
        for m, bar in self.dock_bars.items():
            bar.setVisible(m == mode)
        for a in self.board_actions:
            a.setEnabled(mode == BOARD)
        for a in self.practice_actions:
            a.setEnabled(mode == PRACTICE)
        for a in self.pdf_actions:
            a.setEnabled(mode == PDF)
        self.a_paste.setEnabled(mode in (BOARD, PRACTICE))
        self.a_fit.setText("Fit" if mode != PRACTICE else "Reset zoom")
        self.hud.setVisible(mode == PRACTICE and not self.float_mode)
        if mode != PRACTICE:
            self.timer.pause()
        self._sync_board()
        self._sync_practice()
        self._sync_pdf()
        self._fit_headers()
        self.layout_overlays()
        self.fit_dock()
        view.setFocus()

    def _sync_board(self):
        st = self.state
        self.segments.set_counts(len(st.items), len(st.practice))
        self._fit_headers()
        if st.mode != BOARD:
            self._sync_empty()
            return
        sel = self.board.selected
        for a in (self.a_flip, self.a_bw, self.a_rotate, self.a_rotate_left, self.a_copy, self.a_delete, self.a_front, self.a_back):
            a.setEnabled(bool(sel))
        self.a_flip.setChecked(bool(sel) and sel[-1].flip)
        self.a_bw.setChecked(bool(sel) and sel[-1].gray)
        self.a_arrange.setEnabled(bool(st.items))
        self.a_select_all.setEnabled(bool(st.items))
        self._sync_empty()

    def _sync_practice(self):
        st = self.state
        self.segments.set_counts(len(st.items), len(st.practice))
        self._fit_headers()
        has = bool(st.practice)
        if st.mode == PRACTICE:
            for a in (self.a_prev, self.a_next, self.a_play, self.a_p_flip, self.a_p_bw, self.a_restart):
                a.setEnabled(has)
            self.a_prev.setEnabled(len(st.practice) > 1)
            self.a_next.setEnabled(len(st.practice) > 1)
        running = self.timer.running
        icon = "pause" if running else "play"
        if getattr(self.a_play, "icon_name", "") != icon:
            self.a_play.icon_name = icon
            self.a_play.setIcon(theme.icon(icon, theme.ACCENT))
            self.a_play.setText("Pause" if running else "Play")
        self.a_p_flip.setChecked(st.practice_flip)
        self.a_p_bw.setChecked(st.practice_gray)
        self.a_interval.setText(interval_label(st.interval))
        self._sync_hud()
        self._sync_empty()

    def _sync_hud(self):
        st = self.state
        n = len(st.practice)
        t = clock(self.timer.remaining_ms) if n else "–:––"
        self.hud.set(t, f"Pose {st.practice_index + 1} of {n}" if n else "No poses")
        self.hud_c.set(t, f"{st.practice_index + 1}/{n}" if n else "")
        self.hud_t.set(t, f"{st.practice_index + 1}/{n}" if n else "")

    def _sync_pdf(self):
        st = self.state
        self._sync_title()
        text = f"{self.pdf.current_page + 1} / {self.pdf.page_count}" if self.pdf.ready else ""
        for lab in (self.page_label, self.page_label_c):
            if lab.text() != text:
                lab.setText(text)
        if st.mode == PDF:
            ready = self.pdf.ready
            for a in (self.a_page_prev, self.a_page_next, self.a_to_board, self.a_pdf_practise):
                a.setEnabled(ready)
            self.a_recent.setEnabled(bool(st.docs))
        self._sync_empty()

    def _sync_empty(self):
        st = self.state
        mode = st.mode
        show = (mode == BOARD and not st.items) or (mode == PRACTICE and not st.practice) or (mode == PDF and st.doc is None)
        if not show:
            # isHidden, not isVisible: before the window is first shown nothing counts as visible,
            # so the card would stay un-hidden and appear blank over a full board.
            if not self.empty.isHidden():
                self.empty.hide()
            return
        compact = self.float_mode
        if mode == BOARD:
            self.empty.set_content(
                "image", "Your board is empty",
                "Add pictures or a PDF art book, then keep the board floating on top of your drawing app.",
                ("Add images", lambda: self.pick_images(BOARD)), ("Open PDF", lambda: self.pick_pdf(None)),
                None if compact else ("Import folder", lambda: self.pick_folder(BOARD)),
                ("Open a saved board", self.files.open_dialog),
                "" if compact else "Drop pictures, PDFs or folders anywhere · Ctrl+V to paste · Scroll to zoom · Double-click to fit")
        elif mode == PRACTICE:
            link = ("Use board images", lambda: self.importer.board_to_practice(st.items)) if st.items else ("Back to the board", lambda: st.set_mode(BOARD))
            self.empty.set_content(
                "timer", "Nothing to practise yet",
                "Open a PDF art book, a folder or some pictures. Each pose stays up for the time you choose, then moves on by itself.",
                ("Open a PDF art book", lambda: self.pick_pdf(PRACTICE)), ("Add images", lambda: self.pick_images(PRACTICE)),
                None if compact else ("Use a folder", lambda: self.pick_folder(PRACTICE)), link,
                "" if compact else "Space to pause · ← → to change pose · Scroll to zoom into a pose")
        else:
            self.empty.set_content(
                "pdf", "Read a PDF",
                "Open art books, tutorials and comics. Pages load as you scroll, so even very large books stay light and smooth.",
                ("Open a PDF", lambda: self.pick_pdf(PDF)), ("Back to board", lambda: st.set_mode(BOARD)), None,
                ("Practise with a PDF instead", lambda: self.pick_pdf(PRACTICE)),
                "" if compact else "Ctrl + scroll to zoom · Double-click to switch between fit width and whole page")
        self.empty.body.setVisible(not compact or self.content.height() > 420)
        self.empty.show()
        self.empty.raise_()
        self.chip.raise_()
        self.layout_overlays()

    # ================================================================== board actions

    def _edit_selected(self, fn):
        sel = self.board.selected
        if sel:
            for it in sel:
                fn(it)
            self.state.edited()

    def flip_selected(self):
        sel = self.board.selected
        if sel:
            value = not sel[-1].flip
            self._edit_selected(lambda it: setattr(it, "flip", value))

    def bw_selected(self):
        sel = self.board.selected
        if sel:
            value = not sel[-1].gray
            self._edit_selected(lambda it: setattr(it, "gray", value))

    def rotate_selected(self, direction: int):
        # When an image is flipped, turning it clockwise on screen means turning the picture the other way.
        self._edit_selected(lambda it: setattr(it, "rot", (it.rot + (-direction if it.flip else direction)) % 4))

    def copy_selected(self):
        if not self.importer.copy_items(self.board.selected):
            self.state.notify("Click an image first")

    def paste(self):
        if not self.importer.paste(self.state.mode == PRACTICE, self.ask_pdf_destination):
            self.state.notify("Nothing to paste – copy a picture first")

    def delete_selected(self):
        self.state.remove_items(list(self.board.selected))

    def arrange(self):
        self.state.auto_arrange()
        self.board.fit_all()

    def fit(self):
        mode = self.state.mode
        if mode == BOARD:
            self.board.fit_all()
        elif mode == PRACTICE:
            self.practice.reset_zoom()
        else:
            self.pdf.toggle_fit()

    def zoom(self, factor: float):
        mode = self.state.mode
        if mode == BOARD:
            self.board.zoom_step(factor)
        elif mode == PDF:
            self.pdf.zoom_by(factor)

    # ================================================================== practice actions

    def toggle_practice_flip(self):
        self.state.practice_flip = not self.state.practice_flip
        self.state.schedule_save()
        self.practice.refresh()
        self._sync_practice()

    def toggle_practice_bw(self):
        self.state.practice_gray = not self.state.practice_gray
        self.state.schedule_save()
        self.practice.refresh()
        self._sync_practice()

    def toggle_chime(self):
        settings["chime"] = self.a_chime.isChecked()

    def practise_from(self, page: int):
        doc = self.state.doc
        if doc is not None:
            self.importer.pdf_to_practice(doc.path, page)

    def page_to_board(self, page: int):
        doc = self.state.doc
        if doc is not None:
            self.importer.page_to_board(doc.path, page)

    # ================================================================== pickers & dropping

    def pick_images(self, target: str):
        files, _ = QFileDialog.getOpenFileNames(self, "Add pictures to the " + ("practice list" if target == PRACTICE else "board"),
                                                "", IMAGE_FILTER)
        if files:
            (self.importer.images_to_practice if target == PRACTICE else self.importer.images_to_board)(files)

    def pick_folder(self, target: str):
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder of pictures")
        if folder:
            (self.importer.folder_to_practice if target == PRACTICE else self.importer.folder_to_board)(folder)

    def pick_pdf(self, target):
        path, _ = QFileDialog.getOpenFileName(self, "Open a PDF", "", PDF_FILTER)
        if path:
            self.open_pdf(path, target)

    def open_pdf(self, path: str, target, at: QPoint = None):
        if target == PDF:
            self.importer.pdf_to_reader(path)
        elif target == PRACTICE:
            self.importer.pdf_to_practice(path)
        elif target == BOARD:
            self.choose_pdf_pages(path)
        else:
            self.ask_pdf_destination(path, at)

    def ask_pdf_destination(self, path: str, at: QPoint = None):
        m = menu(self)
        header(m, f"Open “{Path(path).stem}” in")
        item(m, "PDF reader", "pdf", lambda: self.importer.pdf_to_reader(path))
        item(m, "Practice (every page)", "timer", lambda: self.importer.pdf_to_practice(path))
        item(m, "Board (choose pages)", "image", lambda: self.choose_pdf_pages(path))
        m.exec(at or self._menu_point())

    def open_paths(self, paths_, at: QPoint = None):
        board_files = [p for p in paths_ if boards.is_board_file(p) and os.path.isfile(p)]
        if board_files:
            self.files.open(board_files[0])
            paths_ = [p for p in paths_ if p not in board_files]
            if not paths_:
                return
        imgs, pdfs, folders = split_paths(paths_)
        to_practice = self.state.mode == PRACTICE
        if imgs:
            (self.importer.images_to_practice if to_practice else self.importer.images_to_board)(imgs)
        for f in folders:
            (self.importer.folder_to_practice if to_practice else self.importer.folder_to_board)(f)
        if len(pdfs) == 1:
            target = {PDF: PDF, PRACTICE: PRACTICE}.get(self.state.mode)
            self.open_pdf(pdfs[0], target, at)
        else:
            for p in pdfs:
                (self.importer.pdf_to_practice if to_practice else self.importer.pdf_to_reader)(p)
        if not (imgs or pdfs or folders):
            self.state.notify("RefPad opens pictures, PDFs and folders")

    def dragEnterEvent(self, e):
        md = e.mimeData()
        if md.hasUrls() or md.hasImage():
            e.acceptProposedAction()

    def dropEvent(self, e):
        md = e.mimeData()
        local = [u.toLocalFile() for u in md.urls() if u.isLocalFile()] if md.hasUrls() else []
        if local:
            at = self.mapToGlobal(e.position().toPoint())   # read now: the drop event is gone after this method
            QTimer.singleShot(0, lambda: self.open_paths(local, at))
        elif md.hasImage():
            img = QImage(md.imageData())
            if self.state.mode == PRACTICE:
                self.importer.qimages_to_practice([img])
            else:
                self.importer.qimages_to_board([img])
        e.acceptProposedAction()

    # ================================================================== boards & PDF pages

    def open_any(self):
        """Ctrl+O: a board on the Board tab, a PDF on the other tabs."""
        mode = self.state.mode
        if mode == BOARD:
            self.files.open_dialog()
        else:
            self.pick_pdf(mode)

    def show_boards_menu(self, anchor):
        m = menu(self)
        self.files.fill_menu(m)
        m.exec(anchor.mapToGlobal(QPoint(0, anchor.height() + 4)))

    def _sync_title(self):
        st = self.state
        unsaved = st.board_dirty and bool(st.items)
        name = st.board_name + ("  •" if unsaved else "")
        if self.title.text() != name:
            self.title.setText(name)
            self.title.setToolTip(("Not saved yet. " if unsaved else "") + "Boards: new, open, save, recent")
        doc = st.doc
        if st.mode == PDF and doc is not None:
            title = f"{doc.title} – RefPad"
        else:
            title = f"{st.board_name}{' •' if unsaved else ''} – RefPad"
        if self.windowTitle() != title:
            self.setWindowTitle(title)
        self._fit_headers()

    def choose_pdf_pages(self, path: str, preselect=None):
        """Lets you pick which pages of a PDF go to the board (all, page numbers, or by clicking)."""
        def go(info):
            self.chip.fade_out()
            dlg = PdfPagesDialog(self, path, info.count, self.engine, preselect)
            if dlg.exec() == QDialog.DialogCode.Accepted and dlg.pages:
                self.state.set_mode(BOARD)
                self.importer.pdf_pages_to_board(path, dlg.pages)
        self.importer.with_info(path, go)

    # ================================================================== menus

    def _menu_point(self) -> QPoint:
        p = self.mapFromGlobal(QPoint(*self._cursor()))
        if self.rect().contains(p):
            return QPoint(*self._cursor())
        return self.mapToGlobal(self.rect().center())

    @staticmethod
    def _cursor():
        from PySide6.QtGui import QCursor
        c = QCursor.pos()
        return c.x(), c.y()

    def _popup(self, m, anchor_action: QAction = None, anchor_widget: QWidget = None, at: QPoint = None):
        """Shows a menu at `at`, above the visible button of `anchor_action`, or below `anchor_widget`."""
        if at is None and anchor_action is not None:
            btns = [w for w in anchor_action.associatedObjects() if isinstance(w, QToolButton) and w.isVisible()]
            if btns:
                b = btns[0]
                size = m.sizeHint()
                at = b.mapToGlobal(QPoint((b.width() - size.width()) // 2, -size.height() - 8))
        if at is None and anchor_widget is not None:
            size = m.sizeHint()
            at = anchor_widget.mapToGlobal(QPoint(anchor_widget.width() - size.width(), anchor_widget.height() + 4))
        m.exec(at or self._menu_point())

    def show_add_menu(self, anchor):
        st = self.state
        m = menu(self)
        header(m, "Add to board")
        item(m, "Images", "image", lambda: self.pick_images(BOARD))
        item(m, "PDF pages", "pdf", lambda: self.pick_pdf(BOARD))
        item(m, "Folder of images", "folder", lambda: self.pick_folder(BOARD))
        header(m, "Add to practice")
        item(m, "PDF art book (every page)", "pdf", lambda: self.pick_pdf(PRACTICE))
        item(m, "Images", "image", lambda: self.pick_images(PRACTICE))
        item(m, "Folder of images", "folder", lambda: self.pick_folder(PRACTICE))
        item(m, "Use board images", "arrange", lambda: self.importer.board_to_practice(st.items), enabled=bool(st.items))
        header(m, "Read")
        item(m, "Open a PDF to read", "pdf", lambda: self.pick_pdf(PDF))
        self._popup(m, anchor_widget=anchor)

    def show_main_menu(self, anchor):
        st = self.state
        m = menu(self)
        if st.mode == BOARD:
            self.files.fill_menu(m)
            self._fill_board_menu(m)
        elif st.mode == PRACTICE:
            self._fill_practice_menu(m)
        else:
            self._fill_pdf_menu(m, self.pdf.current_page)
        header(m, "Window")
        if self.float_mode:
            item(m, "Back to the full window", "open_full", self.toggle_float, shortcut="Ctrl+T")
            item(m, f"See-through ({round(self.windowOpacity() * 100)}%)", "opacity", self.cycle_opacity)
            item(m, "Minimise", "minimize", self.showMinimized)
        else:
            item(m, "Float on top of other apps", "float", self.toggle_float, shortcut="Ctrl+T")
            m.addAction(self.a_pin)
            item(m, "Exit full screen" if self.isFullScreen() else "Full screen", "open_full", self.toggle_fullscreen, shortcut="F11")
        m.addSeparator()
        item(m, "Check for updates…", "reset", self.show_about)
        item(m, "About RefPad and privacy", "info", self.show_about, shortcut="F1")
        self._popup(m, anchor_widget=anchor)

    def _fill_board_menu(self, m):
        st = self.state
        has = bool(st.items)
        header(m, "Board")
        item(m, "Paste", "paste", self.paste, shortcut="Ctrl+V")
        item(m, "Add images", "image", lambda: self.pick_images(BOARD), shortcut="Ctrl+I")
        item(m, "Add PDF pages…", "pdf", lambda: self.pick_pdf(BOARD))
        item(m, "Import folder", "folder", lambda: self.pick_folder(BOARD))
        item(m, "Fit everything", "fit", self.board.fit_all, enabled=has, shortcut="F")
        item(m, "Arrange in rows", "arrange", self.arrange, enabled=has, shortcut="Ctrl+Shift+A")
        item(m, "Select all", "arrange", self.board.select_all, enabled=has, shortcut="Ctrl+A")
        item(m, "Practise with these images", "timer", lambda: self.importer.board_to_practice(st.items), enabled=has)
        item(m, "Clear board", "delete", st.clear_board, enabled=has, danger=True)

    def _board_context(self, it, pos):
        at = pos.toPoint()
        m = menu(self)
        if it is None:
            self._fill_board_menu(m)
            m.exec(at)
            return
        sel = self.board.selected
        header(m, "Image" if len(sel) <= 1 else f"{len(sel)} images")
        item(m, "Copy", "copy", self.copy_selected, shortcut="Ctrl+C")
        item(m, "Flip horizontally", "flip", self.flip_selected, shortcut="H")
        item(m, "Rotate right", "rotate", lambda: self.rotate_selected(1), shortcut="R")
        item(m, "Rotate left", "rotate_left", lambda: self.rotate_selected(-1), shortcut="Shift+R")
        item(m, "Show in colour" if it.gray else "Black & white", "bw", self.bw_selected, shortcut="G")
        item(m, "Zoom to this image", "zoom", lambda: self.board.fit_item(it))
        item(m, "Bring to front", "arrange", lambda: self.state.bring_to_front(list(sel)), shortcut="PgUp")
        item(m, "Send to back", "arrange", lambda: self.state.send_to_back(list(sel)), shortcut="PgDown")
        item(m, "Practise with " + ("this image" if len(sel) <= 1 else "these images"), "timer",
             lambda: self.importer.board_to_practice(list(sel)))
        item(m, "Reset size and rotation", "reset", lambda: self._edit_selected(lambda i: i.reset()))
        m.addSeparator()
        item(m, "Delete", "delete", self.delete_selected, danger=True, shortcut="Del")
        m.exec(at)

    def _fill_practice_menu(self, m):
        st = self.state
        has = bool(st.practice)
        header(m, "Practice")
        item(m, "Open a PDF art book", "pdf", lambda: self.pick_pdf(PRACTICE))
        item(m, "Add images", "image", lambda: self.pick_images(PRACTICE))
        item(m, "Practise a folder of pictures", "folder", lambda: self.pick_folder(PRACTICE))
        item(m, "Use board images", "arrange", lambda: self.importer.board_to_practice(st.items), enabled=bool(st.items))
        item(m, "Shuffle poses", "reset", st.shuffle_practice, enabled=len(st.practice) > 1)
        item(m, "Restart this pose", "timer", self.timer.restart, enabled=has, shortcut="Home")
        item(m, "Reset zoom", "fit", self.practice.reset_zoom, enabled=has, shortcut="F")
        m.addAction(self.a_chime)
        item(m, "Back to the board", "image", lambda: st.set_mode(BOARD))
        item(m, "Clear practice list", "delete", st.clear_practice, enabled=has, danger=True)

    def show_practice_menu(self, at: QPoint = None):
        m = menu(self)
        self._fill_practice_menu(m)
        self._popup(m, None if at else self.a_p_add, at=at)

    def show_interval_menu(self):
        m = menu(self)
        header(m, "Time per pose")
        for sec in INTERVALS:
            a = item(m, interval_label(sec), "timer", lambda s=sec: (self.timer.set_interval(s), self._sync_practice()))
            a.setCheckable(True)
            a.setChecked(sec == self.state.interval)
        self._popup(m, self.a_interval)

    def _fill_pdf_menu(self, m, page: int):
        st = self.state
        doc = st.doc
        header(m, doc.title if doc else "PDF")
        item(m, "Open another PDF…", "pdf", lambda: self.pick_pdf(PDF))
        if doc is not None and self.pdf.ready:
            item(m, f"Add page {page + 1} to the board", "image", lambda: self.page_to_board(page))
            item(m, "Add pages to the board…", "image", lambda: self.choose_pdf_pages(doc.path, [page]))
            item(m, f"Practise from page {page + 1}", "timer", lambda: self.practise_from(page))
            item(m, self.pdf.fit_label(), "fit", self.pdf.toggle_fit, shortcut="F")
            item(m, "Go to first page", "page_up", lambda: self.pdf.go_to_page(0), shortcut="Home")
            item(m, "Go to last page", "page_down", lambda: self.pdf.go_to_page(self.pdf.page_count - 1), shortcut="End")
        others = st.docs[1:7]
        if others:
            header(m, "Recent")
            for d in others:
                item(m, d.title, "history", lambda d=d: self.importer.pdf_to_reader(d.path))
        if doc is not None:
            m.addSeparator()
            item(m, "Remove from recent", "delete", lambda: st.remove_doc(doc), danger=True)

    def show_pdf_menu(self, at: QPoint = None, page: int = None):
        m = menu(self)
        self._fill_pdf_menu(m, self.pdf.current_page if page is None else page)
        self._popup(m, at=at)

    def show_recent_menu(self):
        st = self.state
        m = menu(self)
        header(m, "Recent PDFs")
        for i, d in enumerate(st.docs):
            pages = f"  ·  {d.pages} pages" if d.pages else ""
            a = item(m, d.title + pages, "pdf", lambda d=d: self.importer.pdf_to_reader(d.path))
            a.setCheckable(True)
            a.setChecked(i == 0)
        if not st.docs:
            item(m, "Nothing opened yet", "history", lambda: None, enabled=False)
        m.addSeparator()
        item(m, "Open a PDF…", "add", lambda: self.pick_pdf(PDF), shortcut="Ctrl+O")
        self._popup(m, self.a_recent)

    # ================================================================== window modes

    def toggle_float(self):
        self.set_float(not self.float_mode)

    def set_float(self, on: bool, initial: bool = False):
        if on == self.float_mode and not initial:
            return
        if not initial:
            self._save_geometry()
            if self.isFullScreen() or self.isMaximized():
                self.showNormal()
        self.float_mode = on
        settings["float_mode"] = on
        visible = self.isVisible()
        flags = Qt.WindowType.Window
        if on:
            flags |= Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
        elif self.pinned:
            flags |= Qt.WindowType.WindowStaysOnTopHint
        self.setWindowFlags(flags)
        self.top.setVisible(not on)
        self.fheader.setVisible(on)
        self.dock.setVisible(on)
        m = EDGE if on else 0
        self.root_layout.setContentsMargins(m, m, m, m)
        self.setWindowOpacity(float(settings["float_opacity"]) if on else 1.0)
        self._restore_geometry(on)
        if visible or not initial:
            self.show()
        if not initial:
            self._apply_mode(self.state.mode)

    def cycle_opacity(self):
        cur = round(self.windowOpacity(), 2)
        nxt = next((o for o in OPACITIES if o < cur - 0.01), OPACITIES[0])
        self.setWindowOpacity(nxt)
        settings["float_opacity"] = nxt
        self.state.notify(f"See-through: {round((1 - nxt) * 100)}%" if nxt < 1 else "Solid window")

    def toggle_pin(self):
        self.pinned = self.a_pin.isChecked()
        if not self.float_mode:
            geo = self.geometry()
            self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, self.pinned)
            self.setGeometry(geo)
            self.show()

    def toggle_fullscreen(self):
        if self.float_mode:
            return
        if self.isFullScreen():
            self.showMaximized() if settings["maximized"] else self.showNormal()
        else:
            self.showFullScreen()

    def _system_move(self):
        if self.windowHandle():
            self.windowHandle().startSystemMove()

    # geometry ---------------------------------------------------------------

    def _save_geometry(self):
        if self.float_mode:
            g = self.geometry()
            settings["float_geometry"] = [g.x(), g.y(), g.width(), g.height()]
        elif not self.isFullScreen():
            settings["maximized"] = self.isMaximized()
            g = self.normalGeometry() if self.isMaximized() else self.geometry()
            settings["geometry"] = [g.x(), g.y(), g.width(), g.height()]

    def _restore_geometry(self, floating: bool):
        screen = QApplication.primaryScreen().availableGeometry()
        saved = settings["float_geometry" if floating else "geometry"]
        if saved and len(saved) == 4:
            r = QRect(*saved)
            if any(s.availableGeometry().intersects(r) for s in QApplication.screens()):
                self.setGeometry(r)
                return
        if floating:
            w, h = 440, min(620, screen.height() - 80)
            self.setGeometry(screen.right() - w - 24, screen.top() + (screen.height() - h) // 2, w, h)
        else:
            w, h = min(1360, screen.width() - 80), min(860, screen.height() - 80)
            self.setGeometry(screen.left() + (screen.width() - w) // 2, screen.top() + (screen.height() - h) // 2, w, h)

    def show_initial(self):
        if not self.float_mode and settings["maximized"]:
            self.showMaximized()
        else:
            self.show()

    # frameless resizing (floating window) -----------------------------------

    def _edges(self, p: QPoint):
        if not self.float_mode:
            return None
        e = Qt.Edge(0)
        if p.x() <= EDGE + 1:
            e |= Qt.Edge.LeftEdge
        if p.x() >= self.width() - EDGE - 2:
            e |= Qt.Edge.RightEdge
        if p.y() <= EDGE + 1:
            e |= Qt.Edge.TopEdge
        if p.y() >= self.height() - EDGE - 2:
            e |= Qt.Edge.BottomEdge
        return e if e != Qt.Edge(0) else None

    def mouseMoveEvent(self, e):
        edges = self._edges(e.position().toPoint())
        if edges is None:
            self.unsetCursor()
            return
        diag1 = (Qt.Edge.LeftEdge | Qt.Edge.TopEdge, Qt.Edge.RightEdge | Qt.Edge.BottomEdge)
        diag2 = (Qt.Edge.RightEdge | Qt.Edge.TopEdge, Qt.Edge.LeftEdge | Qt.Edge.BottomEdge)
        if edges in diag1:
            self.setCursor(Qt.CursorShape.SizeFDiagCursor)
        elif edges in diag2:
            self.setCursor(Qt.CursorShape.SizeBDiagCursor)
        elif edges in (Qt.Edge.LeftEdge, Qt.Edge.RightEdge):
            self.setCursor(Qt.CursorShape.SizeHorCursor)
        else:
            self.setCursor(Qt.CursorShape.SizeVerCursor)

    def mousePressEvent(self, e):
        edges = self._edges(e.position().toPoint())
        if edges is not None and e.button() == Qt.MouseButton.LeftButton and self.windowHandle():
            self.windowHandle().startSystemResize(edges)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), theme.color(theme.SURFACE if self.float_mode else theme.BG))
        if self.float_mode:
            p.setPen(QPen(theme.color(theme.STROKE_STRONG), 1))
            p.drawRect(self.rect().adjusted(0, 0, -1, -1))

    # Windows title bar --------------------------------------------------------

    def _style_native_frame(self):
        if os.name != "nt":
            return
        try:
            hwnd = int(self.winId())
            dwm = ctypes.windll.dwmapi

            def setattr_(attr, value):
                v = ctypes.c_int(value)
                dwm.DwmSetWindowAttribute(hwnd, attr, ctypes.byref(v), ctypes.sizeof(v))

            setattr_(20, 1)              # dark title bar
            setattr_(35, 0x001A1717)     # caption colour #17171A (Windows 11)
            setattr_(34, 0x00332C2C)     # border colour #2C2C33 (Windows 11)
            setattr_(33, 2)              # rounded corners, also for the frameless floating window
        except Exception:
            pass

    # ================================================================== events

    def showEvent(self, e):
        super().showEvent(e)
        self._style_native_frame()
        QTimer.singleShot(0, self.layout_overlays)

    def changeEvent(self, e):
        if e.type() == QEvent.Type.WindowStateChange and self.isMinimized():
            self.timer.pause()          # no one is looking: pause and free memory
            images.cache.trim()
            self.engine.trim()
        super().changeEvent(e)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._sync_empty()

    def closeEvent(self, e):
        self._save_geometry()
        self.files.save_now_if_needed()
        self.pdf._remember()
        self.state.save_now()
        super().closeEvent(e)

    # ================================================================== about & updates

    def show_about(self):
        AboutDialog(self, self.open_update).exec()

    def open_update(self, rel):
        UpdateDialog(self, rel, self._before_restart).exec()

    def _before_restart(self):
        self._save_geometry()
        self.files.save_now_if_needed()
        self.pdf._remember()
        self.state.save_now()

    def _auto_check_updates(self):
        if not settings["auto_update"] or not updater.due_for_check(settings["last_update_check"]):
            return

        def work():
            try:
                return updater.check()
            except updater.UpdateError:
                return False

        def done(rel):
            if rel is False or isinstance(rel, Exception):
                return
            settings["last_update_check"] = time.time()
            if rel is not None and rel.version_text != settings["skip_version"]:
                self.chip.show_message(f"RefPad {rel.version_text} is available", False,
                                       lambda: self.open_update(rel), "UPDATE")

        images.run_async(work, done)

    def after_update(self, ok: bool):
        if ok:
            self.chip.show_message(f"RefPad is up to date ({__version__})")
        else:
            self.chip.show_message("The update couldn't be installed – your previous version is still here")
