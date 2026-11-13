"""PDF reader extras: the page list on the left (thumbnails) and the search bar."""
from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QFrame, QHBoxLayout, QLabel, QLineEdit, QListView, QListWidget,
                               QListWidgetItem)

from refpad.ui import theme
from refpad.ui.widgets import IconButton

THUMB = QSize(104, 140)


class PdfPagesPanel(QListWidget):
    """Thumbnails of every page; click one to go there. Thumbnails render as they scroll into view."""

    pageClicked = Signal(int)
    WIDTH = 152

    def __init__(self, engine, parent=None):
        super().__init__(parent)
        self.engine = engine
        self._path = ""
        self._count = 0
        self._requested = set()
        self._marks = set()
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setFlow(QListView.Flow.TopToBottom)
        self.setWrapping(False)
        self.setIconSize(THUMB)
        self.setGridSize(QSize(THUMB.width() + 24, THUMB.height() + 30))
        self.setUniformItemSizes(True)
        self.setMovement(QListView.Movement.Static)
        self.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setStyleSheet(
            f"QListWidget {{ background: {theme.SURFACE}; border: none; border-right: 1px solid {theme.STROKE}; padding: 6px; }}"
            f"QListWidget::item {{ color: {theme.TEXT_2}; border: 2px solid transparent; border-radius: 8px; padding: 3px; }}"
            f"QListWidget::item:selected {{ background: rgba(250, 204, 21, 0.14); border-color: {theme.ACCENT}; color: {theme.ACCENT}; }}"
            f"QListWidget::item:hover {{ background: {theme.RAISED}; }}")
        self.itemClicked.connect(lambda it: self.pageClicked.emit(self.row(it)))
        self._timer = QTimer(self, singleShot=True, interval=60, timeout=self._load_visible)
        self.verticalScrollBar().valueChanged.connect(lambda _v: self._timer.start())

    def set_doc(self, path: str, count: int, marks=()):
        if path == self._path and count == self._count:
            self.set_marks(marks)
            return
        self._path, self._count = path, count
        self._requested = set()
        self._marks = set(marks)
        self.clear()
        blank = QPixmap(THUMB)
        blank.fill(QColor(theme.RAISED))
        icon = QIcon(blank)
        for i in range(count):
            it = QListWidgetItem(icon, self._label(i))
            it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.addItem(it)
        self._timer.start()

    def _label(self, i):
        return f"{i + 1}  ★" if i in self._marks else str(i + 1)

    def set_marks(self, marks):
        marks = set(marks)
        if marks == self._marks:
            return
        changed = marks ^ self._marks
        self._marks = marks
        for i in changed:
            if 0 <= i < self.count():
                self.item(i).setText(self._label(i))

    def set_current(self, page: int):
        if 0 <= page < self.count() and self.currentRow() != page:
            self.blockSignals(True)
            self.setCurrentRow(page)
            self.blockSignals(False)
            self.scrollToItem(self.item(page), QAbstractItemView.ScrollHint.EnsureVisible)

    def showEvent(self, e):
        super().showEvent(e)
        self._timer.start()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._timer.start()

    def _load_visible(self):
        if not self.isVisible() or not self._path:
            return
        view = self.viewport().rect().adjusted(0, -300, 0, 600)
        for i in range(self.count()):
            if i in self._requested:
                continue
            if self.visualItemRect(self.item(i)).intersects(view):
                self._requested.add(i)
                path = self._path
                self.engine.render_once(path, i, THUMB.height() * 2, lambda img, i=i, p=path: self._thumb(p, i, img))

    def _thumb(self, path, i, img):
        if img is None or path != self._path or i >= self.count():
            return
        pm = QPixmap.fromImage(img).scaled(THUMB * 2, Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation)
        pm.setDevicePixelRatio(2.0)
        self.item(i).setIcon(QIcon(pm))


class SearchBar(QFrame):
    """Find text in the open PDF: type, Enter for the next match, Shift+Enter for the previous one."""

    searched = Signal(str)
    nextHit = Signal()
    prevHit = Signal()
    closed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Chip")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(12, 6, 6, 6)
        lay.setSpacing(6)
        self.field = QLineEdit()
        self.field.setPlaceholderText("Find in this PDF")
        self.field.setClearButtonEnabled(True)
        self.field.setMinimumWidth(220)
        self.field.setStyleSheet(f"QLineEdit {{ background: {theme.BG}; border: 1px solid {theme.STROKE_STRONG};"
                                 f" border-radius: 8px; padding: 6px 8px; font-size: 13px; }}"
                                 f"QLineEdit:focus {{ border-color: {theme.ACCENT}; }}")
        self.count = QLabel("")
        self.count.setObjectName("Muted")
        self.count.setMinimumWidth(92)
        up = IconButton("page_up", "Previous match  (Shift+Enter)", 32)
        down = IconButton("page_down", "Next match  (Enter)", 32)
        close = IconButton("close", "Close  (Esc)", 32)
        for w in (self.field, self.count, up, down, close):
            lay.addWidget(w)
        self._debounce = QTimer(self, singleShot=True, interval=280,
                                timeout=lambda: self.searched.emit(self.field.text().strip()))
        self.field.textChanged.connect(lambda _t: self._debounce.start())
        self.field.returnPressed.connect(self._enter)
        up.clicked.connect(self.prevHit.emit)
        down.clicked.connect(self.nextHit.emit)
        close.clicked.connect(self.closed.emit)
        self.field.installEventFilter(self)
        self.hide()

    def _enter(self):
        from PySide6.QtWidgets import QApplication
        if QApplication.keyboardModifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.prevHit.emit()
        else:
            if self._debounce.isActive():
                self._debounce.stop()
                self.searched.emit(self.field.text().strip())
            self.nextHit.emit()

    def eventFilter(self, obj, e):
        from PySide6.QtCore import QEvent
        if obj is self.field and e.type() == QEvent.Type.KeyPress and e.key() == Qt.Key.Key_Escape:
            self.closed.emit()
            return True
        return super().eventFilter(obj, e)

    def open(self):
        self.show()
        self.raise_()
        self.field.setFocus()
        self.field.selectAll()

    def set_count(self, text: str):
        self.count.setText(text)
