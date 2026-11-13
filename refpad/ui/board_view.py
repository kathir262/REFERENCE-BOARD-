"""The reference board: an endless canvas of images you can move, resize, flip and rotate.

Smoothness tricks:
- Images small on screen are drawn from their 512 px preview; the large copy loads only when needed.
- When zooming stops, every visible image is pre-scaled (on a background thread) to its exact size on
  screen with flip, rotation and black & white applied. Panning then only copies ready-made pixels.
- The dotted background is one tiled fill, images off screen are skipped entirely.
"""
import dataclasses
import math

from PySide6.QtCore import QElapsedTimer, QEvent, QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter, QPainterPath, QPen, QPixmap, QTransform
from PySide6.QtWidgets import QPlainTextEdit, QWidget

from refpad.core import images
from refpad.core.store import NOTE_FONT, NOTE_PAD, size_note
from refpad.ui import theme

MIN_ZOOM, MAX_ZOOM = 0.02, 16.0
HANDLE_R = 7
MAX_BAKED_PIXELS = 3200 * 3200


def _bake(src: QImage, item, tw: int, th: int) -> QImage:
    return images.item_picture(item, src, (tw, th))


def item_transform(it) -> QTransform:
    """Image pixels -> board units (the crop's centre sits at the item's centre)."""
    if it.crop:
        x0, y0 = it.crop[0] + it.crop[2] / 2, it.crop[1] + it.crop[3] / 2
    else:
        x0, y0 = it.w / 2, it.h / 2
    t = QTransform()
    t.translate(it.cx, it.cy)
    if it.flip:
        t.scale(-1, 1)
    t.rotate(90 * it.rot)
    t.scale(it.scale, it.scale)
    t.translate(-x0, -y0)
    return t


def describe_color(c: QColor) -> str:
    luma = round((0.2126 * c.redF() + 0.7152 * c.greenF() + 0.0722 * c.blueF()) * 100)
    hue = c.hsvHue()
    return (f"{c.name().upper()}  ·  hue {max(0, hue)}°  ·  saturation {round(c.hsvSaturationF() * 100)}%  ·  "
            f"brightness {round(c.valueF() * 100)}%  ·  value {luma}%")


def paint_grid(p: QPainter, r: QRectF, n: int):
    """An n x n grid over a picture (light lines with a dark edge, visible on any picture)."""
    p.save()
    for pen, off in ((QPen(QColor(0, 0, 0, 90), 1), 1), (QPen(QColor(255, 255, 255, 150), 1), 0)):
        p.setPen(pen)
        for i in range(1, n):
            x = r.left() + r.width() * i / n + off
            y = r.top() + r.height() * i / n + off
            p.drawLine(QPointF(x, r.top()), QPointF(x, r.bottom()))
            p.drawLine(QPointF(r.left(), y), QPointF(r.right(), y))
    p.restore()


def paint_note(p: QPainter, it, r: QRectF, k: float, show_text: bool = True):
    """A note card; `k` = screen pixels per board unit at scale 1 (scale x zoom)."""
    p.save()
    p.setOpacity(it.opacity)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    rad = max(2.0, 8 * k)
    p.setBrush(QColor(0, 0, 0, 60))
    p.drawRoundedRect(r.translated(0, max(1.0, 3 * k)), rad, rad)
    p.setBrush(QColor("#2A2A31"))
    p.drawRoundedRect(r, rad, rad)
    p.setBrush(theme.color(theme.ACCENT))
    bar = QPainterPath()
    bar.addRoundedRect(r, rad, rad)
    clip = QPainterPath()
    clip.addRect(QRectF(r.left(), r.top(), max(2.0, 5 * k), r.height()))
    p.drawPath(bar.intersected(clip))
    px = NOTE_FONT * k
    if show_text and px >= 4:
        f = QFont("Segoe UI")
        f.setPixelSize(max(1, round(px)))
        p.setFont(f)
        p.setPen(theme.color(theme.TEXT))
        inner = r.adjusted(NOTE_PAD * k + 3 * k, NOTE_PAD * k * 0.8, -NOTE_PAD * k, -NOTE_PAD * k * 0.6)
        p.drawText(inner, Qt.TextFlag.TextWordWrap | Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, it.note)
    elif show_text:
        p.setBrush(QColor(255, 255, 255, 70))
        lh = max(1.0, r.height() / 6)
        for i in range(1, 4):
            p.drawRect(QRectF(r.left() + r.width() * 0.12, r.top() + lh * i * 1.3,
                              r.width() * (0.75 - 0.15 * (i == 3)), lh * 0.5))
    p.restore()


class BoardView(QWidget):
    contextRequested = Signal(object, object)   # item (or None), global QPointF
    selectionChanged = Signal()
    toolChanged = Signal()                       # crop or colour-picker mode switched on/off

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
        self._crop = None      # crop being edited: {"item", "crop", "cx", "cy"}
        self._picking = False  # colour picker on
        self._pick = None      # (screen point, QColor) under the cursor
        self._editor = None    # (QPlainTextEdit, note item, new?)
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

    def view_transform(self) -> QTransform:
        """Board units -> screen pixels."""
        t = QTransform()
        t.translate(self.width() / 2, self.height() / 2)
        t.scale(self.zoom, self.zoom)
        t.translate(-self.cx, -self.cy)
        return t

    def item_at(self, p: QPointF):
        for it in reversed(self.state.items):
            if self.screen_rect(it).contains(p):
                return it
        return None

    def _handle_hit(self, p: QPointF) -> bool:
        if len(self.selected) != 1 or self.selected[0].locked or self._crop:
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
        bg, dot = theme.board_colors()
        if not self._grid or self._grid[0] != t or self._grid[2] != bg.name():
            pm = QPixmap(t, t)
            pm.fill(bg)
            gp = QPainter(pm)
            gp.setRenderHint(QPainter.RenderHint.Antialiasing)
            gp.setPen(Qt.PenStyle.NoPen)
            gp.setBrush(dot)
            gp.drawEllipse(QPointF(t / 2, t / 2), 1.25, 1.25)
            gp.end()
            self._grid = (t, pm, bg.name())
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
        if self._crop:
            self._paint_crop(p)
        else:
            self._paint_selection(p)
        if self._picking and self._pick:
            self._paint_loupe(p)

    def _signature(self, it, r: QRectF):
        return (it.image, round(r.width()), round(r.height()), it.rot, it.flip, it.gray, it.crop, it.values, it.blur)

    def _draw_item(self, p: QPainter, it, r: QRectF) -> bool:
        """Draws one image; returns True when a sharper pre-scaled version is worth making."""
        if it.is_note:
            self._draw_note(p, it, r)
            return False
        if self._crop and self._crop["item"] is it:
            return False   # drawn by the crop editor
        op = it.opacity
        cached = self._display.get(it.id)
        if cached and cached[0] == self._signature(it, r):
            img = cached[1]
            if op >= 1 and not img.hasAlphaChannel():
                self._shadow(p, r)
            p.setOpacity(op)
            p.drawImage(QPointF(round(r.x()), round(r.y())), img)
            p.setOpacity(1.0)
            self._overlays(p, it, r)
            return False
        plain = not (it.gray or it.values or it.blur)
        src = None
        if max(r.width(), r.height()) > images.PREVIEW_SIDE * 1.1 and plain:
            src = images.cache.large(it.image)
        if src is None:
            src = images.cache.preview(it.image, not plain)
        if src is None:
            p.fillRect(r, theme.color(theme.RAISED))
            return False
        if op >= 1 and not src.hasAlphaChannel():
            self._shadow(p, r)
        p.save()
        p.setOpacity(op)
        p.translate(r.center())
        if it.flip:
            p.scale(-1, 1)
        p.rotate(90 * it.rot)
        w, h = (r.width(), r.height()) if it.rot % 2 == 0 else (r.height(), r.width())
        part = images.crop_rect(src, it)
        if part is not None:
            p.drawImage(QRectF(-w / 2, -h / 2, w, h), src, QRectF(part))
        else:
            p.drawImage(QRectF(-w / 2, -h / 2, w, h), src)
        p.restore()
        self._overlays(p, it, r)
        return True

    def _overlays(self, p: QPainter, it, r: QRectF):
        if it.grid and r.width() > 16:
            paint_grid(p, r, it.grid)

    def _draw_note(self, p: QPainter, it, r: QRectF):
        editing = self._editor is not None and self._editor[1] is it
        paint_note(p, it, r, it.scale * self.zoom, show_text=not editing)

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
            if it.locked:
                self._paint_lock(p, r.topLeft() + QPointF(8, 8))
        if len(self.selected) == 1 and not self.selected[0].locked:
            br = self.screen_rect(self.selected[0]).bottomRight()
            p.setPen(QPen(theme.color(theme.BG), 2))
            p.setBrush(theme.color(theme.ACCENT))
            p.drawEllipse(br, HANDLE_R, HANDLE_R)

    @staticmethod
    def _paint_lock(p: QPainter, at: QPointF):
        """A small padlock badge (the image can't be moved)."""
        p.save()
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(theme.color(theme.ACCENT))
        p.drawRoundedRect(QRectF(at.x(), at.y(), 22, 22), 6, 6)
        p.setBrush(theme.color(theme.ON_ACCENT))
        p.drawRoundedRect(QRectF(at.x() + 5, at.y() + 10, 12, 8), 1.5, 1.5)
        p.setPen(QPen(theme.color(theme.ON_ACCENT), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawArc(QRectF(at.x() + 7, at.y() + 4, 8, 10), 0, 180 * 16)
        p.restore()

    # ------------------------------------------------------------------ crop

    @property
    def cropping(self) -> bool:
        return self._crop is not None

    def start_crop(self, it=None) -> bool:
        it = it or (self.selected[0] if len(self.selected) == 1 else None)
        if it is None or it.is_note or it.locked:
            return False
        self.finish_note()
        self._crop = {"item": it, "crop": it.crop, "cx": it.cx, "cy": it.cy}
        self.set_selected([it])
        self.setFocus()
        self.toolChanged.emit()
        self.update()
        return True

    def finish_crop(self, cancel: bool = False):
        c, self._crop = self._crop, None
        if not c:
            return
        it = c["item"]
        if cancel:
            it.crop, it.cx, it.cy = c["crop"], c["cx"], c["cy"]
            self.state.moved()
        else:
            if it.crop and it.crop[0] < 1 and it.crop[1] < 1 and it.crop[2] > it.w - 1 and it.crop[3] > it.h - 1:
                self._set_crop(it, None)   # the whole picture: no crop
            if (it.crop, it.cx, it.cy) != (c["crop"], c["cx"], c["cy"]):
                self.state.edited()
        self.toolChanged.emit()
        self.update()
        self._idle.start()

    @staticmethod
    def _set_crop(it, crop):
        """Changes the crop without moving the picture on the board."""
        old = item_transform(it)
        it.crop = crop
        cx, cy = (crop[0] + crop[2] / 2, crop[1] + crop[3] / 2) if crop else (it.w / 2, it.h / 2)
        c = old.map(QPointF(cx, cy))
        it.cx, it.cy = c.x(), c.y()

    def reset_crop(self, items):
        for it in items:
            if it.crop:
                self._set_crop(it, None)
        self.state.edited()

    def _crop_points(self):
        it = self._crop["item"]
        x, y, w, h = it.crop or (0, 0, it.w, it.h)
        pts = {"l": (x, y + h / 2), "r": (x + w, y + h / 2), "t": (x + w / 2, y), "b": (x + w / 2, y + h),
               "lt": (x, y), "rt": (x + w, y), "lb": (x, y + h), "rb": (x + w, y + h)}
        t = item_transform(it) * self.view_transform()
        return {k: t.map(QPointF(*v)) for k, v in pts.items()}, t

    def _paint_crop(self, p: QPainter):
        it = self._crop["item"]
        t = item_transform(it) * self.view_transform()
        full = QRectF(0, 0, it.w, it.h)
        crop = QRectF(*(it.crop or (0, 0, it.w, it.h)))
        src = images.cache.large(it.image) or images.cache.preview(it.image)
        p.save()
        p.setTransform(t)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if src is not None:
            p.drawImage(full, src)
        else:
            p.fillRect(full, theme.color(theme.RAISED))
        outside = QPainterPath()
        outside.addRect(full)
        inside = QPainterPath()
        inside.addRect(crop)
        p.fillPath(outside.subtracted(inside), QColor(0, 0, 0, 150))
        p.restore()
        sr = t.mapRect(crop)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(QColor(255, 255, 255, 90), 1))
        for i in (1, 2):
            p.drawLine(QPointF(sr.left() + sr.width() * i / 3, sr.top()), QPointF(sr.left() + sr.width() * i / 3, sr.bottom()))
            p.drawLine(QPointF(sr.left(), sr.top() + sr.height() * i / 3), QPointF(sr.right(), sr.top() + sr.height() * i / 3))
        p.setPen(QPen(theme.color(theme.ACCENT), 2))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(sr)
        pts, _ = self._crop_points()
        p.setPen(QPen(theme.color(theme.BG), 1.5))
        p.setBrush(theme.color(theme.ACCENT))
        for k, pt in pts.items():
            s = 6 if len(k) == 1 else 7
            p.drawRect(QRectF(pt.x() - s, pt.y() - s, 2 * s, 2 * s))

    def _crop_press(self, pos: QPointF) -> bool:
        pts, t = self._crop_points()
        it = self._crop["item"]
        start = it.crop or (0, 0, it.w, it.h)
        inv, ok = t.inverted()
        for key, pt in sorted(pts.items(), key=lambda kv: -len(kv[0])):   # corners win
            if math.hypot(pt.x() - pos.x(), pt.y() - pos.y()) <= 12:
                self._drag = {"kind": "crop", "edges": key, "start": start, "from": inv.map(pos)}
                return True
        if t.mapRect(QRectF(*start)).contains(pos):
            self._drag = {"kind": "crop", "edges": "move", "start": start, "from": inv.map(pos)}
            return True
        self.finish_crop()
        return True

    def _crop_move(self, pos: QPointF):
        d = self._drag
        it = self._crop["item"]
        t = item_transform(it) * self.view_transform()
        inv, ok = t.inverted()
        ip = inv.map(pos)
        x, y, w, h = d["start"]
        x0, y0, x1, y1 = x, y, x + w, y + h
        least = max(8.0, 14 / max(1e-6, it.scale * self.zoom))
        e = d["edges"]
        if e == "move":
            dx = ip.x() - d["from"].x()
            dy = ip.y() - d["from"].y()
            x0 = max(0.0, min(it.w - w, x0 + dx))
            y0 = max(0.0, min(it.h - h, y0 + dy))
            x1, y1 = x0 + w, y0 + h
        else:
            if "l" in e:
                x0 = max(0.0, min(x1 - least, ip.x()))
            if "r" in e:
                x1 = min(float(it.w), max(x0 + least, ip.x()))
            if "t" in e:
                y0 = max(0.0, min(y1 - least, ip.y()))
            if "b" in e:
                y1 = min(float(it.h), max(y0 + least, ip.y()))
        self._set_crop(it, (x0, y0, x1 - x0, y1 - y0))
        self.state.moved()

    # ------------------------------------------------------------------ colour picker

    @property
    def picking(self) -> bool:
        return self._picking

    def set_picking(self, on: bool):
        if on == self._picking:
            return
        if on:
            self.finish_crop()
        self._picking = on
        self._pick = None
        if on:
            self.setCursor(Qt.CursorShape.CrossCursor)
        else:
            self.unsetCursor()
        self.toolChanged.emit()
        self.update()

    def _sample(self, pos: QPointF):
        it = self.item_at(pos)
        if it is None or it.is_note:
            return None
        inv, ok = (item_transform(it) * self.view_transform()).inverted()
        ip = inv.map(pos)
        src = images.cache.large(it.image) or images.cache.preview(it.image)
        if src is None:
            return None
        k = src.width() / max(1, it.w)
        x, y = int(ip.x() * k), int(ip.y() * k)
        if not (0 <= x < src.width() and 0 <= y < src.height()):
            return None
        c = QColor(src.pixel(x, y))
        if it.values or it.gray:
            g = round(0.2126 * c.red() + 0.7152 * c.green() + 0.0722 * c.blue())
            if it.values:
                n = it.values
                g = round(round(g / 255 * (n - 1)) * 255 / (n - 1))
            c = QColor(g, g, g)
        return c

    def _paint_loupe(self, p: QPainter):
        pos, c = self._pick
        if c is None:
            return
        luma = round((0.2126 * c.redF() + 0.7152 * c.greenF() + 0.0722 * c.blueF()) * 100)
        lines = [c.name().upper(), f"Hue {max(0, c.hsvHue())}°  Sat {round(c.hsvSaturationF() * 100)}%",
                 f"Bright {round(c.valueF() * 100)}%  Value {luma}%"]
        w, h = 214, 74
        x = pos.x() + 20 if pos.x() + 20 + w < self.width() else pos.x() - 20 - w
        y = pos.y() + 20 if pos.y() + 20 + h < self.height() else pos.y() - 20 - h
        box = QRectF(x, y, w, h)
        p.save()
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(QPen(theme.color(theme.STROKE_STRONG), 1))
        p.setBrush(theme.color(theme.RAISED))
        p.drawRoundedRect(box, 12, 12)
        p.setPen(QPen(QColor(255, 255, 255, 120), 1))
        p.setBrush(c)
        p.drawRoundedRect(QRectF(x + 10, y + 10, 54, 54), 8, 8)
        f = QFont(p.font())
        f.setPixelSize(13)
        f.setBold(True)
        p.setFont(f)
        p.setPen(theme.color(theme.TEXT))
        p.drawText(QPointF(x + 76, y + 27), lines[0])
        f.setBold(False)
        f.setPixelSize(12)
        p.setFont(f)
        p.setPen(theme.color(theme.TEXT_2))
        p.drawText(QPointF(x + 76, y + 46), lines[1])
        p.drawText(QPointF(x + 76, y + 63), lines[2])
        p.restore()

    # ------------------------------------------------------------------ notes

    def edit_note(self, it, new: bool = False):
        self.finish_note()
        ed = QPlainTextEdit(self)
        ed.setPlainText(it.note)
        ed.setFrameStyle(0)
        px = max(13, min(40, round(NOTE_FONT * it.scale * self.zoom)))
        f = QFont("Segoe UI")
        f.setPixelSize(px)
        ed.setFont(f)
        ed.setStyleSheet(f"QPlainTextEdit {{ background: #2A2A31; color: {theme.TEXT}; border: 2px solid {theme.ACCENT};"
                         f" border-radius: 8px; padding: 6px; }}")
        r = self.screen_rect(it)
        w = max(240, round(r.width()))
        h = max(90, round(r.height()) + px * 2)
        x = max(8, min(self.width() - w - 8, round(r.x())))
        y = max(8, min(self.height() - h - 8, round(r.y())))
        ed.setGeometry(QRect(x, y, w, h))
        ed.setPlaceholderText("Type a note…  (Ctrl+Enter to finish)")
        ed.installEventFilter(self)
        self._editor = (ed, it, new)
        ed.show()
        ed.setFocus()
        if new:
            ed.selectAll()
        self.update()

    def finish_note(self):
        if not self._editor:
            return
        ed, it, new = self._editor
        self._editor = None
        text = ed.toPlainText().strip()
        ed.hide()
        ed.deleteLater()
        if it not in self.state.items:
            return
        if not text:
            self.state.items.remove(it)
            self.state.edited()
        elif text != it.note:
            it.note = text
            size_note(it)
            self.state.edited()
        self.setFocus()
        self.update()

    def eventFilter(self, obj, e):
        if self._editor and obj is self._editor[0]:
            if e.type() == QEvent.Type.FocusOut:
                QTimer.singleShot(0, self.finish_note)
            elif e.type() == QEvent.Type.KeyPress and (
                    e.key() == Qt.Key.Key_Escape or
                    (e.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and e.modifiers() & Qt.KeyboardModifier.ControlModifier)):
                self.finish_note()
                return True
        return super().eventFilter(obj, e)

    # ------------------------------------------------------------------ pre-scaled images

    def _bake_visible(self):
        if self._drag is not None or self._target is not None:
            self._idle.start()
            return
        view = QRectF(self.rect())
        keep = set()
        for it in self.state.items:
            r = self.screen_rect(it)
            if it.is_note or not r.intersects(view):
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
            images.run_async(lambda s=src, i=dataclasses.replace(it), a=(tw, th): _bake(s, i, *a),
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
        # Undo/redo puts back copies of the items: keep the same ones selected.
        ids = [it.id for it in self.selected]
        by_id = {it.id: it for it in self.state.items}
        sel = [by_id[i] for i in ids if i in by_id]
        if sel != self.selected:
            self.selected = sel
            self.selectionChanged.emit()
        if self._crop and self._crop["item"] not in self.state.items:
            self._crop = None
            self.toolChanged.emit()
        self.update()
        self._idle.start()

    def _on_replaced(self):
        """Another board was opened (or a new one started): its own camera, nothing selected."""
        self._added = []
        self._reveal.stop()
        self._display.clear()
        self._stop_anim()
        self._crop = None
        self.finish_note()
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
        if self._picking:
            if e.button() == Qt.MouseButton.LeftButton:
                c = self._sample(pos)
                if c is not None:
                    QGuiApplication.clipboard().setText(c.name().upper())
                    self.state.notify("Copied " + describe_color(c))
            else:
                self.set_picking(False)
            return
        if self._crop and e.button() == Qt.MouseButton.LeftButton:
            self._crop_press(pos)
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
        if it is not None and it.locked and not additive:
            # A locked image can be selected, but dragging it moves the board instead.
            self.set_selected([it])
            self._drag = {"kind": "pan", "last": pos}
            return
        if it is not None:
            if additive:
                if it in self.selected:
                    self.set_selected([i for i in self.selected if i is not it])
                    return
                self.set_selected(self.selected + [it])
            elif it not in self.selected:
                self.set_selected([it])
            self._drag = {"kind": "move", "start": pos, "moved": False,
                          "origin": [(i, i.cx, i.cy) for i in self.selected if not i.locked]}
        else:
            if not additive:
                self.set_selected([])
            self._drag = {"kind": "pan", "last": pos}

    def mouseMoveEvent(self, e):
        pos = e.position()
        d = self._drag
        if self._picking and d is None:
            self._pick = (pos, self._sample(pos))
            self.update()
            return
        if d is not None and d["kind"] == "crop":
            self._crop_move(pos)
            return
        if d is None:
            if self._crop:
                pts, t = self._crop_points()
                near = any(math.hypot(pt.x() - pos.x(), pt.y() - pos.y()) <= 12 for pt in pts.values())
                inside = t.mapRect(QRectF(*(self._crop["item"].crop or (0, 0, self._crop["item"].w, self._crop["item"].h)))).contains(pos)
                self.setCursor(Qt.CursorShape.SizeAllCursor if near else
                               Qt.CursorShape.OpenHandCursor if inside else Qt.CursorShape.ArrowCursor)
                return
            if self._space:
                self.setCursor(Qt.CursorShape.OpenHandCursor)
            elif self._handle_hit(pos):
                self.setCursor(Qt.CursorShape.SizeFDiagCursor)
            elif self.item_at(pos) is not None and not self.item_at(pos).locked:
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
        self.update()

    def mouseDoubleClickEvent(self, e):
        if e.button() != Qt.MouseButton.LeftButton:
            return
        if self._crop:
            self.finish_crop()
            return
        it = self.item_at(e.position())
        if it is not None and it.is_note:
            self.edit_note(it)
        elif it is not None:
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
        if self._crop and e.key() in (Qt.Key.Key_Escape, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.finish_crop(cancel=e.key() == Qt.Key.Key_Escape)
            return
        if self._picking and e.key() == Qt.Key.Key_Escape:
            self.set_picking(False)
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
            for it in [i for i in self.selected if not i.locked]:
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
        self.finish_note()
        self.set_picking(False)

    def showEvent(self, e):
        super().showEvent(e)
        # A board without a saved view (e.g. a fresh install or an imported file): show all of it.
        if not getattr(self, "_shown_once", False):
            self._shown_once = True
            if self.state.view is None and self.state.items:
                QTimer.singleShot(0, lambda: self.fit_all(animate=False))
