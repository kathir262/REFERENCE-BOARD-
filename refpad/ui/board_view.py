"""The reference board: an endless canvas of images you can move, resize, flip and rotate.

Smoothness tricks:
- Images small on screen are drawn from their 512 px preview; the large copy loads only when needed.
- When zooming stops, every visible image is pre-scaled (on a background thread) to its exact size on
  screen with flip, rotation and black & white applied. Panning then only copies ready-made pixels.
- The dotted background is one tiled fill, images off screen are skipped entirely.
"""
import math

from PySide6.QtCore import QElapsedTimer, QEvent, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen, QPixmap, QTransform
from PySide6.QtWidgets import QWidget

from refpad.core import images
from refpad.ui import theme

MIN_ZOOM, MAX_ZOOM = 0.02, 16.0
HANDLE_R = 7
MAX_BAKED_PIXELS = 3200 * 3200


def _bake(src: QImage, tw: int, th: int, rot: int, flip: bool, gray: bool) -> QImage:
    img = src.scaled(tw, th, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    if gray:
        img = images.grayscale(img)
    if rot or flip:
        t = QTransform()
        if flip:
            t.scale(-1, 1)
        t.rotate(90 * rot)
        img = img.transformed(t)
    return images.normalize(img)


class BoardView(QWidget):
    contextRequested = Signal(object, object)   # item (or None), global QPointF
    selectionChanged = Signal()

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.grabGesture(Qt.GestureType.PinchGesture)
        self.cx, self.cy, self.zoom = state.view if state.view else (0.0, 0.0, 0.5)
        self.selected: list = []
        self.pad_top = 0       # parts of the view covered by bars (used when fitting)
        self.pad_bottom = 0
        self._drag = None
        self._space = False
        self._display = {}     # item id -> (signature, pre-scaled QImage)
        self._pending = set()
        self._grid = None      # (tile size, pixmap)
        self._idle = QTimer(self, singleShot=True, interval=120, timeout=self._bake_visible)
        self._anim = QTimer(self, interval=12, timeout=self._anim_step)
        self._anim_clock = QElapsedTimer()
        self._target = None    # (cx, cy, zoom) or None
        self._anchor = None    # (board x, board y, screen x, screen y) kept still while zooming
        self._added = []
        self._reveal = QTimer(self, singleShot=True, interval=220, timeout=self._reveal_added)
        state.boardChanged.connect(self._on_board_changed)
        state.itemsMoved.connect(self.update)
        state.itemsAdded.connect(self._on_items_added)
        state.boardReplaced.connect(self._on_replaced)
        images.cache.changed.connect(self._on_cache_changed)

    # ------------------------------------------------------------------ coordinates

    def to_board(self, p: QPointF) -> QPointF:
        return QPointF((p.x() - self.width() / 2) / self.zoom + self.cx, (p.y() - self.height() / 2) / self.zoom + self.cy)

    def screen_rect(self, it) -> QRectF:
        ew, eh = it.ew * self.zoom, it.eh * self.zoom
        x = (it.cx - self.cx) * self.zoom + self.width() / 2 - ew / 2
        y = (it.cy - self.cy) * self.zoom + self.height() / 2 - eh / 2
        return QRectF(x, y, ew, eh)

    def item_at(self, p: QPointF):
        for it in reversed(self.state.items):
            if self.screen_rect(it).contains(p):
                return it
        return None

    def _handle_hit(self, p: QPointF) -> bool:
        if len(self.selected) != 1:
            return False
        br = self.screen_rect(self.selected[0]).bottomRight()
        return math.hypot(p.x() - br.x(), p.y() - br.y()) <= HANDLE_R + 6

    # ------------------------------------------------------------------ selection

    def set_selected(self, items):
        items = [it for it in items if it in self.state.items]
        if items != self.selected:
            self.selected = items
            self.selectionChanged.emit()
            self.update()

    def select_all(self):
        self.set_selected(list(self.state.items))

    # ------------------------------------------------------------------ camera

    def _clamp(self, z: float) -> float:
        return max(MIN_ZOOM, min(MAX_ZOOM, z))

    def animate_to(self, cx: float, cy: float, zoom: float):
        self._anchor = None
        self._target = (cx, cy, self._clamp(zoom))
        self._start_anim()

    def _zoom_at(self, factor: float, sp: QPointF):
        base = self._target[2] if (self._target and self._anchor) else self.zoom
        z = self._clamp(base * factor)
        b = self.to_board(sp)          # the point under the cursor stays under the cursor
        bx, by = b.x(), b.y()
        self._anchor = (bx, by, sp.x(), sp.y())
        self._target = (bx - (sp.x() - self.width() / 2) / z, by - (sp.y() - self.height() / 2) / z, z)
        self._start_anim()

    def _start_anim(self):
        if not self._anim.isActive():
            self._anim_clock.start()
            self._anim.start()

    def _stop_anim(self):
        self._anim.stop()
        self._target = self._anchor = None

    def _anim_step(self):
        if self._target is None:
            self._anim.stop()
            return
        dt = max(1, self._anim_clock.restart())
        k = 1 - (1 - 0.3) ** (dt / 16)
        tx, ty, tz = self._target
        z = math.exp(math.log(self.zoom) + (math.log(tz) - math.log(self.zoom)) * k)
        done = abs(math.log(tz / z)) < 0.002
        if self._anchor:
            bx, by, sx, sy = self._anchor
            z = tz if done else z
            self.zoom = z
            self.cx = bx - (sx - self.width() / 2) / z
            self.cy = by - (sy - self.height() / 2) / z
        else:
            self.zoom = tz if done else z
            self.cx += (tx - self.cx) * (1 if done else k)
            self.cy += (ty - self.cy) * (1 if done else k)
            done = done and abs(tx - self.cx) * self.zoom < 0.5 and abs(ty - self.cy) * self.zoom < 0.5
        if done:
            self._stop_anim()
            self._camera_settled()
        self.update()

    def _camera_settled(self):
        self.state.view = [round(self.cx, 2), round(self.cy, 2), round(self.zoom, 5)]
        self.state.schedule_save()
        self._idle.start()

    def _fit_rect(self, r: QRectF, animate: bool = True, max_zoom: float = 1.5):
        if r.isEmpty():
            return
        margin = 48
        aw = max(50, self.width() - 2 * margin)
        ah = max(50, self.height() - self.pad_top - self.pad_bottom - 2 * margin)
        z = self._clamp(min(aw / r.width(), ah / r.height(), max_zoom))
        free_center = self.pad_top + (self.height() - self.pad_top - self.pad_bottom) / 2
        cx = r.center().x()
        cy = r.center().y() - (free_center - self.height() / 2) / z
        if animate and self.isVisible():
            self.animate_to(cx, cy, z)
        else:
            self._stop_anim()
            self.cx, self.cy, self.zoom = cx, cy, z
            self._camera_settled()
            self.update()

    def fit_all(self, animate: bool = True):
        items = self.state.items
        if not items:
            return
        r = items[0].bounds()
        for it in items[1:]:
            r = r.united(it.bounds())
        self._fit_rect(r, animate)

    def fit_item(self, it):
        self._fit_rect(it.bounds(), True, max_zoom=MAX_ZOOM)

    def zoom_step(self, factor: float):
        self._zoom_at(factor, QPointF(self.width() / 2, self.pad_top + (self.height() - self.pad_top - self.pad_bottom) / 2))

    # ------------------------------------------------------------------ painting

    def _paint_grid(self, p: QPainter):
        s = 40 * self.zoom
        while s < 22:
            s *= 2
        while s >= 88:
            s /= 2
        t = max(8, round(s))
        if not self._grid or self._grid[0] != t:
            pm = QPixmap(t, t)
            pm.fill(theme.color(theme.BG))
            gp = QPainter(pm)
            gp.setRenderHint(QPainter.RenderHint.Antialiasing)
            gp.setPen(Qt.PenStyle.NoPen)
            gp.setBrush(QColor(0x2A, 0x2A, 0x31))
            gp.drawEllipse(QPointF(t / 2, t / 2), 1.25, 1.25)
            gp.end()
            self._grid = (t, pm)
        ox = (self.width() / 2 - self.cx * self.zoom) % t - t / 2
        oy = (self.height() / 2 - self.cy * self.zoom) % t - t / 2
        p.drawTiledPixmap(self.rect(), self._grid[1], QPointF(-ox, -oy).toPoint())

    def paintEvent(self, e):
        p = QPainter(self)
        self._paint_grid(p)
        items = self.state.items
        if not items:
            return
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        view = QRectF(self.rect()).adjusted(-4, -4, 4, 4)
        need_bake = False
        for it in items:
            r = self.screen_rect(it)
            if r.intersects(view) and r.width() >= 1 and r.height() >= 1:
                need_bake |= self._draw_item(p, it, r)
        if need_bake and self._drag is None and self._target is None and not self._idle.isActive():
            self._idle.start()
        self._paint_selection(p)

    def _signature(self, it, r: QRectF):
        return (it.image, round(r.width()), round(r.height()), it.rot, it.flip, it.gray)

    def _draw_item(self, p: QPainter, it, r: QRectF) -> bool:
        """Draws one image; returns True when a sharper pre-scaled version is worth making."""
        cached = self._display.get(it.id)
        if cached and cached[0] == self._signature(it, r):
            img = cached[1]
            if not img.hasAlphaChannel():
                self._shadow(p, r)
            p.drawImage(QPointF(round(r.x()), round(r.y())), img)
            return False
        src = None
        if max(r.width(), r.height()) > images.PREVIEW_SIDE * 1.1 and not it.gray:
            src = images.cache.large(it.image)
        if src is None:
            src = images.cache.preview(it.image, it.gray)
        if src is None:
            p.fillRect(r, theme.color(theme.RAISED))
            return False
        if not src.hasAlphaChannel():
            self._shadow(p, r)
        p.save()
        p.translate(r.center())
        if it.flip:
            p.scale(-1, 1)
        p.rotate(90 * it.rot)
        w, h = (r.width(), r.height()) if it.rot % 2 == 0 else (r.height(), r.width())
        p.drawImage(QRectF(-w / 2, -h / 2, w, h), src)
        p.restore()
        return True

    @staticmethod
    def _shadow(p: QPainter, r: QRectF):
        if r.width() < 12:
            return
        p.fillRect(r.adjusted(-2, 1, 2, 5), QColor(0, 0, 0, 34))
        p.fillRect(r.adjusted(-1, 1, 1, 3), QColor(0, 0, 0, 60))

    def _paint_selection(self, p: QPainter):
        if not self.selected:
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(theme.color(theme.ACCENT), 2)
        pen.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        for it in self.selected:
            r = self.screen_rect(it).adjusted(-1, -1, 1, 1)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(r)
        if len(self.selected) == 1:
            br = self.screen_rect(self.selected[0]).bottomRight()
            p.setPen(QPen(theme.color(theme.BG), 2))
            p.setBrush(theme.color(theme.ACCENT))
            p.drawEllipse(br, HANDLE_R, HANDLE_R)

    # ------------------------------------------------------------------ pre-scaled images

    def _bake_visible(self):
        if self._drag is not None or self._target is not None:
            self._idle.start()
            return
        view = QRectF(self.rect())
        keep = set()
        for it in self.state.items:
            r = self.screen_rect(it)
            if not r.intersects(view):
                continue
            keep.add(it.id)
            w, h = round(r.width()), round(r.height())
            if w < 4 or h < 4 or w * h > MAX_BAKED_PIXELS:
                continue
            sig = self._signature(it, r)
            cached = self._display.get(it.id)
            if (cached and cached[0] == sig) or (it.id, sig) in self._pending:
                continue
            src = images.cache.large(it.image) if max(w, h) > images.PREVIEW_SIDE else images.cache.preview(it.image)
            if src is None:
                continue
            tw, th = (w, h) if it.rot % 2 == 0 else (h, w)
            self._pending.add((it.id, sig))
            images.run_async(lambda s=src, a=(tw, th, it.rot, it.flip, it.gray): _bake(s, *a),
                             lambda img, iid=it.id, sg=sig: self._baked(iid, sg, img))
        for iid in [i for i in self._display if i not in keep]:
            del self._display[iid]

    def _baked(self, iid, sig, img):
        self._pending.discard((iid, sig))
        if not isinstance(img, QImage):
            return
        it = next((i for i in self.state.items if i.id == iid), None)
        if it is not None and self._signature(it, self.screen_rect(it)) == sig:
            self._display[iid] = (sig, img)
            self.update(self.screen_rect(it).toAlignedRect().adjusted(-3, -3, 6, 6))

    def _on_cache_changed(self):
        if self.isVisible():
            self.update()
            self._idle.start()

    def _on_board_changed(self):
        if any(it not in self.state.items for it in self.selected):
            self.set_selected([it for it in self.selected if it in self.state.items])
        self.update()
        self._idle.start()

    def _on_replaced(self):
        """Another board was opened (or a new one started): its own camera, nothing selected."""
        self._added = []
        self._reveal.stop()
        self._display.clear()
        self._stop_anim()
        self.selected = []
        self.selectionChanged.emit()
        if self.state.view:
            self.cx, self.cy, self.zoom = self.state.view
        else:
            self.cx, self.cy, self.zoom = 0.0, 0.0, 0.5
            if self.state.items:
                QTimer.singleShot(0, lambda: self.fit_all(animate=False))
        self.update()
        self._idle.start()

    def _on_items_added(self, new):
        self._added.extend(new)
        self._reveal.start()

    def _reveal_added(self):
        added, self._added = self._added, []
        added = [it for it in added if it in self.state.items]
        if not added:
            return
        view = QRectF(self.rect()).adjusted(0, self.pad_top, 0, -self.pad_bottom)
        if all(view.contains(self.screen_rect(it)) for it in added):
            return
        self.fit_all(animate=len(self.state.items) > len(added))

    # ------------------------------------------------------------------ mouse

    def mousePressEvent(self, e):
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        pos = e.position()
        if self._target is not None:
            self._stop_anim()
            self._camera_settled()
        if e.button() == Qt.MouseButton.MiddleButton or (e.button() == Qt.MouseButton.LeftButton and self._space):
            self._drag = {"kind": "pan", "last": pos}
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        if e.button() == Qt.MouseButton.RightButton:
            it = self.item_at(pos)
            if it is not None and it not in self.selected:
                self.set_selected([it])
            elif it is None:
                self.set_selected([])
            self.contextRequested.emit(it, e.globalPosition())
            return
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if self._handle_hit(pos):
            it = self.selected[0]
            b = it.bounds()
            self._drag = {"kind": "resize", "item": it, "left": b.left(), "top": b.top(),
                          "ew": b.width(), "eh": b.height(), "scale": it.scale}
            return
        it = self.item_at(pos)
        additive = bool(e.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
        if it is not None:
            if additive:
                if it in self.selected:
                    self.set_selected([i for i in self.selected if i is not it])
                    return
                self.set_selected(self.selected + [it])
            elif it not in self.selected:
                self.set_selected([it])
            self._drag = {"kind": "move", "start": pos, "moved": False,
                          "origin": [(i, i.cx, i.cy) for i in self.selected]}
        else:
            if not additive:
                self.set_selected([])
            self._drag = {"kind": "pan", "last": pos}

    def mouseMoveEvent(self, e):
        pos = e.position()
        d = self._drag
        if d is None:
            if self._space:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            elif self._handle_hit(pos):
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif self.item_at(pos) is not None:
                self.setCursor(Qt.CursorShape.SizeAllCursor)
            else:
                self.unsetCursor()
            return
        if d["kind"] == "pan":
            delta = pos - d["last"]
            d["last"] = pos
            self.cx -= delta.x() / self.zoom
            self.cy -= delta.y() / self.zoom
            if delta.manhattanLength() > 0:
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            self.update()
        elif d["kind"] == "move":
            delta = pos - d["start"]
            if not d["moved"]:
                if delta.manhattanLength() < 4:
                    return
                d["moved"] = True
                self.state.bring_to_front([i for i, _, _ in d["origin"]])
            for i, x, y in d["origin"]:
                i.cx = x + delta.x() / self.zoom
                i.cy = y + delta.y() / self.zoom
            self.state.moved()
        elif d["kind"] == "resize":
            b = self.to_board(pos)
            f = max((b.x() - d["left"]) / d["ew"], (b.y() - d["top"]) / d["eh"])
            f = max(f, 24 / max(1.0, min(d["ew"], d["eh"])))
            it = d["item"]
            it.scale = d["scale"] * f
            it.move_to(d["left"], d["top"])
            self.state.moved()

    def mouseReleaseEvent(self, e):
        d, self._drag = self._drag, None
        if d is None:
            return
        if d["kind"] == "pan":
            self.unsetCursor()
            self._camera_settled()
        elif d["kind"] == "move":
            if d["moved"]:
                self.state.edited()
            elif not (e.modifiers() & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier)):
                hit = self.item_at(e.position())
                if hit is not None:
                    self.set_selected([hit])
        elif d["kind"] == "resize":
            self.state.edited()
        self._idle.start()

    def mouseDoubleClickEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        it = self.item_at(e.position())
        if it is not None:
            self.fit_item(it)
        else:
            self.fit_all()

    def wheelEvent(self, e):
        d = e.angleDelta().y() or e.angleDelta().x()
        if d:
            self._zoom_at(1.0018 ** d, e.position())
        e.accept()

    def event(self, e):
        if e.type() == QEvent.Type.Gesture:
            pinch = e.gesture(Qt.GestureType.PinchGesture)
            if pinch is not None:
                f = pinch.scaleFactor()
                if f > 0:
                    c = self.mapFromGlobal(pinch.centerPoint().toPoint())
                    b = self.to_board(QPointF(c))
                    self.zoom = self._clamp(self.zoom * f)
                    self.cx = b.x() - (c.x() - self.width() / 2) / self.zoom
                    self.cy = b.y() - (c.y() - self.height() / 2) / self.zoom
                    self.update()
                if pinch.state() == Qt.GestureState.GestureFinished:
                    self._camera_settled()
                return True
        return super().event(e)

    # ------------------------------------------------------------------ keyboard

    def keyPressEvent(self, e):
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
            self._space = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            return
        if e.key() == Qt.Key.Key_Escape and self.selected:
            self.set_selected([])
            return
        step = 40 / self.zoom
        moves = {Qt.Key.Key_Left: (-step, 0), Qt.Key.Key_Right: (step, 0), Qt.Key.Key_Up: (0, -step), Qt.Key.Key_Down: (0, step)}
        if e.key() in moves and not self.selected:
            dx, dy = moves[e.key()]
            self.animate_to(self.cx + dx * 3, self.cy + dy * 3, self.zoom)
            return
        if e.key() in moves and self.selected:
            dx, dy = moves[e.key()]
            f = 0.25 if e.modifiers() & Qt.KeyboardModifier.ShiftModifier else 0.05
            for it in self.selected:
                it.cx += dx * f
                it.cy += dy * f
            self.state.edited()
            return
        super().keyPressEvent(e)

    def keyReleaseEvent(self, e):
        if e.key() == Qt.Key.Key_Space and not e.isAutoRepeat():
            self._space = False
            self.unsetCursor()
            return
        super().keyReleaseEvent(e)

    def focusOutEvent(self, e):
        self._space = False
        super().focusOutEvent(e)

    def resizeEvent(self, e):
        free_h = max(1, self.height() - self.pad_top - self.pad_bottom)
        self.state.screen_aspect = max(0.5, min(3.0, self.width() / free_h))
        self._idle.start()

    def hideEvent(self, e):
        self._display.clear()
