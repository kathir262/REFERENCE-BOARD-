"""The PDF reader: pages in one continuous column (or two side by side), rendered only when they come into view.

Wheel scrolls smoothly, Ctrl+wheel zooms around the cursor, drag to move the page, double-click to switch
between "fit width" and "whole page". After zooming in, the visible part of the page is rendered again at
full sharpness. Each PDF remembers where you were, its bookmarks and whether it shows two pages at a time.
Also: search highlights, and "snip" mode to drag a box around part of a page and put it on the board.
"""
import math

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from refpad.core import pdf
from refpad.ui import theme

GAP = 14
SIDE = 24
BAR_W = 10
TILE_ALIGN = 64


class PdfView(QWidget):
    pageChanged = Signal()
    contextRequested = Signal(int, object)        # page index, global QPointF
    snipped = Signal(int, object)                 # page, (x, y, w, h) as fractions of the page
    snipModeChanged = Signal(bool)

    def __init__(self, state, engine, parent=None):
        super().__init__(parent)
        self.state = state
        self.engine = engine
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.pad_top = 0
        self.pad_bottom = 0
        self.pad_left = 0          # room taken by the page list on the left
        self.doc = None
        self.info = None
        self._key = ""
        self._pw = 0.0             # page width on screen (px)
        self._cw = 0.0             # content width (one page, or two side by side)
        self._tops: list = []      # page top y in content px
        self._heights: list = []
        self._xs: list = []        # page x inside the content
        self._rows: list = []      # (top, height, [pages])
        self._row_of: list = []
        self._content_h = 0.0
        self.sx = 0.0              # scroll position (content px)
        self.sy = 0.0
        self._ty = None            # smooth-scroll target
        self._vel = 0.0
        self._drag = None
        self._thumb = None         # dragging the fast-scroll thumb
        self._hover_bar = False
        self._want = ()
        self._tiles_on = False
        self.current_page = 0
        self.hits: list = []       # search results: (page, [QRectF in page points])
        self.hit_index = -1
        self.snipping = False
        self._snip = None          # (page, start QPointF, end QPointF) while dragging
        self._clock = QElapsedTimer()
        self._anim = QTimer(self, interval=12, timeout=self._anim_step)
        self._idle = QTimer(self, singleShot=True, interval=160, timeout=self._sharpen)
        self._save = QTimer(self, singleShot=True, interval=600, timeout=self._remember)
        state.docsChanged.connect(self._doc_changed)
        engine.infoReady.connect(self._on_info)
        engine.pageReady.connect(self._on_page)
        self._doc_changed()

    # ------------------------------------------------------------------ document

    def _doc_changed(self):
        doc = self.state.doc
        if doc is self.doc:
            return
        if self.doc is not None:
            self._remember()
        self.doc = doc
        self.info = None
        self._key = pdf.norm(doc.path) if doc else ""
        self._tops, self._heights, self._xs, self._rows, self._row_of = [], [], [], [], []
        self._ty = None
        self._tiles_on = False
        self.hits, self.hit_index = [], -1
        self.set_snipping(False)
        if doc is not None:
            self.info = self.engine.info(doc.path)
            self._relayout(restore=True)
        self.update()
        self.pageChanged.emit()

    def _on_info(self, key):
        if key == self._key and self.doc is not None:
            self.info = self.engine.info(self.doc.path)
            if self.info and not self.info.error and self.doc.pages != self.info.count:
                self.doc.pages = self.info.count
                self.state.schedule_save()
            self._relayout(restore=True)
            self.update()
            self.pageChanged.emit()

    @property
    def ready(self) -> bool:
        return self.info is not None and not self.info.error and self.info.count > 0

    @property
    def page_count(self) -> int:
        return self.info.count if self.ready else 0

    @property
    def spread(self) -> bool:
        return bool(self.doc and self.doc.spread)

    def set_spread(self, on: bool):
        if self.doc is None or self.doc.spread == on:
            return
        page = self.current_page
        self.doc.spread = on
        self._relayout(restore=True)
        self.go_to_page(page, smooth=False)
        self.state.schedule_save()
        self.pageChanged.emit()

    # ------------------------------------------------------------------ layout

    def _avail(self):
        return (max(100.0, self.width() - self.pad_left - 2 * SIDE),
                max(100.0, self.height() - self.pad_top - self.pad_bottom))

    def _base_width(self) -> float:
        """Page width at zoom 1: the whole width, or half of it with two pages side by side."""
        aw, _ = self._avail()
        return (aw - GAP) / 2 if self.spread else aw

    def _row_pages(self):
        n = self.page_count
        if not self.spread:
            return [[i] for i in range(n)]
        rows = [[0]] if n else []                     # the cover on its own, like a book
        rows += [list(range(i, min(i + 2, n))) for i in range(1, n, 2)]
        return rows

    def _whole_page_zoom(self) -> float:
        _, ah = self._avail()
        if not self.ready:
            return 1.0
        rows = self._row_pages()
        r = self._row_of[self.current_page] if self._row_of and self.current_page < len(self._row_of) else 0
        pages = rows[min(r, len(rows) - 1)]
        a = max(self.info.aspect(i) for i in pages)
        return min(1.0, (ah - 2 * GAP) / a / max(1.0, self._base_width()))

    def effective_zoom(self) -> float:
        if self.doc is None:
            return 1.0
        return self._whole_page_zoom() if self.doc.zoom <= 0 else self.doc.zoom

    def _layout_rows(self):
        n = self.page_count
        self._pw = self._base_width() * self.effective_zoom()
        two = self.spread
        self._cw = 2 * self._pw + GAP if two else self._pw
        self._tops, self._heights, self._xs = [0.0] * n, [0.0] * n, [0.0] * n
        self._row_of, self._rows = [0] * n, []
        y = self.pad_top + GAP
        for r, pages in enumerate(self._row_pages()):
            hs = [self._pw * self.info.aspect(i) for i in pages]
            for k, i in enumerate(pages):
                self._tops[i], self._heights[i] = y, hs[k]
                if len(pages) == 1:
                    self._xs[i] = (self._cw - self._pw) / 2
                else:
                    self._xs[i] = k * (self._pw + GAP)
                self._row_of[i] = r
            self._rows.append((y, max(hs), pages))
            y += max(hs) + GAP
        self._content_h = y + self.pad_bottom

    def _relayout(self, restore: bool = False):
        if not self.ready:
            return
        anchor = None if (restore or not self._rows) else self._position()
        self._layout_rows()
        page, offset = (self.doc.page, self.doc.offset) if anchor is None else anchor
        self._set_position(page, offset)

    def _position(self):
        """(page, fraction) at the top of the view."""
        if not self._rows:
            return 0, 0.0
        y = self.sy + self.pad_top + GAP
        r = self._row_at_y(y)
        top, h, pages = self._rows[r]
        return pages[0], max(0.0, min(1.0, (y - top) / max(1.0, h)))

    def _set_position(self, page: int, offset: float):
        if not self._rows:
            return
        page = max(0, min(page, len(self._tops) - 1))
        top, h, _ = self._rows[self._row_of[page]]
        self.sy = top + offset * h - self.pad_top - GAP
        self._clamp()
        self._ty = None
        self._update_current()

    def _row_at_y(self, y: float) -> int:
        lo, hi = 0, len(self._rows) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self._rows[mid][0] <= y:
                lo = mid
            else:
                hi = mid - 1
        return lo

    def _page_at_y(self, y: float) -> int:
        return self._rows[self._row_at_y(y)][2][0] if self._rows else 0

    def page_at(self, pos: QPointF) -> int:
        """The page under a point on screen, or -1."""
        if not self._rows:
            return -1
        for i in self._rows[self._row_at_y(self.sy + pos.y())][2]:
            if self.page_rect(i).contains(pos):
                return i
        return -1

    def _max_sy(self) -> float:
        return max(0.0, self._content_h - self.height())

    def _max_sx(self) -> float:
        return max(0.0, self._cw + 2 * SIDE - (self.width() - self.pad_left))

    def _clamp(self):
        self.sy = max(0.0, min(self.sy, self._max_sy()))
        mx = self._max_sx()
        self.sx = max(0.0, min(self.sx, mx)) if mx > 0 else 0.0

    def _content_left(self) -> float:
        mx = self._max_sx()
        if mx > 0:
            return self.pad_left + SIDE - self.sx
        return self.pad_left + (self.width() - self.pad_left - self._cw) / 2

    def page_rect(self, i: int) -> QRectF:
        """Where page i is on screen."""
        return QRectF(self._content_left() + self._xs[i], self._tops[i] - self.sy, self._pw, self._heights[i])

    def _update_current(self):
        if not self._rows:
            return
        mid = self.sy + self.pad_top + (self.height() - self.pad_top - self.pad_bottom) / 2
        i = self._page_at_y(mid)
        if i != self.current_page:
            self.current_page = i
            self.pageChanged.emit()
        self._save.start()

    def _remember(self):
        if self.doc is not None and self._rows:
            self.doc.page, self.doc.offset = self._position()
            self.state.schedule_save()

    # ------------------------------------------------------------------ scrolling

    def scroll_by(self, dy: float, smooth: bool = True):
        if not smooth:
            self.sy += dy
            self._ty = None
            self._after_scroll()
            return
        base = self._ty if self._ty is not None else self.sy
        self._ty = max(0.0, min(base + dy, self._max_sy()))
        if not self._anim.isActive():
            self._clock.start()
            self._anim.start()

    def _anim_step(self):
        dt = max(1, self._clock.restart())
        if self._ty is not None:
            k = 1 - (1 - 0.25) ** (dt / 16)
            d = self._ty - self.sy
            if abs(d) < 0.5:
                self.sy, self._ty = self._ty, None
            else:
                self.sy += d * k
        elif abs(self._vel) > 0.05:
            self.sy += self._vel * dt
            self._vel *= 0.94 ** (dt / 16)
        else:
            self._vel = 0.0
            self._anim.stop()
            return
        self._after_scroll()

    def _after_scroll(self):
        before = self.sy
        self._clamp()
        if self.sy != before:
            self._vel = 0.0
        self._update_current()
        self.update()
        self._idle.start()

    def go_to_page(self, page: int, smooth: bool = True, offset: float = 0.0):
        if not self._rows:
            return
        page = max(0, min(page, len(self._tops) - 1))
        target = self._tops[page] + offset - self.pad_top - GAP
        if smooth:
            self.scroll_by(target - (self._ty if self._ty is not None else self.sy))
        else:
            self.sy = target
            self._after_scroll()

    def next_page(self):
        row = self._row_of[self.current_page] if self._row_of else 0
        if row + 1 < len(self._rows):
            self.go_to_page(self._rows[row + 1][2][0])

    def prev_page(self):
        if not self._rows:
            return
        row = self._row_of[self.current_page]
        top = self._rows[row][0] - self.pad_top - GAP
        if self.sy <= top + 2 and row > 0:
            row -= 1
        self.go_to_page(self._rows[row][2][0])

    # ------------------------------------------------------------------ zoom

    def set_zoom(self, zoom: float, anchor: QPointF = None):
        if self.doc is None or not self.ready:
            return
        anchor = anchor or QPointF(self.pad_left + (self.width() - self.pad_left) / 2,
                                   self.pad_top + (self.height() - self.pad_top - self.pad_bottom) / 2)
        cy = self.sy + anchor.y()
        r = self._row_at_y(cy)
        top, h, _ = self._rows[r]
        fy = (cy - top) / max(1.0, h)
        fx = (anchor.x() - self._content_left()) / max(1.0, self._cw)
        self.doc.zoom = max(0.2, min(8.0, zoom)) if zoom > 0 else zoom
        self._layout_rows()
        top, h, _ = self._rows[r]
        self.sy = top + fy * h - anchor.y()
        self._ty = None
        if self._max_sx() > 0:
            self.sx = SIDE + fx * self._cw - (anchor.x() - self.pad_left)
        self._clamp()
        self._update_current()
        self.update()
        self._idle.start()
        self.state.schedule_save()

    def zoom_by(self, factor: float, anchor: QPointF = None):
        self.set_zoom(self.effective_zoom() * factor, anchor)

    def toggle_fit(self):
        """Fit width <-> whole page."""
        if self.doc is None:
            return
        if self.doc.zoom <= 0 or abs(self.effective_zoom() - self._whole_page_zoom()) < 0.01:
            self.set_zoom(1.0)
        else:
            page = self.current_page
            self.set_zoom(-1)
            self.go_to_page(page, smooth=False)

    def fit_label(self) -> str:
        return "Fit width" if self.doc is not None and self.doc.zoom <= 0 else "Whole page"

    # ------------------------------------------------------------------ bookmarks

    def toggle_bookmark(self, page: int = None) -> bool:
        """Adds or removes a bookmark; returns True if the page is now bookmarked."""
        if self.doc is None:
            return False
        page = self.current_page if page is None else page
        marks = set(self.doc.bookmarks)
        marks ^= {page}
        self.doc.bookmarks = sorted(marks)
        self.state.schedule_save()
        self.update()
        self.pageChanged.emit()
        return page in marks

    # ------------------------------------------------------------------ search

    def set_hits(self, hits, index: int = -1):
        self.hits, self.hit_index = hits, index
        self.update()

    def show_hit(self, index: int):
        if not self.hits:
            return
        self.hit_index = index % len(self.hits)
        page, rects = self.hits[self.hit_index]
        if self.ready and rects:
            k = self._pw / max(1.0, self.info.sizes[page][0])
            y = rects[0].top() * k
            self.go_to_page(page, smooth=True, offset=max(0.0, y - (self.height() - self.pad_top - self.pad_bottom) / 3))
        self.update()

    def _paint_hits(self, p: QPainter, i: int, r: QRectF):
        if not self.hits:
            return
        k = r.width() / max(1.0, self.info.sizes[i][0])
        for n, (page, rects) in enumerate(self.hits):
            if page != i:
                continue
            current = n == self.hit_index
            p.setPen(QPen(theme.color("#D97706"), 2) if current else Qt.PenStyle.NoPen)
            p.setBrush(theme.color(theme.ACCENT, 0.55 if current else 0.32))
            for q in rects:
                p.drawRect(QRectF(r.x() + q.x() * k - 1, r.y() + q.y() * k - 1, q.width() * k + 2, q.height() * k + 2))

    # ------------------------------------------------------------------ snip

    def set_snipping(self, on: bool):
        if on == self.snipping:
            return
        self.snipping = on
        self._snip = None
        if on:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.unsetCursor()
        self.snipModeChanged.emit(on)
        self.update()

    def _paint_snip(self, p: QPainter):
        page, a, b = self._snip
        r = QRectF(a, b).normalized().intersected(self.page_rect(page))
        dim = QPainterPath()
        dim.addRect(self.page_rect(page))
        hole = QPainterPath()
        hole.addRect(r)
        p.fillPath(dim.subtracted(hole), QColor(0, 0, 0, 110))
        p.setPen(QPen(theme.color(theme.ACCENT), 2, Qt.PenStyle.DashLine))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(r)

    # ------------------------------------------------------------------ painting

    def _device_width(self) -> int:
        return max(1, round(self._pw * self.devicePixelRatioF()))

    def _base_key(self, i: int):
        bucket = min(pdf.MAX_PAGE_WIDTH, max(256, math.ceil(self._device_width() / 128) * 128))
        return pdf.Key(self._key, i, bucket, None)

    def _visible_pages(self):
        if not self._rows:
            return []
        top, bottom = self.sy, self.sy + self.height()
        r = self._row_at_y(top)
        out = []
        while r < len(self._rows) and self._rows[r][0] < bottom:
            if self._rows[r][0] + self._rows[r][1] > top:
                out += self._rows[r][2]
            r += 1
        return out

    def _tile_key(self, i: int):
        """Sharp render of only the visible part of page i (when zoomed beyond the normal render size)."""
        dw = self._device_width()
        if dw <= pdf.MAX_PAGE_WIDTH * 1.02:
            return None
        dpr = self.devicePixelRatioF()
        pr = self.page_rect(i)
        left, top = pr.left(), pr.top()
        x0 = max(0.0, self.pad_left - left) * dpr
        y0 = max(0.0, -top) * dpr
        x1 = min(self._pw, self.width() - left) * dpr
        y1 = min(self._heights[i], self.height() - top) * dpr
        if x1 <= x0 or y1 <= y0:
            return None
        a = TILE_ALIGN
        x0, y0 = int(x0 // a * a), int(y0 // a * a)
        dh = round(self._heights[i] * dpr)
        x1, y1 = min(dw, int(math.ceil(x1 / a) * a)), min(dh, int(math.ceil(y1 / a) * a))
        return pdf.Key(self._key, i, dw, (x0, y0, x1 - x0, y1 - y0))

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), theme.color(theme.BG))
        if self.doc is None:
            return
        if not self.ready:
            p.setPen(theme.color(theme.TEXT_2))
            f = p.font()
            f.setPointSizeF(11)
            p.setFont(f)
            text = self.info.error if self.info is not None else f"Opening “{self.doc.title}”…"
            p.drawText(self.rect().adjusted(40 + self.pad_left, self.pad_top, -40, -self.pad_bottom),
                       Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text)
            return
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        dpr = self.devicePixelRatioF()
        marks = set(self.doc.bookmarks)
        keys = []
        for i in self._visible_pages():
            r = self.page_rect(i)
            base = self._base_key(i)
            keys.append(base)
            img = self.engine.page(base) or self.engine.best_page(self._key, i, base.width)
            p.fillRect(r.adjusted(-1, 0, 1, 3), QColor(0, 0, 0, 70))
            if img is None:
                p.fillRect(r, QColor(250, 250, 250))
                p.setPen(QColor(150, 150, 150))
                p.drawText(r, Qt.AlignmentFlag.AlignCenter, str(i + 1))
            else:
                p.drawImage(r, img)
            if self._tiles_on:
                tk = self._tile_key(i)
                if tk is not None:
                    keys.append(tk)
                    tile = self.engine.page(tk)
                    if tile is not None:
                        x, y, w, h = tk.clip
                        p.drawImage(QRectF(r.x() + x / dpr, r.y() + y / dpr, w / dpr, h / dpr), tile)
            self._paint_hits(p, i, r)
            if i in marks:
                self._paint_ribbon(p, r)
        if self._snip:
            self._paint_snip(p)
        self._paint_bar(p)
        # Read ahead: the next two pages and the one before.
        if keys:
            last = max(k.page for k in keys)
            first = min(k.page for k in keys)
            for j in (last + 1, last + 2, first - 1):
                if 0 <= j < self.page_count:
                    keys.append(self._base_key(j))
        keys = tuple(dict.fromkeys(keys))
        if keys != self._want:
            self._want = keys
            self.engine.want(self, keys)

    @staticmethod
    def _paint_ribbon(p: QPainter, r: QRectF):
        w = max(10.0, min(22.0, r.width() * 0.045))
        x, y = r.right() - w * 1.8, r.top()
        path = QPainterPath()
        path.moveTo(x, y)
        path.lineTo(x + w, y)
        path.lineTo(x + w, y + w * 1.7)
        path.lineTo(x + w / 2, y + w * 1.25)
        path.lineTo(x, y + w * 1.7)
        path.closeSubpath()
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.color(theme.ACCENT))
        p.drawPath(path)
        p.restore()

    def _bar_geometry(self):
        top = self.pad_top + 4
        track = self.height() - self.pad_top - self.pad_bottom - 8
        if self._content_h <= self.height() or track <= 40:
            return None
        h = max(44.0, track * self.height() / self._content_h)
        y = top + (track - h) * (self.sy / max(1.0, self._max_sy()))
        return QRectF(self.width() - BAR_W - 4, y, BAR_W, h), top, track

    def _paint_bar(self, p: QPainter):
        g = self._bar_geometry()
        if g is None:
            return
        thumb, _, _ = g
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        active = self._thumb is not None or self._hover_bar
        w = BAR_W if active else 6
        r = QRectF(thumb.right() - w, thumb.y(), w, thumb.height())
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.color(theme.ACCENT if self._thumb is not None else theme.STROKE_STRONG, 0.95))
        p.drawRoundedRect(r, w / 2, w / 2)
        if self._thumb is not None:   # page bubble while fast-scrolling
            text = f"{self.current_page + 1} / {self.page_count}"
            f = QFont(p.font())
            f.setPointSizeF(11)
            f.setBold(True)
            p.setFont(f)
            tw = p.fontMetrics().horizontalAdvance(text) + 24
            b = QRectF(r.left() - tw - 10, r.center().y() - 17, tw, 34)
            p.setBrush(theme.color(theme.RAISED))
            p.setPen(theme.color(theme.STROKE_STRONG))
            p.drawRoundedRect(b, 17, 17)
            p.setPen(theme.color(theme.TEXT))
            p.drawText(b, Qt.AlignmentFlag.AlignCenter, text)

    def _sharpen(self):
        """After zooming/scrolling stops: render the visible parts at full sharpness."""
        if self._drag is None and self._thumb is None and self._ty is None:
            self._tiles_on = True
            self.update()

    def _on_page(self, key):
        if key in self._want:
            self.update()

    # ------------------------------------------------------------------ input

    def wheelEvent(self, e):
        d = e.angleDelta()
        if e.modifiers() & Qt.KeyboardModifier.ControlModifier:
            if d.y():
                self.zoom_by(1.0018 ** d.y(), e.position())
        elif e.modifiers() & Qt.KeyboardModifier.ShiftModifier or (d.x() and not d.y()):
            self.sx -= (d.x() or d.y()) * 1.2
            self._after_scroll()
        else:
            pd = e.pixelDelta().y()
            self.scroll_by(-(pd if pd else d.y() * 1.3), smooth=not pd)
        self._tiles_on = False
        e.accept()

    def mousePressEvent(self, e):
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        pos = e.position()
        if e.button() == Qt.MouseButton.RightButton:
            if self.snipping:
                self.set_snipping(False)
            elif self.ready:
                page = self.page_at(pos)
                self.contextRequested.emit(page if page >= 0 else self._page_at_y(self.sy + pos.y()), e.globalPosition())
            return
        if self.snipping and e.button() == Qt.MouseButton.LeftButton:
            page = self.page_at(pos)
            if page >= 0:
                self._snip = (page, pos, pos)
            return
        g = self._bar_geometry()
        if e.button() == Qt.MouseButton.LeftButton and g and pos.x() >= self.width() - BAR_W - 12:
            thumb, top, track = g
            if not thumb.contains(QPointF(thumb.center().x(), pos.y())):
                self._scroll_to_bar(pos.y() - thumb.height() / 2, g)
                thumb = self._bar_geometry()[0]
            self._thumb = pos.y() - thumb.y()
            self.update()
            return
        if e.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self._anim.stop()
            self._ty, self._vel = None, 0.0
            self._drag = {"last": pos, "samples": [(pos.y(), self._clock_ms())]}
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def _clock_ms(self):
        if not self._clock.isValid():
            self._clock.start()
        return self._clock.elapsed()

    def _scroll_to_bar(self, thumb_top, g):
        thumb, top, track = g
        frac = (thumb_top - top) / max(1.0, track - thumb.height())
        self.sy = max(0.0, min(1.0, frac)) * self._max_sy()
        self._ty = None
        self._after_scroll()

    def mouseMoveEvent(self, e):
        pos = e.position()
        if self._snip:
            page, a, _ = self._snip
            self._snip = (page, a, pos)
            self.update()
            return
        if self._thumb is not None:
            g = self._bar_geometry()
            if g:
                self._scroll_to_bar(pos.y() - self._thumb, g)
            return
        if self._drag is None:
            hover = pos.x() >= self.width() - BAR_W - 12 and self._bar_geometry() is not None
            if hover != self._hover_bar:
                self._hover_bar = hover
                self.update(self.width() - BAR_W - 8, 0, BAR_W + 8, self.height())
            return
        delta = pos - self._drag["last"]
        self._drag["last"] = pos
        self.sy -= delta.y()
        self.sx -= delta.x()
        s = self._drag["samples"]
        s.append((pos.y(), self._clock_ms()))
        del s[:-5]
        self._tiles_on = False
        self._after_scroll()

    def mouseReleaseEvent(self, e):
        if self._snip:
            page, a, b = self._snip
            self._snip = None
            pr = self.page_rect(page)
            r = QRectF(a, b).normalized().intersected(pr)
            if r.width() >= 12 and r.height() >= 12:
                frac = ((r.left() - pr.left()) / pr.width(), (r.top() - pr.top()) / pr.height(),
                        r.width() / pr.width(), r.height() / pr.height())
                self.snipped.emit(page, frac)
            self.update()
            return
        if self._thumb is not None:
            self._thumb = None
            self.update()
            self._idle.start()
            return
        d, self._drag = self._drag, None
        if not self.snipping:
            self.unsetCursor()
        if d and len(d["samples"]) >= 2:
            (y0, t0), (y1, t1) = d["samples"][0], d["samples"][-1]
            if 0 < t1 - t0 < 160 and self._clock_ms() - t1 < 60:
                self._vel = -(y1 - y0) / (t1 - t0)   # keep gliding after a quick flick
                self._clock.restart()
                self._anim.start()

    def mouseDoubleClickEvent(self, e):
        if self.snipping:
            return
        if e.button() == Qt.MouseButton.LeftButton and e.position().x() < self.width() - BAR_W - 12:
            self.toggle_fit()

    def keyPressEvent(self, e):
        k = e.key()
        view_h = self.height() - self.pad_top - self.pad_bottom
        if k == Qt.Key.Key_Escape and self.snipping:
            self.set_snipping(False)
        elif k in (Qt.Key.Key_Down, Qt.Key.Key_J):
            self.scroll_by(80)
        elif k in (Qt.Key.Key_Up, Qt.Key.Key_K):
            self.scroll_by(-80)
        elif k == Qt.Key.Key_PageDown or (k == Qt.Key.Key_Space and not e.modifiers()):
            self.scroll_by(view_h - 60)
        elif k == Qt.Key.Key_PageUp or (k == Qt.Key.Key_Space and e.modifiers() & Qt.KeyboardModifier.ShiftModifier):
            self.scroll_by(-(view_h - 60))
        elif k == Qt.Key.Key_Home:
            self.go_to_page(0)
        elif k == Qt.Key.Key_End:
            self.go_to_page(self.page_count - 1)
        elif k == Qt.Key.Key_Right and self._max_sx() <= 0:
            self.next_page()
        elif k == Qt.Key.Key_Left and self._max_sx() <= 0:
            self.prev_page()
        else:
            super().keyPressEvent(e)

    def resizeEvent(self, e):
        if self.ready and self._rows:
            pos = self._position()
            self._relayout()
            self._set_position(*pos)
        self._tiles_on = False
        self._idle.start()

    def set_padding(self, top: int, bottom: int, left: int = None):
        left = self.pad_left if left is None else left
        if (top, bottom, left) != (self.pad_top, self.pad_bottom, self.pad_left):
            self.pad_top, self.pad_bottom, self.pad_left = top, bottom, left
            if self.ready and self._rows:
                pos = self._position()
                self._relayout()
                self._set_position(*pos)
            self.update()

    def hideEvent(self, e):
        self._remember()
        self.engine.release(self)
        self._want = ()
        self.set_snipping(False)
