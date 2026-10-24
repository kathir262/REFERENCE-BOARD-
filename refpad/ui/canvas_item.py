"""
Interactive BeeRef Canvas Item: movable, scalable, rotatable, flippable image tile and text notes.
Full BeeRef feature set: 90° rotations, opacity, layering (Z-order), reset transforms.
"""
from typing import Optional
from PySide6.QtWidgets import (
    QGraphicsItem, QGraphicsTextItem, QStyleOptionGraphicsItem, QWidget
)
from PySide6.QtGui import (
    QPainter, QPixmap, QColor, QPen, QBrush, QFont
)
from PySide6.QtCore import Qt, QRectF, QPointF

from refpad.models.item import RefItem
from refpad.ui.themes import get_current_theme

class CanvasRefItem(QGraphicsItem):
    def __init__(self, ref_item: RefItem, parent=None):
        super().__init__(parent)
        self.ref_item = ref_item
        self.pixmap: Optional[QPixmap] = ref_item.get_transformed_pixmap()
        self.item_opacity: float = ref_item.opacity

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

    def set_item_opacity(self, opacity: float):
        self.item_opacity = max(0.05, min(1.0, opacity))
        self.ref_item.opacity = self.item_opacity
        self.update()

    def reset_scale(self):
        self.setScale(1.0)

    def reset_rotation(self):
        self.ref_item.rotation = 0.0
        self.update_transformations()

    def reset_flip(self):
        self.ref_item.is_flipped_h = False
        self.ref_item.is_flipped_v = False
        self.update_transformations()

    def reset_crop(self):
        self.ref_item.reset_crop()
        self.update_transformations()

    def reset_all_transforms(self):
        self.setScale(1.0)
        self.ref_item.reset_transforms()
        self.ref_item.is_grayscale = False
        self.ref_item.is_inverted = False
        self.set_item_opacity(1.0)
        self.update_transformations()

    def raise_to_top(self):
        scene = self.scene()
        if scene:
            all_z = [it.zValue() for it in scene.items() if it != self]
            max_z = max(all_z, default=0.0)
            self.setZValue(max_z + 1.0)

    def lower_to_bottom(self):
        scene = self.scene()
        if scene:
            all_z = [it.zValue() for it in scene.items() if it != self]
            min_z = min(all_z, default=0.0)
            self.setZValue(min_z - 1.0)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: Optional[QWidget] = None):
        if not self.pixmap or self.pixmap.isNull():
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.setOpacity(self.item_opacity)

        theme = get_current_theme()

        # Draw image
        painter.drawPixmap(0, 0, self.pixmap)

        rect = self.boundingRect()
        if self.isSelected():
            accent_col = QColor(theme.accent)
            pen = QPen(accent_col, 2.5)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(rect)

            # Draw corner grip handles
            handle_size = 9
            painter.setBrush(QBrush(accent_col))
            painter.setPen(QPen(QColor(0, 0, 0, 160), 1))
            for pt in [rect.topLeft(), rect.topRight(), rect.bottomLeft(), rect.bottomRight()]:
                painter.drawRect(QRectF(pt.x() - handle_size / 2, pt.y() - handle_size / 2, handle_size, handle_size))

            # Floating name badge
            badge_w = min(320.0, max(100.0, len(self.ref_item.name) * 7.5 + 16))
            badge_rect = QRectF(0, -22, badge_w, 18)
            painter.setBrush(QBrush(QColor(theme.bg_card)))
            painter.setPen(QPen(accent_col, 1))
            painter.drawRoundedRect(badge_rect, 4, 4)
            painter.setPen(QColor(theme.text_primary))
            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, self.ref_item.name)

        elif self.is_hovered:
            painter.setPen(QPen(QColor(255, 255, 255, 60), 1.2))
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

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.RightButton:
            if not self.isSelected():
                if self.scene():
                    self.scene().clearSelection()
                self.setSelected(True)
            event.accept()
            return
        super().mousePressEvent(event)

    def contextMenuEvent(self, event):
        if not self.isSelected():
            if self.scene():
                self.scene().clearSelection()
            self.setSelected(True)
        views = self.scene().views() if self.scene() else []
        if views:
            views[0].show_context_menu_at(event.pos().toPoint(), event.screenPos(), clicked_item=self)
        event.accept()


class CanvasTextItem(QGraphicsTextItem):
    """Sticky text note on BeeRef canvas."""
    def __init__(self, text: str = "Note...", parent=None):
        super().__init__(text, parent)
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsMovable |
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QGraphicsItem.GraphicsItemFlag.ItemIsFocusable
        )
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFont(QFont("Segoe UI", 14, QFont.Weight.DemiBold))
        self.setDefaultTextColor(QColor(240, 240, 245))

    def raise_to_top(self):
        scene = self.scene()
        if scene:
            all_z = [it.zValue() for it in scene.items() if it != self]
            max_z = max(all_z, default=0.0)
            self.setZValue(max_z + 1.0)

    def lower_to_bottom(self):
        scene = self.scene()
        if scene:
            all_z = [it.zValue() for it in scene.items() if it != self]
            min_z = min(all_z, default=0.0)
            self.setZValue(min_z - 1.0)

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget: Optional[QWidget] = None):
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = self.boundingRect()
        painter.setBrush(QBrush(QColor(24, 26, 32, 210)))
        theme = get_current_theme()
        pen_col = QColor(theme.accent) if self.isSelected() else QColor(255, 255, 255, 30)
        painter.setPen(QPen(pen_col, 1.2))
        painter.drawRoundedRect(rect, 6, 6)
        super().paint(painter, option, widget)
