"""
BeeRef Infinite Canvas View (Complete 1-to-1 Feature Implementation).
Supports full BeeRef actions:
- 1-to-1 Context Menu on items and canvas
- Flip H/V, 90° Rotations, Reset Transforms, Opacity Slider
- MaxRects/Shelf Optimal Packing, Horizontal/Vertical/Square arrangement
- Align Left/Right/Top/Bottom, Normalize Height/Width/Size
- Layering (Raise to top, Lower to bottom)
- Clipboard copy/paste, text notes, high-res canvas export, bulk export
- Stylus & Touch navigation (middle drag, space drag, pinch zoom)
- Zero purple — 100% theme-aware.
"""
from typing import List, Optional, Tuple
import math
import os
from PySide6.QtWidgets import (
    QGraphicsView, QGraphicsScene, QWidget, QApplication, QFileDialog, QMessageBox
)
from PySide6.QtGui import (
    QPainter, QColor, QPen, QBrush, QWheelEvent, QMouseEvent,
    QKeyEvent, QDragEnterEvent, QDropEvent, QFont, QTouchEvent,
    QTabletEvent, QPointingDevice, QImage, QPixmap, QTransform,
    QContextMenuEvent
)
from PySide6.QtCore import Qt, QRectF, QPointF, QPoint, Signal, QEvent

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
        self.setDragMode(QGraphicsView.DragMode.NoDrag)

        self.is_panning = False
        self.is_space_pressed = False
        self.pan_start_pos = QPointF(0, 0)
        self.touch_initial_dist = 0.0
        self.touch_last_center = QPointF(0, 0)
        self.eyedropper_active = False
        self.right_press_pos = QPointF(0, 0)
        self.setAcceptDrops(True)

        self.setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)
        self.viewport().setContextMenuPolicy(Qt.ContextMenuPolicy.DefaultContextMenu)

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
            cw, ch = 420, 175
            card = QRectF(center.x() - cw / 2, center.y() - ch / 2, cw, ch)
            painter.setBrush(QBrush(QColor(theme.bg_card)))
            painter.setPen(QPen(QColor(theme.border), 1.2))
            painter.drawRoundedRect(card, 12, 12)

            painter.setPen(QColor(theme.text_primary))
            painter.setFont(QFont("Segoe UI", 15, QFont.Weight.Bold))
            painter.drawText(QRectF(card.left(), card.top() + 18, cw, 28), Qt.AlignmentFlag.AlignCenter, "🖼 Reference Board")

            painter.setPen(QColor(theme.text_muted))
            painter.setFont(QFont("Segoe UI", 10))
            painter.drawText(QRectF(card.left() + 20, card.top() + 52, cw - 40, 44), Qt.AlignmentFlag.AlignCenter,
                             "Drop reference images or PDF documents here\nor paste directly from clipboard (Ctrl+V)")

            painter.setPen(QColor(theme.accent))
            painter.setFont(QFont("Segoe UI", 9, QFont.Weight.DemiBold))
            painter.drawText(QRectF(card.left(), card.top() + 116, cw, 22), Qt.AlignmentFlag.AlignCenter,
                             "Right-Click: BeeRef Menu  •  Space+Drag: Pan  •  Tab: Practice")
            painter.restore()

    def get_all_image_items(self) -> List[CanvasRefItem]:
        return [it for it in self.scene.items() if isinstance(it, CanvasRefItem)]

    def get_selected_image_items(self) -> List[CanvasRefItem]:
        return [it for it in self.scene.selectedItems() if isinstance(it, CanvasRefItem)]

    def add_ref_items(self, items: List[RefItem], auto_tile: bool = True):
        canvas_items = []
        for item in items:
            c_item = CanvasRefItem(item)
            self.scene.addItem(c_item)
            canvas_items.append(c_item)

        if auto_tile and canvas_items:
            self.arrange_optimal(canvas_items)

    # =========================================================================
    # BEE-REF 1-to-1 CONTEXT MENU EVENT & DISPATCH
    # =========================================================================
    def show_context_menu_at(self, local_pos, global_pos, clicked_item: Optional[CanvasRefItem] = None):
        import time
        now = time.time()
        if now - getattr(self, '_last_menu_opened_at', 0) < 0.35:
            return
        self._last_menu_opened_at = now

        self.user_activity_detected.emit()
        pos_point = local_pos if isinstance(local_pos, QPoint) else local_pos.toPoint()
        gpos_point = global_pos if isinstance(global_pos, QPoint) else global_pos.toPoint()

        if clicked_item is None:
            item = self.itemAt(pos_point)
            if not item:
                # Also check scene items overlapping at this scene pos
                scene_pos = self.mapToScene(pos_point)
                items_here = self.scene.items(scene_pos)
                for it in items_here:
                    if isinstance(it, (CanvasRefItem, CanvasTextItem)):
                        item = it
                        break

            if isinstance(item, CanvasRefItem):
                clicked_item = item
                if not item.isSelected():
                    self.scene.clearSelection()
                    item.setSelected(True)
            elif isinstance(item, CanvasTextItem):
                if not item.isSelected():
                    self.scene.clearSelection()
                    item.setSelected(True)
            else:
                self.scene.clearSelection()

        from refpad.ui.beeref_menu import BeeRefContextMenu
        main_win = self.window()
        if clicked_item:
            menu = BeeRefContextMenu.build_image_menu(self, self, main_win, clicked_item)
        else:
            menu = BeeRefContextMenu.build_canvas_menu(self, self, main_win)
        menu.exec(gpos_point)

    def contextMenuEvent(self, event: QContextMenuEvent):
        item = self.itemAt(event.pos())
        if not item:
            scene_pos = self.mapToScene(event.pos())
            for it in self.scene.items(scene_pos):
                if isinstance(it, (CanvasRefItem, CanvasTextItem)):
                    item = it
                    break
        clicked_ref = item if isinstance(item, CanvasRefItem) else None
        self.show_context_menu_at(event.pos(), event.globalPos(), clicked_item=clicked_ref)
        event.accept()

    # =========================================================================
    # TRANSFORM ACTIONS
    # =========================================================================
    def flip_selected(self, vertical: bool = False):
        selected = self.get_selected_image_items()
        for it in selected:
            if vertical:
                it.ref_item.toggle_flip_v()
            else:
                it.ref_item.toggle_flip_h()
            it.update_transformations()

    def rotate_selected(self, cw: bool = True):
        selected = self.get_selected_image_items()
        for it in selected:
            if cw:
                it.ref_item.rotate_cw()
            else:
                it.ref_item.rotate_ccw()
            it.update_transformations()

    def toggle_grayscale_selected(self):
        selected = self.get_selected_image_items()
        for it in selected:
            it.ref_item.toggle_grayscale()
            it.update_transformations()

    def toggle_invert_selected(self):
        selected = self.get_selected_image_items()
        for it in selected:
            it.ref_item.toggle_invert()
            it.update_transformations()

    def set_selected_opacity(self, opacity: float):
        selected = self.get_selected_image_items()
        for it in selected:
            it.set_item_opacity(opacity)

    def reset_scale_selected(self):
        for it in self.get_selected_image_items():
            it.reset_scale()

    def reset_rotation_selected(self):
        for it in self.get_selected_image_items():
            it.reset_rotation()

    def reset_flip_selected(self):
        for it in self.get_selected_image_items():
            it.reset_flip()

    def reset_crop_selected(self):
        for it in self.get_selected_image_items():
            it.reset_crop()

    def reset_selected_transforms(self):
        for it in self.get_selected_image_items():
            it.reset_all_transforms()

    # =========================================================================
    # ARRANGE & PACKING ALGORITHMS (BeeRef 1-to-1)
    # =========================================================================
    def arrange_optimal(self, items: Optional[List[CanvasRefItem]] = None):
        """Optimal 2D shelf-pack packing algorithm centered at selection centroid."""
        if items is None:
            items = self.get_selected_image_items()
            if len(items) < 2:
                items = self.get_all_image_items()
        if len(items) < 2:
            return

        # Calculate selection center
        rects = [it.sceneBoundingRect() for it in items]
        min_x = min(r.left() for r in rects)
        max_x = max(r.right() for r in rects)
        min_y = min(r.top() for r in rects)
        max_y = max(r.bottom() for r in rects)
        center = QPointF((min_x + max_x) / 2.0, (min_y + max_y) / 2.0)

        # Sort items by height descending for optimal packing density
        sorted_items = sorted(items, key=lambda it: it.boundingRect().height() * it.scale(), reverse=True)
        gap = 24.0

        # Estimate ideal container width based on total area
        total_area = sum(it.boundingRect().width() * it.scale() * it.boundingRect().height() * it.scale() for it in items)
        target_width = max(600.0, math.sqrt(total_area * 1.3))

        # Shelf packing
        shelf_x = 0.0
        shelf_y = 0.0
        shelf_height = 0.0
        placed_positions = []

        for it in sorted_items:
            w = it.boundingRect().width() * it.scale()
            h = it.boundingRect().height() * it.scale()

            if shelf_x + w > target_width and shelf_x > 0:
                shelf_x = 0.0
                shelf_y += shelf_height + gap
                shelf_height = 0.0

            placed_positions.append((it, shelf_x, shelf_y, w, h))
            shelf_x += w + gap
            shelf_height = max(shelf_height, h)

        total_packed_w = max(x + w for _, x, _, w, _ in placed_positions)
        total_packed_h = max(y + h for _, _, y, _, h in placed_positions)

        # Re-center at selection centroid
        offset_x = center.x() - total_packed_w / 2.0
        offset_y = center.y() - total_packed_h / 2.0

        for it, x, y, _, _ in placed_positions:
            it.setPos(offset_x + x, offset_y + y)

        self.fit_all_items()

    def arrange_line(self, vertical: bool = False):
        """Arrange items in a clean line sorted by reference name."""
        items = self.get_selected_image_items()
        if len(items) < 2:
            items = self.get_all_image_items()
        if len(items) < 2:
            return

        sorted_items = sorted(items, key=lambda it: it.ref_item.name.lower())
        rects = [it.sceneBoundingRect() for it in sorted_items]
        center = QPointF(
            (min(r.left() for r in rects) + max(r.right() for r in rects)) / 2.0,
            (min(r.top() for r in rects) + max(r.bottom() for r in rects)) / 2.0
        )
        gap = 24.0

        if vertical:
            total_h = sum(it.boundingRect().height() * it.scale() for it in sorted_items) + gap * (len(sorted_items) - 1)
            curr_y = center.y() - total_h / 2.0
            for it in sorted_items:
                w = it.boundingRect().width() * it.scale()
                h = it.boundingRect().height() * it.scale()
                it.setPos(center.x() - w / 2.0, curr_y)
                curr_y += h + gap
        else:
            total_w = sum(it.boundingRect().width() * it.scale() for it in sorted_items) + gap * (len(sorted_items) - 1)
            curr_x = center.x() - total_w / 2.0
            for it in sorted_items:
                w = it.boundingRect().width() * it.scale()
                h = it.boundingRect().height() * it.scale()
                it.setPos(curr_x, center.y() - h / 2.0)
                curr_x += w + gap

        self.fit_all_items()

    def arrange_square(self):
        """Arrange items in a neat square grid sorted by reference name."""
        items = self.get_selected_image_items()
        if len(items) < 2:
            items = self.get_all_image_items()
        if len(items) < 2:
            return

        sorted_items = sorted(items, key=lambda it: it.ref_item.name.lower())
        cols = math.ceil(math.sqrt(len(sorted_items)))
        gap = 24.0

        # Compute max width and height per row/column
        max_w = max(it.boundingRect().width() * it.scale() for it in sorted_items)
        max_h = max(it.boundingRect().height() * it.scale() for it in sorted_items)

        rects = [it.sceneBoundingRect() for it in sorted_items]
        center = QPointF(
            (min(r.left() for r in rects) + max(r.right() for r in rects)) / 2.0,
            (min(r.top() for r in rects) + max(r.bottom() for r in rects)) / 2.0
        )

        rows = math.ceil(len(sorted_items) / cols)
        grid_w = cols * max_w + (cols - 1) * gap
        grid_h = rows * max_h + (rows - 1) * gap
        start_x = center.x() - grid_w / 2.0
        start_y = center.y() - grid_h / 2.0

        for idx, it in enumerate(sorted_items):
            r = idx // cols
            c = idx % cols
            it.setPos(start_x + c * (max_w + gap), start_y + r * (max_h + gap))

        self.fit_all_items()

    def align_selected(self, mode: str):
        selected = self.get_selected_image_items()
        if len(selected) < 2:
            return

        rects = [(it, it.pos(), it.boundingRect()) for it in selected]

        if mode == 'left':
            min_x = min(pos.x() for _, pos, _ in rects)
            for it, pos, _ in rects:
                it.setPos(min_x, pos.y())
        elif mode == 'right':
            max_r = max(pos.x() + br.width() * it.scale() for it, pos, br in rects)
            for it, pos, br in rects:
                it.setPos(max_r - br.width() * it.scale(), pos.y())
        elif mode == 'top':
            min_y = min(pos.y() for _, pos, _ in rects)
            for it, pos, _ in rects:
                it.setPos(pos.x(), min_y)
        elif mode == 'bottom':
            max_b = max(pos.y() + br.height() * it.scale() for it, pos, br in rects)
            for it, pos, br in rects:
                it.setPos(pos.x(), max_b - br.height() * it.scale())

    def normalize_selected(self, mode: str = 'height'):
        """Normalize selected images to equal height, width, or area (size)."""
        selected = self.get_selected_image_items()
        if len(selected) < 2:
            return

        if mode == 'height':
            avg_h = sum(it.boundingRect().height() * it.scale() for it in selected) / len(selected)
            for it in selected:
                bh = it.boundingRect().height()
                if bh > 0:
                    it.setScale(avg_h / bh)
        elif mode == 'width':
            avg_w = sum(it.boundingRect().width() * it.scale() for it in selected) / len(selected)
            for it in selected:
                bw = it.boundingRect().width()
                if bw > 0:
                    it.setScale(avg_w / bw)
        elif mode == 'size':
            avg_area = sum(it.boundingRect().width() * it.scale() * it.boundingRect().height() * it.scale() for it in selected) / len(selected)
            for it in selected:
                ba = it.boundingRect().width() * it.boundingRect().height()
                if ba > 0:
                    it.setScale(math.sqrt(avg_area / ba))

    # =========================================================================
    # Z-ORDERING & SELECTION
    # =========================================================================
    def raise_selected_to_top(self):
        for it in self.get_selected_image_items():
            it.raise_to_top()

    def lower_selected_to_bottom(self):
        for it in self.get_selected_image_items():
            it.lower_to_bottom()

    def select_all(self):
        for it in self.scene.items():
            if isinstance(it, (CanvasRefItem, CanvasTextItem)):
                it.setSelected(True)

    def deselect_all(self):
        self.scene.clearSelection()

    def invert_selection(self):
        for it in self.scene.items():
            if isinstance(it, (CanvasRefItem, CanvasTextItem)):
                it.setSelected(not it.isSelected())

    def delete_selected(self):
        for it in self.scene.selectedItems():
            self.scene.removeItem(it)

    def cut_selected(self):
        self.copy_selected_to_clipboard()
        self.delete_selected()

    # =========================================================================
    # VIEW ACTIONS
    # =========================================================================
    def fit_all_items(self):
        items_rect = self.scene.itemsBoundingRect()
        if not items_rect.isNull() and items_rect.width() > 0:
            self.fitInView(items_rect.adjusted(-60, -60, 60, 60), Qt.AspectRatioMode.KeepAspectRatio)

    def fit_selected_items(self):
        selected = self.scene.selectedItems()
        if not selected:
            self.fit_all_items()
            return
        rect = selected[0].sceneBoundingRect()
        for it in selected[1:]:
            rect = rect.united(it.sceneBoundingRect())
        self.fitInView(rect.adjusted(-40, -40, 40, 40), Qt.AspectRatioMode.KeepAspectRatio)

    def reset_zoom(self):
        self.setTransform(QTransform())

    def toggle_scrollbars(self):
        current = self.horizontalScrollBarPolicy()
        new_pol = Qt.ScrollBarPolicy.ScrollBarAsNeeded if current == Qt.ScrollBarPolicy.ScrollBarAlwaysOff else Qt.ScrollBarPolicy.ScrollBarAlwaysOff
        self.setHorizontalScrollBarPolicy(new_pol)
        self.setVerticalScrollBarPolicy(new_pol)

    # =========================================================================
    # CLIPBOARD & TEXT NOTES
    # =========================================================================
    def paste_from_clipboard(self):
        """Paste image or text from clipboard onto canvas."""
        clipboard = QApplication.clipboard()
        mime = clipboard.mimeData()

        if mime.hasImage():
            img = clipboard.image()
            if not img.isNull():
                pix = QPixmap.fromImage(img)
                ref = RefItem(source_type='clipboard', in_memory_pixmap=pix, name=f"Pasted Reference ({pix.width()}x{pix.height()})")
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
        selected = self.get_selected_image_items()
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

    # =========================================================================
    # EYEDROPPER COLOR PICKER
    # =========================================================================
    def activate_eyedropper_mode(self):
        self.eyedropper_active = True
        self.setCursor(Qt.CursorShape.CrossCursor)

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

    # =========================================================================
    # EXPORT & SCENE MANAGEMENT
    # =========================================================================
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

    def export_all_images_dialog(self, parent_widget=None):
        items = self.get_all_image_items()
        if not items:
            QMessageBox.information(parent_widget or self, "Export Images", "No images to export.")
            return

        folder = QFileDialog.getExistingDirectory(parent_widget or self, "Select Export Folder")
        if folder:
            count = 0
            for idx, it in enumerate(items):
                pix = it.ref_item.get_transformed_pixmap()
                if pix and not pix.isNull():
                    clean_name = "".join(c for c in it.ref_item.name if c.isalnum() or c in (' ', '.', '_', '-')).strip()
                    if not clean_name.lower().endswith(('.png', '.jpg', '.jpeg')):
                        clean_name += ".png"
                    out_path = os.path.join(folder, f"{idx+1:03d}_{clean_name}")
                    pix.save(out_path, "PNG")
                    count += 1
            QMessageBox.information(parent_widget or self, "Export Complete", f"Successfully exported {count} images to {folder}")

    def clear_scene_dialog(self, parent_widget=None):
        if not self.scene.items():
            return
        res = QMessageBox.question(
            parent_widget or self,
            "New Scene",
            "Are you sure you want to start a new scene? Any unsaved changes will be lost.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if res == QMessageBox.StandardButton.Yes:
            self.scene.clear()
            self.reset_zoom()

    # =========================================================================
    # EVENT HANDLERS (Stylus, Touch, Mouse, Keyboard)
    # =========================================================================
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
        if self.eyedropper_active and event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            hex_col = self.sample_color_at(scene_pos)
            self.eyedropper_active = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        if event.modifiers() & Qt.KeyboardModifier.AltModifier and event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.pos())
            hex_col = self.sample_color_at(scene_pos)
            if hex_col:
                event.accept()
                return

        if event.button() == Qt.MouseButton.MiddleButton or (event.button() == Qt.MouseButton.LeftButton and getattr(self, 'is_space_pressed', False)):
            self.is_panning = True
            self.pan_start_pos = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        if event.button() == Qt.MouseButton.RightButton:
            self.right_press_pos = event.position()
            # Immediately find and select item under right click if not selected
            item = self.itemAt(event.position().toPoint())
            if not item:
                scene_pos = self.mapToScene(event.position().toPoint())
                items_here = self.scene.items(scene_pos)
                for it in items_here:
                    if isinstance(it, (CanvasRefItem, CanvasTextItem)):
                        item = it
                        break

            self.clicked_item_on_right = item if isinstance(item, CanvasRefItem) else None
            if isinstance(item, (CanvasRefItem, CanvasTextItem)) and not item.isSelected():
                self.scene.clearSelection()
                item.setSelected(True)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.position().toPoint())
            if not item:
                scene_pos = self.mapToScene(event.position().toPoint())
                items_here = self.scene.items(scene_pos)
                if items_here:
                    item = items_here[0]
            if item and isinstance(item, (CanvasRefItem, CanvasTextItem)):
                self.setDragMode(QGraphicsView.DragMode.NoDrag)
            else:
                self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

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

        if event.button() == Qt.MouseButton.RightButton:
            delta = event.position() - getattr(self, 'right_press_pos', event.position())
            if math.hypot(delta.x(), delta.y()) < 10:
                clicked = getattr(self, 'clicked_item_on_right', None)
                self.show_context_menu_at(event.position().toPoint(), event.globalPosition().toPoint(), clicked_item=clicked)
            event.accept()
            return

        if event.button() == Qt.MouseButton.LeftButton:
            self.setDragMode(QGraphicsView.DragMode.NoDrag)

        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent):
        self.user_activity_detected.emit()
        item = self.itemAt(event.position().toPoint())
        if isinstance(item, (CanvasRefItem, CanvasTextItem)):
            self.fitInView(item.sceneBoundingRect().adjusted(-60, -60, 60, 60), Qt.AspectRatioMode.KeepAspectRatio)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        ctrl = event.modifiers() & Qt.KeyboardModifier.ControlModifier
        shift = event.modifiers() & Qt.KeyboardModifier.ShiftModifier

        if key == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.is_space_pressed = True
            if not self.is_panning:
                self.setCursor(Qt.CursorShape.OpenHandCursor)

        if ctrl and key == Qt.Key.Key_V:
            if self.paste_from_clipboard():
                event.accept()
                return
        elif ctrl and key == Qt.Key.Key_C:
            self.copy_selected_to_clipboard()
            event.accept()
            return
        elif ctrl and key == Qt.Key.Key_X:
            self.cut_selected()
            event.accept()
            return
        elif ctrl and key == Qt.Key.Key_A:
            self.select_all()
            event.accept()
            return
        elif (ctrl and shift and key == Qt.Key.Key_A) or (ctrl and key == Qt.Key.Key_D):
            self.deselect_all()
            event.accept()
            return
        elif ctrl and key == Qt.Key.Key_T:
            self.add_text_note()
            event.accept()
            return

        # Arrange & Normalize shortcuts
        if shift and key == Qt.Key.Key_O:
            self.arrange_optimal()
            event.accept()
            return
        elif shift and key == Qt.Key.Key_H:
            self.normalize_selected(mode='height')
            event.accept()
            return
        elif shift and key == Qt.Key.Key_W:
            self.normalize_selected(mode='width')
            event.accept()
            return
        elif shift and key == Qt.Key.Key_S:
            self.normalize_selected(mode='size')
            event.accept()
            return

        # Single key item operations
        selected = self.get_selected_image_items()
        if selected:
            if key == Qt.Key.Key_H:
                self.flip_selected(vertical=False)
                event.accept()
                return
            elif key == Qt.Key.Key_V:
                self.flip_selected(vertical=True)
                event.accept()
                return
            elif key == Qt.Key.Key_G:
                self.toggle_grayscale_selected()
                event.accept()
                return
            elif key == Qt.Key.Key_I:
                self.toggle_invert_selected()
                event.accept()
                return
            elif key == Qt.Key.Key_R:
                self.reset_selected_transforms()
                event.accept()
                return
            elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
                self.delete_selected()
                event.accept()
                return
            elif key == Qt.Key.Key_P:
                self.arrange_optimal(selected)
                event.accept()
                return
            elif key == Qt.Key.Key_PageUp:
                self.raise_selected_to_top()
                event.accept()
                return
            elif key == Qt.Key.Key_PageDown:
                self.lower_selected_to_bottom()
                event.accept()
                return

        if key in (Qt.Key.Key_1, Qt.Key.Key_F):
            self.fit_all_items()
            event.accept()
            return
        elif key == Qt.Key.Key_2:
            self.fit_selected_items()
            event.accept()
            return
        elif key == Qt.Key.Key_S:
            self.activate_eyedropper_mode()
            event.accept()
            return

        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.is_space_pressed = False
            if not self.is_panning:
                self.setCursor(Qt.CursorShape.ArrowCursor)
        super().keyReleaseEvent(event)

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
