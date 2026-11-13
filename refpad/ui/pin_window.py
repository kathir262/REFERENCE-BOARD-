"""One picture pinned on top of every other app (for example next to the canvas while you paint).

Drag it to move, scroll to make it bigger or smaller, drag the corner to resize, right-click for
see-through, flip and close. Pinned pictures close when RefPad closes.
"""
from PySide6.QtCore import QPoint, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QIcon, QImage, QPainter, QPen, QTransform
from PySide6.QtWidgets import QSizeGrip, QWidget

from refpad import paths
from refpad.ui import theme
from refpad.ui.widgets import item, menu


class PinWindow(QWidget):
    def __init__(self, img: QImage, title: str = "Pinned picture"):
        super().__init__(None, Qt.WindowType.Window | Qt.WindowType.FramelessWindowHint |
                         Qt.WindowType.WindowStaysOnTopHint | Qt.WindowType.Tool)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(title)
        self.setWindowIcon(QIcon(str(paths.resource("refpad/assets/refpad.ico"))))
        self.img = img
        self._hover = False
        long_side = 360
        k = long_side / max(img.width(), img.height(), 1)
        self.resize(max(120, round(img.width() * k)), max(120, round(img.height() * k)))
        self.setMinimumSize(80, 80)
        self.setMouseTracking(True)
        grip = QSizeGrip(self)
        grip.setFixedSize(16, 16)
        self._grip = grip

    def resizeEvent(self, e):
        self._grip.move(self.width() - 16, self.height() - 16)

    def _image_rect(self) -> QRectF:
        w, h = self.width(), self.height()
        k = min(w / max(1, self.img.width()), h / max(1, self.img.height()))
        iw, ih = self.img.width() * k, self.img.height() * k
        return QRectF((w - iw) / 2, (h - ih) / 2, iw, ih)

    def paintEvent(self, e):
        p = QPainter(self)
        p.fillRect(self.rect(), theme.color(theme.BG))
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        p.drawImage(self._image_rect(), self.img)
        p.setPen(QPen(theme.color(theme.STROKE_STRONG), 1))
        p.drawRect(self.rect().adjusted(0, 0, -1, -1))
        if self._hover:   # a close button while the mouse is over the picture
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, 160))
            p.drawEllipse(self._close_rect())
            p.drawPixmap(self._close_rect().adjusted(5, 5, -5, -5).toRect(), theme.pixmap("close", theme.TEXT, 16))

    def _close_rect(self) -> QRectF:
        return QRectF(self.width() - 32, 6, 26, 26)

    def enterEvent(self, e):
        self._hover = True
        self.update()

    def leaveEvent(self, e):
        self._hover = False
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if self._close_rect().contains(e.position()):
                self.close()
            elif self.windowHandle():
                self.windowHandle().startSystemMove()
        elif e.button() == Qt.MouseButton.RightButton:
            self._menu(e.globalPosition().toPoint())

    def wheelEvent(self, e):
        f = 1.1 if e.angleDelta().y() > 0 else 1 / 1.1
        c = self.geometry().center()
        size = QSize(max(80, round(self.width() * f)), max(80, round(self.height() * f)))
        self.resize(size)
        self.move(c - QPoint(size.width() // 2, size.height() // 2))

    def _menu(self, at: QPoint):
        m = menu(self)
        for pct in (100, 80, 60, 40):
            a = item(m, f"{pct}% visible", "opacity", lambda p=pct: self.setWindowOpacity(p / 100))
            a.setCheckable(True)
            a.setChecked(abs(self.windowOpacity() - pct / 100) < 0.02)
        m.addSeparator()
        item(m, "Flip horizontally", "flip", self._flip)
        item(m, "Close", "close", self.close)
        m.exec(at)

    def _flip(self):
        self.img = self.img.transformed(QTransform().scale(-1, 1))
        self.update()
