"""
BeeRef Infinite Canvas View (Full-Featured).
Supports clipboard paste (Ctrl+V), text notes, packing, alignment,
normalization, eyedropper color picker, high-res export, and PDF page tiling.
Zero hardcoded purple — 100% theme-aware.
"""
from typing import List, Optional, Tuple
import math
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QWidget, QApplication, QFileDialog, QMessageBox
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QWheelEvent, QMouseEvent,
    QKeyEvent, QDragEnterEvent, QDropEvent, QFont, QTouchEvent,
    QTabletEvent, QPointingDevice, QImage, QPixmap
)
from PySide6.QtCore import Qt, QRectF, QPointF, Signal, QEvent

from refpad.models.item import RefItem
from refpad.ui.canvas_item import CanvasRefItem, CanvasTextItem
from refpad.ui.themes import get_current_theme

class CanvasView(QGraphicsView):
    files_dropped = Signal(list)
    start_session_with_item = Signal(object)
    user_activity_detected = Signal()
    color_sampled = Signal(str)

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

        self.is_panning = False
        self.pan_start_pos = QPointF(0, 0)
        self.touch_initial_dist = 0.0
        self.touch_last_center = QPointF(0, 0)
        self.setAcceptDrops(True)

        self.update_theme_background()

    def update_theme_background(self):
        """Hardware-accelerated seamless dot grid texture brush (zero CPU loops)."""
        theme = get_current_theme()
        pix = QPixmap(40, 40)
        pix.fill(QColor(theme.bg_dark))
        p = QPainter(pix)
        p.setPen(QColor(theme.dot_grid))
        p.drawPoint(0, 0)
        p.end()
        self.setBackgroundBrush(QBrush(pix))

    def drawForeground(self, painter: QPainter, rect: QRectF):
        """Draw empty state card only when no references exist on board."""
        super().drawForeground(painter, rect)
        items = [it for it in self.scene.items() if isinstance(it, (CanvasRefItem, CanvasTextItem))]
        if not items:
            theme = get_current_theme()
            painter.save()
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            center = self.mapToScene(self.viewport().rect().center())
            cw, ch = 390, 160
            card = QRectF(center.x() - cw / 2, center.y() - ch / 2, cw, ch)
            painter.setBrush(QBrush(QColor(theme.bg_card)))
            painter.setPen(QPen(QColor(theme.border), 1.2))
            painter.drawRoundedRect(card, 12, 12)

            painter.setPen(QColor(theme.text_primary))
            painter.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
            painter.drawText(QRectF(card.left(), card.top() + 16, cw, 28), Qt.AlignmentFlag.AlignCenter, "🖼 Reference Board Mode")

            painter.setPen(QColor(theme.text_muted))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(QRectF(card.left() + 20, card.top() + 50, cw - 40, 42), Qt.AlignmentFlag.AlignCenter,
                             "Drop reference images or PDF books here\nor paste directly from clipboard (Ctrl+V)")

            painter.setPen(QColor(theme.accent))
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
            painter.drawText(QRectF(card.left(), card.top() + 106, cw, 22), Qt.AlignmentFlag.AlignCenter,
                             "Middle-Click / Space+Drag: Pan  •  Scroll: Zoom  •  Tab: Practice")
            painter.restore()

    def add_ref_items(self, items: List[RefItem], auto_tile: bool = True):
        canvas_items = []
        for item in items:
            c_item = CanvasRefItem(item)
            self.scene.addItem(c_item)
            canvas_items.append(c_item)

        if auto_tile and canvas_items:
            self.auto_arrange_items(canvas_items)

    def paste_from_clipboard(self):
        """Paste image or text from clipboard onto canvas."""
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()

        if mime.hasImage():
            img = clipboard.image()
            if not img.isNull():
                pix = QPixmap.fromImage(img)
                ref = RefItem(source_type='clipboard', in_memory_pixmap=pix, name=f"Pasted Image ({pix.width()}x{pix.height()})")
                c_item = CanvasRefItem(ref)
                view_center = self.mapToScene(self.viewport().rect().center())
                c_item.setPos(view_center.x() - pix.width() / 2, view_center.y() - pix.height() / 2)
                self.scene.addItem(c_item)
                self.scene.clearSelection()
                c_item.setSelected(True)
                return True
        elif mime.hasText():
            text = clipboard.text().strip()
            if text:
                self.add_text_note(text)
                return True
        return False

    def copy_selected_to_clipboard(self):
        selected = [it for it in self.scene.selectedItems() if isinstance(it, CanvasRefItem)]
        if selected:
            pix = selected[0].ref_item.get_transformed_pixmap()
            if pix and not pix.isNull():
                QApplication.clipboard().setPixmap(pix)

    def add_text_note(self, text: str = "Note..."):
        view_center = self.mapToScene(self.viewport().rect().center())
        note = CanvasTextItem(text)
        note.setPos(view_center)
        self.scene.addItem(note)
        self.scene.clearSelection()
        note.setSelected(True)
        note.setFocus()

    def auto_arrange_items(self, items: Optional[List[CanvasRefItem]] = None):
        """Pack items into a neat grid."""
        if items is None:
            items = [it for it in self.scene.items() if isinstance(it, CanvasRefItem)]
        if not items:
            return

        spacing = 30
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

    def align_selected(self, mode: str):
        selected = [it for it in self.scene.selectedItems() if isinstance(it, CanvasRefItem)]
        if len(selected) < 2:
            return

        rects = [(it, it.pos(), it.boundingRect()) for it in selected]

        if mode == 'left':
            min_x = min(pos.x() for _, pos, _ in rects)
            for it, pos, _ in rects:
                it.setPos(min_x, pos.y())
        elif mode == 'right':
            max_r = max(pos.x() + br.width() for _, pos, br in rects)
            for it, pos, br in rects:
                it.setPos(max_r - br.width(), pos.y())
        elif mode == 'top':
            min_y = min(pos.y() for _, pos, _ in rects)
            for it, pos, _ in rects:
                it.setPos(pos.x(), min_y)
        elif mode == 'bottom':
            max_b = max(pos.y() + br.height() for _, pos, br in rects)
            for it, pos, br in rects:
                it.setPos(pos.x(), max_b - br.height())
        elif mode == 'center_h':
            spacing = 30
            sorted_by_x = sorted(rects, key=lambda r: r[1].x())
            start_x = sorted_by_x[0][1].x()
            curr_y = sorted_by_x[0][1].y()
            for it, _, br in sorted_by_x:
                it.setPos(start_x, curr_y)
                start_x += br.width() + spacing
        elif mode == 'center_v':
            spacing = 30
            sorted_by_y = sorted(rects, key=lambda r: r[1].y())
            curr_x = sorted_by_y[0][1].x()
            start_y = sorted_by_y[0][1].y()
            for it, _, br in sorted_by_y:
                it.setPos(curr_x, start_y)
                start_y += br.height() + spacing

    def normalize_selected(self, dimension: str = 'height'):
        selected = [it for it in self.scene.selectedItems() if isinstance(it, CanvasRefItem)]
        if len(selected) < 2:
            return

        target_val = selected[0].boundingRect().height() if dimension == 'height' else selected[0].boundingRect().width()
        for it in selected[1:]:
            cur_val = it.boundingRect().height() if dimension == 'height' else it.boundingRect().width()
            if cur_val > 0:
                s = target_val / cur_val
                it.setScale(s)

    def sample_color_at(self, scene_pos: QPointF) -> Optional[str]:
        item = self.scene.itemAt(scene_pos, self.transform())
        if isinstance(item, CanvasRefItem) and item.pixmap:
            local_pos = item.mapFromScene(scene_pos)
            lx = int(local_pos.x())
            ly = int(local_pos.y())
            if 0 <= lx < item.pixmap.width() and 0 <= ly < item.pixmap.height():
                img = item.pixmap.toImage()
                color = img.pixelColor(lx, ly)
                hex_str = color.name().upper()
                QApplication.clipboard().setText(hex_str)
                self.color_sampled.emit(hex_str)
                return hex_str
        return None

    def export_canvas_image(self, file_path: str) -> bool:
        rect = self.scene.itemsBoundingRect().adjusted(-20, -20, 20, 20)
        if rect.isEmpty():
            return False

        img = QImage(int(rect.width()), int(rect.height()), QImage.Format.Format_ARGB32_Premultiplied)
        theme = get_current_theme()
        img.fill(QColor(theme.bg_dark))

        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.scene.render(painter, QRectF(img.rect()), rect)
        painter.end()

        return img.save(file_path)

    def fit_all_items(self):
        items_rect = self.scene.itemsBoundingRect()
        if not items_rect.isNull() and items_rect.width() > 0:
            self.fitInView(items_rect.adjusted(-60, -60, 60, 60), Qt.AspectRatioMode.KeepAspectRatio)

    def event(self, event: QEvent) -> bool:
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
        if event.modifiers() & Qt.KeyboardModifier.AltModifier and event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            hex_col = self.sample_color_at(scene_pos)
            if hex_col:
                event.accept()
                return

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
        key = event.key()
        ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier

        if ctrl and key == Qt.Key.Key_V:
            if self.paste_from_clipboard():
                event.accept()
                return
        elif ctrl and key == Qt.Key.Key_C:
            self.copy_selected_to_clipboard()
            event.accept()
            return
        elif ctrl and key == Qt.Key.Key_N:
            self.add_text_note()
            event.accept()
            return

        selected = [it for it in self.scene.selectedItems() if isinstance(it, CanvasRefItem)]
        if selected:
            if key == Qt.Key.Key_H:
                for it in selected:
                    it.ref_item.toggle_flip()
                    it.update_transformations()
                event.accept()
                return
            elif key == Qt.Key.Key_G:
                for it in selected:
                    it.ref_item.toggle_grayscale()
                    it.update_transformations()
                event.accept()
                return
            elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                for it in selected:
                    self.scene.removeItem(it)
                event.accept()
                return
            elif key == Qt.Key.Key_P:
                self.auto_arrange_items(selected)
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
