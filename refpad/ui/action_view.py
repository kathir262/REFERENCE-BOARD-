"""
Action View (Line of Action timed practice).
Empty-state and background fully theme-aware. Zero hardcoded purple.
"""
import math
from typing import Optional
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import (
    QPainter, QPixmap, QColor, QWheelEvent, QMouseEvent,
    QTouchEvent, QTabletEvent, QPen, QBrush, QFont, QPointingDevice
)
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QEvent

from refpad.models.item import RefItem
from refpad.ui.timer_hud import TimerHUD
from refpad.ui.themes import get_current_theme


class ActionView(QWidget):
    open_folder_requested = Signal()
    open_pdf_requested = Signal()
    files_dropped = Signal(list)
    user_activity_detected = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMouseTracking(True)
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)

        self.current_item: Optional[RefItem] = None
        self.cached_pixmap: Optional[QPixmap] = None

        self.zoom_factor: float = 1.0
        self.pan_offset = QPointF(0, 0)
        self.is_panning: bool = False
        self.last_mouse_pos = QPointF(0, 0)

        self.touch_initial_distance: float = 0.0
        self.touch_initial_zoom: float = 1.0
        self.touch_last_center = QPointF(0, 0)

        self.timer_hud = TimerHUD(self)
        self.timer_hud.move(16, 16)

    def set_item(self, item: Optional[RefItem]):
        self.current_item = item
        self.cached_pixmap = None
        self.zoom_factor = 1.0
        self.pan_offset = QPointF(0, 0)
        if item:
            self.cached_pixmap = item.get_transformed_pixmap()
        self.update()

    def refresh_transforms(self):
        if self.current_item:
            self.cached_pixmap = self.current_item.get_transformed_pixmap()
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        theme = get_current_theme()
        painter.fillRect(self.rect(), QColor(theme.bg_dark))

        if not self.cached_pixmap or self.cached_pixmap.isNull():
            self._draw_empty_state(painter, theme)
            return

        win_w, win_h = self.width(), self.height()
        pix_w = self.cached_pixmap.width()
        pix_h = self.cached_pixmap.height()

        base_scale = min(win_w / pix_w, win_h / pix_h)
        draw_w = pix_w * base_scale * self.zoom_factor
        draw_h = pix_h * base_scale * self.zoom_factor

        center_x = (win_w - draw_w) / 2.0 + self.pan_offset.x()
        center_y = (win_h - draw_h) / 2.0 + self.pan_offset.y()

        painter.drawPixmap(QRectF(center_x, center_y, draw_w, draw_h).toRect(), self.cached_pixmap)

    def _draw_empty_state(self, painter: QPainter, theme):
        cx = self.width() / 2.0
        cy = self.height() / 2.0

        card_rect = QRectF(cx - 185, cy - 80, 370, 160)
        painter.setBrush(QBrush(QColor(theme.bg_card)))
        painter.setPen(QPen(QColor(theme.border), 1))
        painter.drawRoundedRect(card_rect, 12, 12)

        painter.setPen(QColor(theme.text_primary))
        painter.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        painter.drawText(QRectF(cx - 165, cy - 65, 330, 30), Qt.AlignmentFlag.AlignCenter, "Line of Action Mode")

        painter.setPen(QColor(theme.text_muted))
        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(QRectF(cx - 165, cy - 30, 330, 40), Qt.AlignmentFlag.AlignCenter,
                         "Drop a folder of poses or an anatomy PDF\nto start your timed practice session.")

        painter.setPen(QColor(theme.text_muted))
        painter.setFont(QFont("Segoe UI", 9))
        painter.drawText(QRectF(cx - 165, cy + 22, 330, 22), Qt.AlignmentFlag.AlignCenter,
                         "Space: Play/Pause   Tab: Switch to Board")

    # --- Touch ---
    def event(self, event: QEvent) -> bool:
        if event.type() in (QEvent.Type.TouchBegin, QEvent.Type.TouchUpdate, QEvent.Type.TouchEnd):
            touch_event: QTouchEvent = event
            points = touch_event.points()
            self.user_activity_detected.emit()
            valid_points = [p for p in points if max(p.ellipseDiameters().width(), p.ellipseDiameters().height()) < 42]

            if len(valid_points) == 2:
                p1 = valid_points[0].position()
                p2 = valid_points[1].position()
                dist = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
                center = (p1 + p2) / 2.0

                if touch_event.type() == QEvent.Type.TouchBegin:
                    self.touch_initial_distance = dist
                    self.touch_initial_zoom = self.zoom_factor
                    self.touch_last_center = center
                elif touch_event.type() == QEvent.Type.TouchUpdate:
                    if self.touch_initial_distance > 10:
                        self.zoom_factor = max(0.4, min(6.0, self.touch_initial_zoom * (dist / self.touch_initial_distance)))
                    self.pan_offset += center - self.touch_last_center
                    self.touch_last_center = center
                    self.update()

                event.accept()
                return True

        return super().event(event)

    def tabletEvent(self, event: QTabletEvent):
        self.user_activity_detected.emit()
        if event.buttons() & Qt.MouseButton.RightButton:
            if event.type() == QEvent.Type.TabletMove:
                self.pan_offset += event.position() - self.last_mouse_pos
                self.update()
            self.last_mouse_pos = event.position()
            event.accept()
            return
        if event.pointingDevice().pointerType() == QPointingDevice.PointerType.Eraser and event.type() == QEvent.Type.TabletPress:
            self.zoom_factor = 1.0
            self.pan_offset = QPointF(0, 0)
            self.update()
            event.accept()
            return
        self.last_mouse_pos = event.position()
        super().tabletEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        self.user_activity_detected.emit()
        factor = 1.15 if event.angleDelta().y() > 0 else 0.85
        self.zoom_factor = max(0.5, min(6.0, self.zoom_factor * factor))
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        self.user_activity_detected.emit()
        if event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton):
            self.is_panning = True
            self.last_mouse_pos = event.position()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        self.user_activity_detected.emit()
        if self.is_panning:
            self.pan_offset += event.position() - self.last_mouse_pos
            self.last_mouse_pos = event.position()
            self.update()
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.RightButton):
            self.is_panning = False
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        self.zoom_factor = 1.0
        self.pan_offset = QPointF(0, 0)
        self.update()
        super().mouseDoubleClickEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
