"""
Line of Action practice view: Single pose display with pan/zoom and integrated Timer HUD.
"""
from typing import Optional
from pathlib import Path
import math
from PySide6.QtWidgets import QWidget, QLabel, QVBoxLayout
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
        self.is_pen_down: bool = False

        # Embedded Timer HUD
        self.timer_hud = TimerHUD(self)
        self.timer_hud.move(18, 55)

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

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # Keep Timer HUD in top-left with nice padding
        self.timer_hud.move(18, 55)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Canvas dark background
        painter.fillRect(self.rect(), QColor(16, 17, 20))

        if not self.cached_pixmap or self.cached_pixmap.isNull():
            self._draw_empty_state(painter)
            return

        # Calculate fit-to-window rectangle
        win_w, win_h = self.width(), self.height()
        pix_w = self.cached_pixmap.width()
        pix_h = self.cached_pixmap.height()

        scale_w = win_w / pix_w
        scale_h = win_h / pix_h
        base_scale = min(scale_w, scale_h) * 0.94  # Slight margin

        draw_w = pix_w * base_scale * self.zoom_factor
        draw_h = pix_h * base_scale * self.zoom_factor

        center_x = (win_w - draw_w) / 2.0 + self.pan_offset.x()
        center_y = (win_h - draw_h) / 2.0 + self.pan_offset.y()

        target_rect = QRectF(center_x, center_y, draw_w, draw_h)

        # Subtle shadow / outline around reference image
        painter.setPen(QPen(QColor(255, 255, 255, 20), 1))
        painter.drawRect(target_rect)

        painter.drawPixmap(target_rect.toRect(), self.cached_pixmap)

    def _draw_empty_state(self, painter: QPainter):
        """Clean welcome UI when no references are loaded."""
        painter.setPen(QColor(180, 190, 210))
        painter.setFont(QFont("Segoe UI", 16, QFont.Weight.Bold))
        center_rect = QRectF(0, self.height() / 2 - 90, self.width(), 35)
        painter.drawText(center_rect, Qt.AlignmentFlag.AlignCenter, "Line of Action Mode")

        painter.setPen(QColor(130, 140, 160))
        painter.setFont(QFont("Segoe UI", 11))
        sub_rect = QRectF(40, self.height() / 2 - 50, self.width() - 80, 50)
        painter.drawText(sub_rect, Qt.AlignmentFlag.AlignCenter,
                         "Drag & Drop an image folder or PDF book here\nor use the controls below to start your timed practice.")

        # Quick hint keys
        hint_rect = QRectF(40, self.height() / 2 + 10, self.width() - 80, 70)
        painter.setFont(QFont("Segoe UI", 9))
        painter.setPen(QColor(100, 110, 130))
        hints = "Space: Play/Pause  |  Right/Left: Skip/Back  |  H: Flip  |  G: B&W  |  Tab: Switch to BeeRef Board"
        painter.drawText(hint_rect, Qt.AlignmentFlag.AlignCenter, hints)

    def event(self, event: QEvent) -> bool:
        """Handle Touch Events with 2-finger pinch/pan and palm rejection."""
        if event.type() in (QEvent.Type.TouchBegin, QEvent.Type.TouchUpdate, QEvent.Type.TouchEnd):
            touch_event: QTouchEvent = event
            points = touch_event.points()

            # Palm Rejection: Discard large palm contacts
            valid_points = []
            for p in points:
                # If contact diameter is large (> 40px), classify as palm rest
                dia = max(p.ellipseDiameters().width(), p.ellipseDiameters().height())
                if dia < 42:
                    valid_points.append(p)

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
                    # 1. Pinch to zoom
                    if self.touch_initial_distance > 10:
                        scale = dist / self.touch_initial_distance
                        self.zoom_factor = max(0.4, min(6.0, self.touch_initial_zoom * scale))

                    # 2. Two-finger Pan
                    delta = center - self.touch_last_center
                    self.pan_offset += delta
                    self.touch_last_center = center
                    self.update()

                event.accept()
                return True

            elif len(valid_points) == 1 and touch_event.type() == QEvent.Type.TouchUpdate:
                # Single finger swipe when zoomed in
                if self.zoom_factor > 1.05:
                    delta = valid_points[0].position() - valid_points[0].pressPosition()
                    self.pan_offset += delta * 0.1
                    self.update()
                    event.accept()
                    return True

        return super().event(event)

    def tabletEvent(self, event: QTabletEvent):
        """Handle Stylus / Pen interactions (Wacom, Surface, S-Pen)."""
        pointer_type = event.pointingDevice().pointerType()
        is_pen = (pointer_type == QPointingDevice.PointerType.Pen)
        is_eraser = (pointer_type == QPointingDevice.PointerType.Eraser)

        # Barrel Button Pan: Hold barrel button while moving pen to pan
        if event.buttons() & Qt.MouseButton.RightButton:
            if event.type() == QEvent.Type.TabletMove:
                delta = event.position() - self.last_mouse_pos
                self.pan_offset += delta
                self.update()
            self.last_mouse_pos = event.position()
            event.accept()
            return

        if is_eraser and event.type() == QEvent.Type.TabletPress:
            # Eraser tip resets zoom
            self.zoom_factor = 1.0
            self.pan_offset = QPointF(0, 0)
            self.update()
            event.accept()
            return

        self.last_mouse_pos = event.position()
        super().tabletEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        # Zoom in/out of reference pose
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 0.85
        self.zoom_factor = max(0.5, min(5.0, self.zoom_factor * factor))
        self.update()

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton or event.button() == Qt.MouseButton.RightButton:
            self.is_panning = True
            self.last_mouse_pos = event.position()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
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
        # Reset zoom and pan
        self.zoom_factor = 1.0
        self.pan_offset = QPointF(0, 0)
        self.update()
        super().mouseDoubleClickEvent(event)

    # Drag & Drop handling
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        paths = [url.toLocalFile() for url in urls if url.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
