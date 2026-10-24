"""
BeeRef Infinite Canvas View: Freeform 2D moodboard, zoomable, pannable, multi-item reference board.
"""
from typing import List, Optional
from PySide6.QtWidgets import QGraphicsView, QGraphicsScene, QWidget
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QWheelEvent, QMouseEvent, QKeyEvent, QDragEnterEvent, QDropEvent, QFont
from PySide6.QtCore import Qt, QRectF, QPointF, Signal

from refpad.models.item import RefItem
from refpad.ui.canvas_item import CanvasRefItem

class CanvasView(QGraphicsView):
    files_dropped = Signal(list)
    start_session_with_item = Signal(object)  # (RefItem)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(-50000, -50000, 100000, 100000)
        self.setScene(self.scene)

        # Rendering hints for super crisp high-performance drawing
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

        # Background color (BeeRef dark slate)
        self.setBackgroundBrush(QBrush(QColor(19, 21, 26)))

        self.is_panning = False
        self.pan_start_pos = QPointF(0, 0)
        self.setAcceptDrops(True)

    def add_ref_items(self, items: List[RefItem], auto_tile: bool = True):
        """Add RefItems onto the infinite canvas."""
        canvas_items = []
        for item in items:
            c_item = CanvasRefItem(item)
            self.scene.addItem(c_item)
            canvas_items.append(c_item)

        if auto_tile and canvas_items:
            self.auto_arrange_items(canvas_items)

    def auto_arrange_items(self, items: Optional[List[CanvasRefItem]] = None):
        """Tile items neatly in a grid (BeeRef style pack)."""
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

        # Center view on items
        self.fit_all_items()

    def fit_all_items(self):
        items_rect = self.scene.itemsBoundingRect()
        if not items_rect.isNull() and items_rect.width() > 0:
            self.fitInView(items_rect.adjusted(-60, -60, 60, 60), Qt.AspectRatioMode.KeepAspectRatio)

    def wheelEvent(self, event: QWheelEvent):
        # Zoom centered at cursor
        delta = event.angleDelta().y()
        factor = 1.15 if delta > 0 else 0.85
        self.scale(factor, factor)

    def mousePressEvent(self, event: QMouseEvent):
        # Middle click or Space+Left click initiates smooth pan
        if event.button() == Qt.MouseButton.MiddleButton or (event.button() == Qt.MouseButton.LeftButton and event.modifiers() & Qt.KeyboardModifier.SpaceModifier):
            self.is_panning = True
            self.pan_start_pos = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
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
        # Double clicking an item starts Line of Action session starting at that item!
        item = self.itemAt(event.position().toPoint())
        if isinstance(item, CanvasRefItem):
            self.start_session_with_item.emit(item.ref_item)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        # Flip, Grayscale, or Delete selected items
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
            elif event.key() == Qt.Key.Key_Delete or event.key() == Qt.Key.Key_Backspace:
                for it in selected:
                    self.scene.removeItem(it)
                event.accept()
                return
        super().keyPressEvent(event)

    # Drag & Drop handling
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
