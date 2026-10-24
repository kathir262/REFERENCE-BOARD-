"""
Line of Action Practice View (Edge-to-Edge).
Provides 100% unobstructed full-bleed reference display with smooth pan/zoom,
integrated draggable Timer HUD, and multi-touch / stylus handling.
"""
from typing import Optional
from pathlib import Path
import math
from PySide6.QtWidgets import QWidget
from PySide6.QtGui import (
    QPainter, QPixmap, QColor, QWheelEvent, QMouseEvent,
    QTouchEvent, QTabletEvent, QPen, QBrush, QFont, QPointingDevice
)
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QEvent

from refpad.models.item import RefItem
from refpad.ui.timer_hud import TimerHUD

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

        # Pan and Zoom state for single image
        self.zoom_factor: float = 1.0
        self.pan_offset = QPointF(0, 0)
        self.is_panning: bool = False
        self.last_mouse_pos = QPointF(0, 0)

        # Multi-touch & Stylus tracking
        self.touch_initial_distance: float = 0.0
        self.touch_initial_zoom: float = 1.0
        self.touch_last_center = QPointF(0, 0)

        # Floating Draggable Timer HUD
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

        # Deep graphite background
        painter.fillRect(self.rect(), QColor(13, 14, 18))

        if not self.cached_pixmap or self.cached_pixmap.isNull():
            self._draw_empty_state(painter)
            return

        # Full-bleed aspect fit
        win_w, win_h = self.width(), self.height()
        pix_w = self.cached_pixmap.width()
        pix_h = self.cached_pixmap.height()

        scale_w = win_w / pix_w
        scale_h = win_h / pix_h
        base_scale = min(scale_w, scale_h)

        draw_w = pix_w * base_scale * self.zoom_factor
        draw_h = pix_h * base_scale * self.zoom_factor

        center_x = (win_w - draw_w) / 2.0 + self.pan_offset.x()
        center_y = (win_h - draw_h) / 2.0 + self.pan_offset.y()

        target_rect = QRectF(center_x, center_y, draw_w, draw_h)
        painter.drawPixmap(target_rect.toRect(), self.cached_pixmap)

    def _draw_empty_state(self, painter: QPainter):
        """Boutique empty state inviting the artist to load references."""
        cx = self.width() / 2.0
        cy = self.height() / 2.0

        card_rect = QRectF(cx - 180, cy - 90, 360, 180)
        painter.setBrush(QBrush(QColor(18, 20, 26, 210)))
        painter.setPen(QPen(QColor(255, 255, 255, 20), 1))
        painter.drawRoundedRect(card_rect, 14, 14)

        painter.setPen(QColor(240, 243, 250))
        painter.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
        painter.drawText(QRectF(cx - 160, cy - 70, 320, 30), Qt.AlignmentFlag.AlignCenter, "Line of Action Mode")

        painter.setPen(QColor(140, 150, 165))
        painter.setFont(QFont("Segoe UI", 10))
        painter.drawText(QRectF(cx - 160, cy - 35, 320, 45), Qt.AlignmentFlag.AlignCenter,
                         "Drop a folder of poses or an anatomy PDF\nto start your timed practice session.")

        painter.setPen(QColor(126, 87, 246))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
        painter.drawText(QRectF(cx - 160, cy + 25, 320, 25), Qt.AlignmentFlag.AlignCenter,
                         "Space: Play/Pause  •  Tab: BeeRef Board")

    def event(self, event: QEvent) -> bool:
        """Handle Touch Events with 2-finger pinch/pan and palm rejection."""
        if event.type() in (QEvent.Type.TouchBegin, QEvent.Type.TouchUpdate, QEvent.Type.TouchEnd):
            touch_event: QTouchEvent = event
            points = touch_event.points()
            self.user_activity_detected.emit()

            # Palm Rejection: Discard large palm contacts (> 42px)
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
                        scale = dist / self.touch_initial_distance
                        self.zoom_factor = max(0.4, min(6.0, self.touch_initial_zoom * scale))

                    delta = center - self.touch_last_center
                    self.pan_offset += delta
                    self.touch_last_center = center
                    self.update()

                event.accept()
                return True

            elif len(valid_points) == 1 and touch_event.type() == QEvent.Type.TouchUpdate:
                if self.zoom_factor > 1.05:
                    delta = valid_points[0].position() - valid_points[0].pressPosition()
                    self.pan_offset += delta * 0.1
                    self.update()
                    event.accept()
                    return True

        return super().event(event)

    def tabletEvent(self, event: QTabletEvent):
        """Stylus / Pen handling with barrel button pan."""
        self.user_activity_detected.emit()
        pointer_type = event.pointingDevice().pointerType()
        is_eraser = (pointer_type == QPointingDevice.PointerType.Eraser)

        if event.buttons() & Qt.MouseButton.RightButton:
            if event.type() == QEvent.Type.TabletMove:
                delta = event.position() - self.last_mouse_pos
                self.pan_offset += delta
                self.update()
            self.last_mouse_pos = event.position()
            event.accept()
            return

        if is_eraser and event.type() == QEvent.Type.TabletPress:
            self.zoom_factor = 1.0
            self.pan_offset = QPointF(0, 0)
            self.update()
            event.accept()
            return

        self.last_mouse_pos = event.position()
        super().tabletEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        self.user_activity_detected.emit()
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 0.85
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
            delta = event.position() - self.last_mouse_pos
            self.pan_offset += delta
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
        urls = event.mimeData().urls()
        paths = [url.toLocalFile() for url in urls if url.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
