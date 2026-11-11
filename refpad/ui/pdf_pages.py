"""Choose which PDF pages to add to the board: all of them, page numbers like "1-5, 8, 12-20",
or by clicking page thumbnails. Thumbnails render as they scroll into view."""
import re
from pathlib import Path

from PySide6.QtCore import QSize, Qt, QTimer
from PySide6.QtGui import QColor, QIcon, QPixmap
from PySide6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QLabel, QLineEdit, QListView, QListWidget,
                               QListWidgetItem, QPushButton, QVBoxLayout)

from refpad.ui import theme

THUMB = QSize(112, 150)


def parse_pages(text: str, count: int):
    """'1-5, 8, 12-' -> sorted page indexes (0-based). Returns None when the text can't be understood."""
    pages = set()
    for part in re.split(r"[,\s;]+", text.strip()):
        if not part:
            continue
        m = re.fullmatch(r"(\d*)\s*[-–]\s*(\d*)", part)
        if m and (m.group(1) or m.group(2)):
            a = int(m.group(1)) if m.group(1) else 1
            b = int(m.group(2)) if m.group(2) else count
            if a > b:
                a, b = b, a
        elif part.isdigit():
            a = b = int(part)
        else:
            return None
        if a < 1 or a > count:
            return None
        pages.update(range(a - 1, min(b, count)))
    return sorted(pages)


def pages_text(pages) -> str:
    """[0,1,2,3,7] -> '1-4, 8'"""
    out, run = [], []
    for p in sorted(pages):
        if run and p == run[-1] + 1:
            run.append(p)
        else:
            if run:
                out.append(f"{run[0] + 1}-{run[-1] + 1}" if len(run) > 1 else f"{run[0] + 1}")
            run = [p]
    if run:
        out.append(f"{run[0] + 1}-{run[-1] + 1}" if len(run) > 1 else f"{run[0] + 1}")
    return ", ".join(out)


class PdfPagesDialog(QDialog):
    def __init__(self, parent, path: str, count: int, engine, preselect=None):
        super().__init__(parent)
        self.path, self.count, self.engine = path, count, engine
        self.pages = []
        self._closed = False
        self._requested = set()
        self._typing = False
        self.setWindowTitle("Add PDF pages to the board")
        self.resize(760, 640)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(22, 20, 22, 18)
        lay.setSpacing(12)

        title = QLabel(f"Add pages from “{Path(path).stem}”")
        title.setObjectName("DialogTitle")
        lay.addWidget(title)
        sub = QLabel(f"{count} pages. Click pages to choose them, or type page numbers.")
        sub.setObjectName("Muted")
        lay.addWidget(sub)

        row = QHBoxLayout()
        row.setSpacing(8)
        self.all_btn = self._btn("All pages")
        self.none_btn = self._btn("None")
        self.all_btn.clicked.connect(lambda: self._select(range(count)))
        self.none_btn.clicked.connect(lambda: self._select([]))
        self.field = QLineEdit()
        self.field.setPlaceholderText("Pages, e.g. 1-5, 8, 12-20")
        self.field.setClearButtonEnabled(True)
        self.field.setStyleSheet(f"QLineEdit {{ background: {theme.RAISED}; border: 1px solid {theme.STROKE_STRONG};"
                                 f" border-radius: 10px; padding: 7px 10px; font-size: 13px; }}"
                                 f"QLineEdit:focus {{ border-color: {theme.ACCENT}; }}")
        self.field.textEdited.connect(self._typed)
        row.addWidget(self.all_btn)
        row.addWidget(self.none_btn)
        row.addSpacing(6)
        row.addWidget(self.field, 1)
        lay.addLayout(row)

        self.grid = QListWidget()
        self.grid.setViewMode(QListView.ViewMode.IconMode)
        self.grid.setIconSize(THUMB)
        self.grid.setGridSize(QSize(THUMB.width() + 22, THUMB.height() + 34))
        self.grid.setResizeMode(QListView.ResizeMode.Adjust)
        self.grid.setMovement(QListView.Movement.Static)
        self.grid.setUniformItemSizes(True)
        self.grid.setSelectionMode(QAbstractItemView.SelectionMode.MultiSelection)
        self.grid.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.grid.setStyleSheet(
            f"QListWidget {{ background: {theme.BG}; border: 1px solid {theme.STROKE}; border-radius: 12px; padding: 8px; }}"
            f"QListWidget::item {{ color: {theme.TEXT_2}; border: 2px solid transparent; border-radius: 8px; padding: 4px; }}"
            f"QListWidget::item:selected {{ background: rgba(250, 204, 21, 0.14); border-color: {theme.ACCENT}; color: {theme.ACCENT}; }}"
            f"QListWidget::item:hover {{ background: {theme.RAISED}; }}")
        blank = QPixmap(THUMB)
        blank.fill(QColor(theme.RAISED))
        placeholder = QIcon(blank)
        for i in range(count):
            it = QListWidgetItem(placeholder, str(i + 1))
            it.setTextAlignment(Qt.AlignmentFlag.AlignHCenter)
            self.grid.addItem(it)
        self.grid.itemSelectionChanged.connect(self._selection_changed)
        self.grid.verticalScrollBar().valueChanged.connect(lambda _v: self._thumbs_timer.start())
        lay.addWidget(self.grid, 1)

        bottom = QHBoxLayout()
        self.info = QLabel()
        self.info.setObjectName("Muted")
        self.info.setWordWrap(True)
        cancel = self._btn("Cancel")
        cancel.clicked.connect(self.reject)
        self.ok = self._btn("Add", "primary")
        self.ok.clicked.connect(self.accept)
        bottom.addWidget(self.info, 1)
        bottom.addWidget(cancel)
        bottom.addWidget(self.ok)
        lay.addLayout(bottom)

        self._thumbs_timer = QTimer(self, singleShot=True, interval=60, timeout=self._load_visible)
        self._select(range(count) if preselect is None else preselect)
        if preselect:
            QTimer.singleShot(0, lambda: self.grid.scrollToItem(self.grid.item(min(preselect))))

    def _btn(self, text, kind="secondary"):
        b = QPushButton(text)
        b.setProperty("kind", kind)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        return b

    # ------------------------------------------------------------------ selection

    def _select(self, pages):
        wanted = set(pages)
        self.grid.blockSignals(True)
        for i in range(self.count):
            self.grid.item(i).setSelected(i in wanted)
        self.grid.blockSignals(False)
        self._selection_changed()

    def _typed(self, text):
        pages = parse_pages(text, self.count) if text.strip() else []
        if pages is None:
            self.info.setText(f"Type page numbers between 1 and {self.count}, like 1-5, 8, 12-20")
            self.info.setStyleSheet(f"color: {theme.DANGER};")
            self.ok.setEnabled(False)
            return
        self._typing = True
        self._select(pages)
        self._typing = False
        if pages:
            self.grid.scrollToItem(self.grid.item(pages[0]))

    def _selection_changed(self):
        self.pages = sorted(self.grid.row(it) for it in self.grid.selectedItems())
        n = len(self.pages)
        if not self._typing:
            self.field.setText("" if n in (0, self.count) else pages_text(self.pages))
        self.ok.setEnabled(n > 0)
        self.ok.setText(f"Add {n} page{'s' if n != 1 else ''}" if n else "Add")
        self.info.setStyleSheet("")
        if n == 0:
            self.info.setText("No pages chosen.")
        elif n > 60:
            self.info.setText(f"{n} pages will be added one by one; you can keep working, or stop it from the message at the bottom.")
        else:
            self.info.setText(f"{n} of {self.count} pages chosen.")

    # ------------------------------------------------------------------ thumbnails

    def showEvent(self, e):
        super().showEvent(e)
        self._thumbs_timer.start()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._thumbs_timer.start()

    def _load_visible(self):
        view = self.grid.viewport().rect().adjusted(0, -200, 0, 400)   # a little ahead of the scroll
        for i in range(self.count):
            if i in self._requested:
                continue
            if self.grid.visualItemRect(self.grid.item(i)).intersects(view):
                self._requested.add(i)
                self.engine.render_once(self.path, i, THUMB.height() * 2, lambda img, i=i: self._thumb(i, img))

    def _thumb(self, i, img):
        if self._closed or img is None:
            return
        pm = QPixmap.fromImage(img).scaled(THUMB * 2, Qt.AspectRatioMode.KeepAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation)
        pm.setDevicePixelRatio(2.0)
        self.grid.item(i).setIcon(QIcon(pm))

    def done(self, r):
        self._closed = True
        super().done(r)
