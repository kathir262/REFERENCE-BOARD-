"""
BeeRef Infinite Canvas View (Modern 2D Moodboard).
Full-bleed infinite canvas with subtle dot grid, smooth pinch-to-zoom,
and multi-item drag & drop arrangement.
"""
from typing import List, Optional
import math
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QWidget
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QWheelEvent, QMouseEvent,
    QKeyEvent, QDragEnterEvent, QDropEvent, QFont, QTouchEvent,
    QTabletEvent, QPointingDevice
)
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QEvent

from refpad.models.item import RefItem
from refpad.ui.canvas_item import CanvasRefItem

class CanvasView(QGraphicsView):
    files_dropped = Signal(list)
    start_session_with_item = Signal(object)
    user_activity_detected = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(-50000, -50000, 100000, 100000)
        self.setScene(self.scene)

        self.viewport().setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)

        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

        # Deep slate background
        self.setBackgroundBrush(QBrush(QColor(14, 15, 20)))

        self.is_panning = False
        self.pan_start_pos = QPointF(0, 0)
        self.touch_initial_dist = 0.0
        self.touch_last_center = QPointF(0, 0)
        self.setAcceptDrops(True)

    def drawBackground(self, painter: QPainter, rect: QRectF):
        """Draw subtle dot grid pattern on infinite canvas."""
        super().drawBackground(painter, rect)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
        painter.setPen(QColor(255, 255, 255, 12))

        grid_size = 50
        left = int(rect.left()) - (int(rect.left()) % grid_size)
        top = int(rect.top()) - (int(rect.top()) % grid_size)

        points = []
        x = left
        while x < rect.right():
            y = top
            while y < rect.bottom():
                points.append(QPointF(x, y))
                y += grid_size
            x += grid_size

        if points:
            painter.drawPoints(points)
        painter.restore()

    def add_ref_items(self, items: List[RefItem], auto_tile: bool = True):
        canvas_items = []
        for item in items:
            c_item = CanvasRefItem(item)
            self.scene.addItem(c_item)
            canvas_items.append(c_item)

        if auto_tile and canvas_items:
            self.auto_arrange_items(canvas_items)

    def auto_arrange_items(self, items: Optional[List[CanvasRefItem]] = None):
        if items is None:
            items = [it for it in self.scene.items() if isinstance(it, CanvasRefItem)]
        if not items:
            return

        spacing = 40
        x_cursor = 0
        y_cursor = 0
        row_max_h = 0
        cols = max(3, int(len(items) ** 0.5 * 1.5))

        for idx, item in enumerate(items):
            rect = item.boundingRect()
            item.setPos(x_cursor, y_cursor)
            row_max_h = max(row_max_h, rect.height())
            x_cursor += rect.width() + spacing

            if (idx + 1) % cols == 0:
                x_cursor = 0
                y_cursor += row_max_h + spacing
                row_max_h = 0

        self.fit_all_items()

    def fit_all_items(self):
        items_rect = self.scene.itemsBoundingRect()
        if not items_rect.isNull() and items_rect.width() > 0:
            self.fitInView(items_rect.adjusted(-60, -60, 60, 60), Qt.AspectRatioMode.KeepAspectRatio)

    def event(self, event: QEvent) -> bool:
        """Handle 2-finger pinch-zoom and pan on infinite canvas with palm rejection."""
        if event.type() in (QEvent.Type.TouchBegin, QEvent.Type.TouchUpdate, QEvent.Type.TouchEnd):
            touch_event: QTouchEvent = event
            points = touch_event.points()
            self.user_activity_detected.emit()

            valid = [p for p in points if max(p.ellipseDiameters().width(), p.ellipseDiameters().height()) < 42]

            if len(valid) == 2:
                p1 = valid[0].position()
                p2 = valid[1].position()
                dist = math.hypot(p2.x() - p1.x(), p2.y() - p1.y())
                center = (p1 + p2) / 2.0

                if touch_event.type() == QEvent.Type.TouchBegin:
                    self.touch_initial_dist = dist
                    self.touch_last_center = center
                elif touch_event.type() == QEvent.Type.TouchUpdate:
                    if self.touch_initial_dist > 15:
                        scale_factor = dist / self.touch_initial_dist
                        step = max(0.9, min(1.1, scale_factor))
                        self.scale(step, step)
                        self.touch_initial_dist = dist

                    delta = center - self.touch_last_center
                    self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() - delta.x()))
                    self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() - delta.y()))
                    self.touch_last_center = center

                event.accept()
                return True

        return super().event(event)

    def tabletEvent(self, event: QTabletEvent):
        """Stylus barrel button pan on canvas."""
        self.user_activity_detected.emit()
        if event.buttons() & Qt.MouseButton.RightButton:
            if event.type() == QEvent.Type.TabletMove:
                delta = event.position() - self.pan_start_pos
                self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() - delta.x()))
                self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() - delta.y()))
            self.pan_start_pos = event.position()
            event.accept()
            return
        super().tabletEvent(event)

    def wheelEvent(self, event: QWheelEvent):
        self.user_activity_detected.emit()
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 0.85
        self.scale(factor, factor)

    def mousePressEvent(self, event: QMouseEvent):
        self.user_activity_detected.emit()
        if event.button() == Qt.MouseButton.MiddleButton or (event.button() == Qt.MouseButton.LeftButton and event.modifiers() & Qt.KeyboardModifier.SpaceModifier):
            self.is_panning = True
            self.pan_start_pos = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        self.user_activity_detected.emit()
        if self.is_panning:
            delta = event.position() - self.pan_start_pos
            self.pan_start_pos = event.position()
            self.horizontalScrollBar().setValue(int(self.horizontalScrollBar().value() - delta.x()))
            self.verticalScrollBar().setValue(int(self.verticalScrollBar().value() - delta.y()))
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton or self.is_panning:
            self.is_panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        self.user_activity_detected.emit()
        item = self.itemAt(event.position().toPoint())
        if isinstance(item, CanvasRefItem):
            self.start_session_with_item.emit(item.ref_item)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        selected = [it for it in self.scene.selectedItems() if isinstance(it, CanvasRefItem)]
        if selected:
            if event.key() == Qt.Key.Key_H:
                for it in selected:
                    it.ref_item.toggle_flip()
                    it.update_transformations()
                event.accept()
                return
            elif event.key() == Qt.Key.Key_G:
                for it in selected:
                    it.ref_item.toggle_grayscale()
                    it.update_transformations()
                event.accept()
                return
            elif event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                for it in selected:
                    self.scene.removeItem(it)
                event.accept()
                return
        super().keyPressEvent(event)

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        urls = event.mimeData().urls()
        paths = [url.toLocalFile() for url in urls if url.isLocalFile()]
        if paths:
            self.files_dropped.emit(paths)
            event.acceptProposedAction()
