"""Practice: one pose at a time, fitted to the window, with a slide between poses.

Wheel to zoom into a pose, drag to look around, double-click to reset. When not zoomed, drag
sideways (or use the arrow keys) to change pose. The next pose is loaded ahead of time.
"""
import math

from PySide6.QtCore import QEasingCurve, QPointF, QRectF, Qt, QTimer, QVariantAnimation, Signal
from PySide6.QtGui import QImage, QPainter, QTransform
from PySide6.QtWidgets import QWidget

from refpad.core import images, pdf
from refpad.ui import theme

SLIDE_MS = 260
MARGIN = 20


def _bake(src: QImage, w: int, h: int, flip: bool, gray: bool) -> QImage:
    img = src.scaled(w, h, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation)
    if gray:
        img = images.grayscale(img)
    if flip:
        img = img.transformed(QTransform().scale(-1, 1))
    return images.normalize(img)


class PracticeView(QWidget):
    contextRequested = Signal(object)    # global QPointF

    def __init__(self, state, timer, engine, parent=None):
        super().__init__(parent)
        self.state = state
        self.timer = timer
        self.engine = engine
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.pad_top = 0
        self.pad_bottom = 0
        self._pose = state.pose
        self._old = None              # pose sliding out
        self._dir = 1
        self._t = 1.0                 # slide progress
        self._zoom = 1.0
        self._pan = QPointF()
        self._drag = None
        self._swipe = 0.0
        self._display = None          # (signature, pre-scaled image)
        self._baking = None
        self._want = ()
        self._anim = QVariantAnimation(self, startValue=0.0, endValue=1.0, duration=SLIDE_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_slide)
        self._anim.finished.connect(self._slide_done)
        self._idle = QTimer(self, singleShot=True, interval=90, timeout=self._bake_current)
        state.poseChanged.connect(self._on_pose_changed)
        state.practiceChanged.connect(self.update)
        images.cache.changed.connect(self._on_source_changed)
        engine.pageReady.connect(self._on_page)
        engine.infoReady.connect(lambda _k: self._on_source_changed())
        timer.tick.connect(self._update_progress)
        timer.phaseChanged.connect(self.update)
        self._peek = False

    # ------------------------------------------------------------------ layout

    def _box(self) -> QRectF:
        return QRectF(MARGIN, self.pad_top + MARGIN, self.width() - 2 * MARGIN,
                      self.height() - self.pad_top - self.pad_bottom - 2 * MARGIN)

    def _aspect(self, pose):
        """Height/width of a pose (None while unknown)."""
        if pose is None:
            return None
        if pose.kind == "pdf":
            info = self.engine.info(pose.ref)
            return info.aspect(pose.page) if info and not info.error else None
        src = self._source(pose, 0)
        return src.height() / max(1, src.width()) if src is not None else None

    def _fit(self, pose):
        a = self._aspect(pose)
        if a is None:
            return None
        box = self._box()
        w = min(box.width(), box.height() / a)
        h = w * a
        return QRectF(box.center().x() - w / 2, box.center().y() - h / 2, w, h)

    def _source(self, pose, width_px: int):
        """Best picture available for a pose (requests better ones)."""
        if pose.kind == "img":
            return images.cache.large(pose.ref) or images.cache.preview(pose.ref)
        if pose.kind == "file":
            return images.cache.file(pose.ref)
        info = self.engine.info(pose.ref)
        if info is None or info.error:
            return None
        key = self._page_key(pose, width_px)
        return self.engine.page(key) or self.engine.best_page(key.path, key.page, key.width)

    def _page_key(self, pose, width_px: int):
        bucket = min(pdf.MAX_PAGE_WIDTH, max(256, math.ceil(max(1, width_px) / 128) * 128))
        return pdf.Key(pdf.norm(pose.ref), pose.page, bucket, None)

    def _missing_text(self, pose):
        if pose.kind == "file" and images.cache.failed("file", pose.ref):
            return "Can't open this picture. It may have been moved or deleted."
        if pose.kind == "img" and images.cache.failed("img", pose.ref):
            return "Can't open this picture."
        if pose.kind == "pdf":
            info = self.engine.info(pose.ref)
            if info is not None and info.error:
                return info.error
        return None

    # ------------------------------------------------------------------ painting

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), theme.board_colors()[0])
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if not self.state.practice:
            return
        dpr = self.devicePixelRatioF()
        w = self.width()
        if self._t < 1.0 and self._old is not None:
            off = self._t * w   # the old pose slides out one way while the new one comes in
            self._draw_pose(p, self._old, dpr, current=False, x_shift=-self._dir * off)
            self._draw_pose(p, self._pose, dpr, current=True, x_shift=self._dir * (w - off))
        else:
            self._draw_pose(p, self._pose, dpr, current=True, x_shift=self._swipe)
        if self.timer.hidden and not self._peek:
            self._paint_cover(p)
        self._paint_progress(p)
        self._request_pages(dpr)

    def _draw_pose(self, p, pose, dpr, current, x_shift):
        if pose is None:
            return
        r = self._fit(pose)
        if r is None:
            msg = self._missing_text(pose)
            p.setPen(theme.color(theme.TEXT_2 if msg else theme.MUTED))
            p.drawText(self._box().translated(x_shift, 0), Qt.AlignmentFlag.AlignCenter | Qt.TextFlag.TextWordWrap,
                       msg or "Loading…")
            return
        if current and self._zoom != 1.0:
            c = r.center()
            r = QRectF(c.x() - r.width() * self._zoom / 2 + self._pan.x(), c.y() - r.height() * self._zoom / 2 + self._pan.y(),
                       r.width() * self._zoom, r.height() * self._zoom)
        r.translate(x_shift, 0)
        flip, gray = self.state.practice_flip, self.state.practice_gray
        sig = (pose.key, round(r.width()), round(r.height()), flip, gray)
        if current and self._display and self._display[0] == sig:
            p.drawImage(QPointF(round(r.x()), round(r.y())), self._display[1])
            return
        src = self._source(pose, round(r.width() * dpr))
        if src is None:
            p.fillRect(r, theme.color(theme.RAISED))
            return
        if gray:
            src = images.grayscale(src) if max(src.width(), src.height()) <= 1200 else src
        p.save()
        if flip:
            p.translate(r.center().x() * 2, 0)
            p.scale(-1, 1)
        p.drawImage(r, src)
        p.restore()
        if current and self._t >= 1.0 and not self._idle.isActive():
            self._idle.start()

    def _paint_cover(self, p):
        """Memory mode: the pose is hidden while you draw it from memory."""
        box = self._box()
        p.fillRect(QRectF(0, self.pad_top, self.width(), self.height() - self.pad_top), theme.board_colors()[0])
        f = p.font()
        f.setPixelSize(26)
        f.setBold(True)
        p.setFont(f)
        p.setPen(theme.color(theme.TEXT))
        p.drawText(box.adjusted(0, 0, 0, -40), Qt.AlignmentFlag.AlignCenter, "Draw it from memory")
        f.setPixelSize(14)
        f.setBold(False)
        p.setFont(f)
        p.setPen(theme.color(theme.TEXT_2))
        p.drawText(box.adjusted(0, 60, 0, 0), Qt.AlignmentFlag.AlignCenter,
                   "Hold the mouse button to peek · the next pose comes when the time is up")

    def _paint_progress(self, p):
        y = self.pad_top
        w = self.width()
        p.fillRect(QRectF(0, y, w, 3), theme.color(theme.STROKE))
        p.fillRect(QRectF(0, y, w * min(1.0, max(0.0, self.timer.progress)), 3),
                   theme.color(theme.ACCENT if self.timer.running else theme.MUTED))

    def _update_progress(self):
        self.update(0, self.pad_top, self.width(), 3)

    # ------------------------------------------------------------------ loading ahead

    def _request_pages(self, dpr):
        """PDF pages for the current pose first, then the next one, then the previous one."""
        keys = []
        n = len(self.state.practice)
        for off in (0, 1, -1):
            pose = self.state.practice[(self.state.practice_index + off) % n] if n else None
            if pose is None:
                continue
            if pose.kind == "pdf":
                r = self._fit(pose)
                if r is not None:
                    keys.append(self._page_key(pose, round(r.width() * dpr * (self._zoom if off == 0 else 1))))
            elif off == 1:
                self._source(pose, 0)   # starts loading the next picture
        keys = tuple(dict.fromkeys(keys))
        if keys != self._want:
            self._want = keys
            self.engine.want(self, keys)

    def _bake_current(self):
        pose = self._pose
        if pose is None or self._drag or self._t < 1.0:
            return
        r = self._fit(pose)
        if r is None:
            return
        if self._zoom != 1.0:
            r = QRectF(0, 0, r.width() * self._zoom, r.height() * self._zoom)
        w, h = round(r.width()), round(r.height())
        if w < 4 or h < 4 or w * h > 3600 * 3600:
            return
        src = self._source(pose, round(w * self.devicePixelRatioF()))
        if src is None:
            return
        flip, gray = self.state.practice_flip, self.state.practice_gray
        sig = (pose.key, w, h, flip, gray)
        if (self._display and self._display[0] == sig) or self._baking == (sig, src.cacheKey()):
            return
        self._baking = (sig, src.cacheKey())
        images.run_async(lambda: _bake(src, w, h, flip, gray), lambda img: self._baked(sig, img))

    def _baked(self, sig, img):
        self._baking = None
        if isinstance(img, QImage):
            self._display = (sig, img)
            self.update()

    def _on_source_changed(self):
        if self.isVisible():
            self.update()
            self._idle.start()

    def _on_page(self, key):
        if key in self._want and self.isVisible():
            self.update()
            self._idle.start()

    # ------------------------------------------------------------------ pose changes

    def _on_pose_changed(self):
        new = self.state.pose
        if new is self._pose:
            return
        old_i = self.state.practice.index(self._pose) if self._pose in self.state.practice else -1
        new_i = self.state.practice_index
        n = len(self.state.practice)
        forward = old_i < 0 or (new_i - old_i) % max(1, n) <= n // 2
        self._old, self._pose = self._pose, new
        self._dir = 1 if forward else -1
        self._zoom, self._pan, self._display = 1.0, QPointF(), None
        if self._old is not None and new is not None and self.isVisible():
            self._anim.stop()
            self._anim.setStartValue(min(1.0, max(0.0, abs(self._swipe) / max(1, self.width()))))
            self._t = self._anim.startValue()
            self._anim.start()
        else:
            self._t = 1.0
            self._old = None
        self._swipe = 0.0
        self.update()

    def _on_slide(self, v):
        self._t = float(v)
        self.update()

    def _slide_done(self):
        self._t = 1.0
        self._old = None
        self.update()
        self._idle.start()

    def refresh(self):
        """Flip / black & white changed."""
        self.update()
        self._idle.start()

    def reset_zoom(self):
        self._zoom, self._pan = 1.0, QPointF()
        self.update()
        self._idle.start()

    # ------------------------------------------------------------------ mouse

    def wheelEvent(self, e):
        d = e.angleDelta().y()
        if not d or self._pose is None:
            return
        old = self._zoom
        self._zoom = max(1.0, min(8.0, self._zoom * 1.0018 ** d))
        if self._zoom == 1.0:
            self._pan = QPointF()
        else:
            box_c = self._box().center()
            m = e.position() - box_c - self._pan
            self._pan -= m * (self._zoom / old - 1)
        self.update()
        self._idle.start()

    def mousePressEvent(self, e):
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if e.button() == Qt.MouseButton.RightButton:
            self.contextRequested.emit(e.globalPosition())
            return
        if e.button() in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            if self.timer.hidden:
                self._peek = True    # memory mode: peek while the button is held
                self.update()
                return
            self._drag = {"start": e.position(), "last": e.position()}

    def mouseMoveEvent(self, e):
        d = self._drag
        if d is None:
            return
        delta = e.position() - d["last"]
        d["last"] = e.position()
        if self._zoom > 1.0:
            self._pan += delta
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        elif len(self.state.practice) > 1:
            self._swipe += delta.x()
        self.update()

    def mouseReleaseEvent(self, e):
        if self._peek:
            self._peek = False
            self.update()
            return
        d, self._drag = self._drag, None
        self.unsetCursor()
        if d is None:
            return
        if self._zoom <= 1.0 and abs(self._swipe) > min(120, self.width() * 0.12):
            self.state.prev_pose() if self._swipe > 0 else self.timer.advance()
            return
        if self._swipe:
            self._swipe = 0.0
            self.update()
        self._idle.start()

    def mouseDoubleClickEvent(self, e):
        if self._zoom != 1.0:
            self.reset_zoom()
        else:
            box_c = self._box().center()
            self._zoom = 2.5
            self._pan = -(e.position() - box_c) * (self._zoom - 1)
            self.update()
            self._idle.start()

    def resizeEvent(self, e):
        self._display = None
        self._idle.start()

    def hideEvent(self, e):
        self.engine.release(self)
        self._want = ()
