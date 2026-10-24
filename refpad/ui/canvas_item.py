"""
Interactive BeeRef Canvas Item: movable, scalable, rotatable, flippable image tile.
"""
from typing import Optional
from PySide6.QtWidgets import QGraphicsItem, QGraphicsPixmapItem, QStyleOptionGraphicsItem, QWidget
from PySide6.QtGui import QPainter, QPixmap, QColor, QPen, QBrush, QFont, QTransform
from PySide6.QtCore import Qt, QRectF, QPointF

from refpad.models.item import RefItem

class CanvasRefItem(QGraphicsItem):
    def __init__(self, ref_item: RefItem, parent=None):
        super().__init__(parent)
        self.ref_item = ref_item
        self.pixmap: Optional[QPixmap] = ref_item.get_transformed_pixmap()

        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)
        self.is_hovered: bool = False

    def boundingRect(self) -> QRectF:
        if not self.pixmap or self.pixmap.isNull():
            return QRectF(0, 0, 200, 200)
        return QRectF(0, 0, self.pixmap.width(), self.pixmap.height())

    def update_transformations(self):
        self.prepareGeometryChange()
        self.pixmap = self.ref_item.get_transformed_pixmap()
        self.update()

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: Optional[QWidget] = None):
        if not self.pixmap or self.pixmap.isNull():
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        # Draw pixmap
        painter.drawPixmap(0, 0, self.pixmap)

        # Selection or hover highlight
        rect = self.boundingRect()
        if self.isSelected():
            pen = QPen(QColor(126, 87, 246, 230), 3)  # Bright accent purple
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

            # Draw corner grip handles
            handle_size = 10
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            painter.setPen(QPen(QColor(126, 87, 246), 1.5))
            for pt in [rect.topLeft(), rect.topRight(), rect.bottomLeft(), rect.bottomRight()]:
                painter.drawRect(QRectF(pt.x() - handle_size / 2, pt.y() - handle_size / 2, handle_size, handle_size))

            # Name badge on top
            badge_rect = QRectF(0, -24, min(300, max(120, len(self.ref_item.name) * 8)), 20)
            painter.setBrush(QBrush(QColor(20, 22, 28, 220)))
            painter.setPen(QPen(QColor(126, 87, 246, 180), 1))
            painter.drawRoundedRect(badge_rect, 4, 4)
            painter.setPen(QColor(240, 240, 245))
            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.DemiBold))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, self.ref_item.name)

        elif self.is_hovered:
            pen = QPen(QColor(255, 255, 255, 70), 1.5)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

    def hoverEnterEvent(self, event):
        self.is_hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.is_hovered = False
        self.update()
        super().hoverLeaveEvent(event)
