"""The PDF reader: pages in one continuous column, rendered only when they come into view.

Wheel scrolls smoothly, Ctrl+wheel zooms around the cursor, drag to move the page, double-click to switch
between "fit width" and "whole page". After zooming in, the visible part of the page is rendered again at
full sharpness. Each PDF remembers where you were.
"""
import math

from PySide6.QtCore import QElapsedTimer, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QPainter
from PySide6.QtWidgets import QWidget

from refpad.core import pdf
from refpad.ui import theme

GAP = 14
SIDE = 24
BAR_W = 10
TILE_ALIGN = 64


class PdfView(QWidget):
    pageChanged = Signal()
    contextRequested = Signal(int, object)   # page index, global QPointF

    def __init__(self, state, engine, parent=None):
        super().__init__(parent)
        self.state = state
        self.engine = engine
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.pad_top = 0
        self.pad_bottom = 0
        self.doc = None
        self.info = None
        self._key = ""
        self._pw = 0.0             # page width on screen (px)
        self._tops: list = []      # page top y in content px
        self._heights: list = []
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
        self._tops, self._heights = [], []
        self._ty = None
        self._tiles_on = False
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

    # ------------------------------------------------------------------ layout

    def _avail(self):
        return max(100.0, self.width() - 2 * SIDE), max(100.0, self.height() - self.pad_top - self.pad_bottom)

    def _whole_page_zoom(self) -> float:
        aw, ah = self._avail()
        a = self.info.aspect(self.current_page) if self.ready else 1.414
        return min(1.0, (ah - 2 * GAP) / a / aw)

    def effective_zoom(self) -> float:
        if self.doc is None:
            return 1.0
        return self._whole_page_zoom() if self.doc.zoom <= 0 else self.doc.zoom

    def _relayout(self, restore: bool = False):
        if not self.ready:
            return
        anchor = None if restore else self._position()
        aw, _ = self._avail()
        self._pw = aw * self.effective_zoom()
        y = self.pad_top + GAP
        self._tops, self._heights = [], []
        for i in range(self.info.count):
            h = self._pw * self.info.aspect(i)
            self._tops.append(y)
            self._heights.append(h)
            y += h + GAP
        self._content_h = y + self.pad_bottom
        page, offset = (self.doc.page, self.doc.offset) if anchor is None else anchor
        self._set_position(page, offset)

    def _position(self):
        """(page, fraction) at the top of the view."""
        if not self._tops:
            return 0, 0.0
        y = self.sy + self.pad_top + GAP
        i = self._page_at_y(y)
        return i, max(0.0, min(1.0, (y - self._tops[i]) / max(1.0, self._heights[i])))

    def _set_position(self, page: int, offset: float):
        if not self._tops:
            return
        page = max(0, min(page, len(self._tops) - 1))
        self.sy = self._tops[page] + offset * self._heights[page] - self.pad_top - GAP
        self._clamp()
        self._ty = None
        self._update_current()

    def _page_at_y(self, y: float) -> int:
        lo, hi = 0, len(self._tops) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if self._tops[mid] <= y:
                lo = mid
            else:
                hi = mid - 1
        return lo

    def _max_sy(self) -> float:
        return max(0.0, self._content_h - self.height())

    def _max_sx(self) -> float:
        return max(0.0, self._pw + 2 * SIDE - self.width())

    def _clamp(self):
        self.sy = max(0.0, min(self.sy, self._max_sy()))
        mx = self._max_sx()
        self.sx = max(0.0, min(self.sx, mx)) if mx > 0 else 0.0

    def _page_left(self) -> float:
        mx = self._max_sx()
        return (SIDE - self.sx) if mx > 0 else (self.width() - self._pw) / 2

    def _update_current(self):
        if not self._tops:
            return
        mid = self.sy + self.pad_top + (self.height() - self.pad_top - self.pad_bottom) / 2
        i = self._page_at_y(mid)
        if i != self.current_page:
            self.current_page = i
            self.pageChanged.emit()
        self._save.start()

    def _remember(self):
        if self.doc is not None and self._tops:
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

    def go_to_page(self, page: int, smooth: bool = True):
        if not self._tops:
            return
        page = max(0, min(page, len(self._tops) - 1))
        target = self._tops[page] - self.pad_top - GAP
        if smooth:
            self.scroll_by(target - (self._ty if self._ty is not None else self.sy))
        else:
            self.sy = target
            self._after_scroll()

    def next_page(self):
        self.go_to_page(self.current_page + 1)

    def prev_page(self):
        top = self._tops[self.current_page] - self.pad_top - GAP if self._tops else 0
        self.go_to_page(self.current_page - 1 if self.sy <= top + 2 else self.current_page)

    # ------------------------------------------------------------------ zoom

    def set_zoom(self, zoom: float, anchor: QPointF = None):
        if self.doc is None or not self.ready:
            return
        anchor = anchor or QPointF(self.width() / 2, self.pad_top + (self.height() - self.pad_top - self.pad_bottom) / 2)
        cy = self.sy + anchor.y()
        i = self._page_at_y(cy)
        fy = (cy - self._tops[i]) / max(1.0, self._heights[i])
        fx = (anchor.x() - self._page_left()) / max(1.0, self._pw)
        self.doc.zoom = max(0.2, min(8.0, zoom)) if zoom > 0 else zoom
        self._relayout_keep(i, fy, fx, anchor)

    def _relayout_keep(self, i, fy, fx, anchor):
        aw, _ = self._avail()
        self._pw = aw * self.effective_zoom()
        y = self.pad_top + GAP
        for j in range(len(self._tops)):
            h = self._pw * self.info.aspect(j)
            self._tops[j], self._heights[j] = y, h
            y += h + GAP
        self._content_h = y + self.pad_bottom
        self.sy = self._tops[i] + fy * self._heights[i] - anchor.y()
        self._ty = None
        if self._max_sx() > 0:
            self.sx = SIDE + fx * self._pw - anchor.x()
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
            self.set_zoom(-1)
            self.go_to_page(self.current_page, smooth=False)

    def fit_label(self) -> str:
        return "Fit width" if self.doc is not None and self.doc.zoom <= 0 else "Whole page"

    # ------------------------------------------------------------------ painting

    def _device_width(self) -> int:
        return max(1, round(self._pw * self.devicePixelRatioF()))

    def _base_key(self, i: int):
        bucket = min(pdf.MAX_PAGE_WIDTH, max(256, math.ceil(self._device_width() / 128) * 128))
        return pdf.Key(self._key, i, bucket, None)

    def _visible_pages(self):
        if not self._tops:
            return []
        top, bottom = self.sy, self.sy + self.height()
        i = self._page_at_y(top)
        out = []
        while i < len(self._tops) and self._tops[i] < bottom:
            if self._tops[i] + self._heights[i] > top:
                out.append(i)
            i += 1
        return out

    def _tile_key(self, i: int):
        """Sharp render of only the visible part of page i (when zoomed beyond the normal render size)."""
        dw = self._device_width()
        if dw <= pdf.MAX_PAGE_WIDTH * 1.02:
            return None
        dpr = self.devicePixelRatioF()
        left = self._page_left()
        top = self._tops[i] - self.sy
        x0 = max(0.0, -left) * dpr
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
            p.drawText(self.rect().adjusted(40, self.pad_top, -40, -self.pad_bottom),
                       Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap, text)
            return
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        dpr = self.devicePixelRatioF()
        left = self._page_left()
        keys = []
        for i in self._visible_pages():
            r = QRectF(left, self._tops[i] - self.sy, self._pw, self._heights[i])
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
            if self.ready:
                self.contextRequested.emit(self._page_at_y(self.sy + pos.y()), e.globalPosition())
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
        if self._thumb is not None:
            self._thumb = None
            self.update()
            self._idle.start()
            return
        d, self._drag = self._drag, None
        self.unsetCursor()
        if d and len(d["samples"]) >= 2:
            (y0, t0), (y1, t1) = d["samples"][0], d["samples"][-1]
            if 0 < t1 - t0 < 160 and self._clock_ms() - t1 < 60:
                self._vel = -(y1 - y0) / (t1 - t0)   # keep gliding after a quick flick
                self._clock.restart()
                self._anim.start()

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and e.position().x() < self.width() - BAR_W - 12:
            self.toggle_fit()

    def keyPressEvent(self, e):
        k = e.key()
        view_h = self.height() - self.pad_top - self.pad_bottom
        if k in (Qt.Key.Key_Down, Qt.Key.Key_J):
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
        if self.ready and self._tops:
            pos = self._position()
            self._relayout()
            self._set_position(*pos)
        self._tiles_on = False
        self._idle.start()

    def set_padding(self, top: int, bottom: int):
        if (top, bottom) != (self.pad_top, self.pad_bottom):
            self.pad_top, self.pad_bottom = top, bottom
            if self.ready and self._tops:
                pos = self._position()
                self._relayout()
                self._set_position(*pos)

    def hideEvent(self, e):
        self._remember()
        self.engine.release(self)
        self._want = ()
