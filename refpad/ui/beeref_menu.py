"""
Complete 1-to-1 BeeRef Context Menu and Action Engine for Reference Board.
Accurately split into:
1. Image Context Menu (Green Circle): Focused image transforms & operations on right-clicking an image.
2. Dock System Menu (Red Circle): Full BeeRef system menus (File, Edit, View, Insert, Transform, Normalize, Arrange, Images, Practice Mode, Themes, Help) for the bottom dock button.
3. Canvas Context Menu: Quick canvas actions + system menus when right-clicking empty canvas.
4. Import Destination Dialog: Clear separation between Reference Board and Practice Mode during PDF / image / folder imports.
"""
import os
import math
from typing import List, Optional
from PySide6.QtWidgets import (
    QMenu, QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSlider,
    QPushButton, QMessageBox, QFileDialog, QTableWidget, QTableWidgetItem,
    QHeaderView, QApplication, QFrame
)
from PySide6.QtCore import Qt, QPoint, QPointF
from PySide6.QtGui import QKeySequence, QFont, QColor

from refpad.models.item import RefItem
from refpad.ui.canvas_item import CanvasRefItem, CanvasTextItem
from refpad.ui.themes import get_current_theme, THEMES, set_current_theme

def style_beeref_menu(menu: QMenu):
    """Apply consistent sleek theme styling to any QMenu."""
    theme = get_current_theme()
    menu.setStyleSheet(f"""
        QMenu {{
            background-color: {theme.bg_card};
            color: {theme.text_primary};
            border: 1px solid {theme.border};
            border-radius: 8px;
            padding: 5px;
        }}
        QMenu::item {{
            padding: 6px 28px 6px 14px;
            border-radius: 4px;
            font-family: 'Segoe UI', -apple-system, sans-serif;
            font-size: 11px;
            font-weight: 500;
        }}
        QMenu::item:selected {{
            background-color: {theme.accent};
            color: {theme.bg_dark};
        }}
        QMenu::item:disabled {{
            color: {theme.text_muted};
            background-color: transparent;
        }}
        QMenu::separator {{
            height: 1px;
            background: {theme.border};
            margin: 4px 6px;
        }}
    """)


class ImportDestinationDialog(QDialog):
    """
    Sleek theme-styled dialog asking whether to import to Reference Board, Practice Mode, or Both.
    Guarantees that Reference Board and Practice Mode remain separate!
    """
    def __init__(self, parent, count: int = 1, current_mode: str = 'canvas'):
        super().__init__(parent)
        self.setWindowTitle("Import References")
        self.setFixedSize(440, 290)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        self.selected_target = current_mode

        theme = get_current_theme()
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {theme.bg_card};
                color: {theme.text_primary};
                border: 1px solid {theme.border};
                border-radius: 12px;
            }}
            QLabel {{
                color: {theme.text_primary};
                font-family: 'Segoe UI', -apple-system, sans-serif;
            }}
            QPushButton {{
                background-color: {theme.bg_dark};
                color: {theme.text_primary};
                border: 1px solid {theme.border};
                border-radius: 8px;
                padding: 10px 16px;
                font-size: 11px;
                font-weight: 600;
                text-align: left;
            }}
            QPushButton:hover {{
                background-color: {theme.accent};
                color: {theme.bg_dark};
                border-color: {theme.accent};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(10)

        lbl_title = QLabel(f"Import {count} Reference{'s' if count != 1 else ''}")
        lbl_title.setFont(QFont("Segoe UI", 13, QFont.Weight.Bold))
        layout.addWidget(lbl_title)

        lbl_sub = QLabel("Choose destination mode for imported references:")
        lbl_sub.setFont(QFont("Segoe UI", 10))
        lbl_sub.setStyleSheet(f"color: {theme.text_muted};")
        layout.addWidget(lbl_sub)

        layout.addSpacing(4)

        btn_canvas = QPushButton("🖼  Reference Board\n    Load into the moodboard canvas for arranging, scaling & study")
        btn_canvas.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_canvas.clicked.connect(lambda: self._choose('canvas'))
        layout.addWidget(btn_canvas)

        btn_action = QPushButton("⏱  Practice Mode\n    Load into timed gesture drawing session with countdown timer")
        btn_action.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_action.clicked.connect(lambda: self._choose('action'))
        layout.addWidget(btn_action)

        btn_both = QPushButton("⚡  Both Modes\n    Load into Reference Board canvas AND Practice session")
        btn_both.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_both.clicked.connect(lambda: self._choose('both'))
        layout.addWidget(btn_both)

    def _choose(self, target: str):
        self.selected_target = target
        self.accept()


class OpacitySliderDialog(QDialog):
    """BeeRef Opacity Adjustment Dialog with live preview."""
    def __init__(self, parent, target_items: List[CanvasRefItem]):
        super().__init__(parent)
        self.target_items = target_items
        self.setWindowTitle("Change Opacity")
        self.setFixedSize(320, 140)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        theme = get_current_theme()
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {theme.bg_card};
                color: {theme.text_primary};
                border: 1px solid {theme.border};
                border-radius: 10px;
            }}
            QLabel {{
                color: {theme.text_primary};
                font-family: 'Segoe UI';
                font-size: 12px;
            }}
            QSlider::groove:horizontal {{
                height: 6px;
                background: {theme.border};
                border-radius: 3px;
            }}
            QSlider::sub-page:horizontal {{
                background: {theme.accent};
                border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {theme.accent};
                border: 2px solid {theme.bg_dark};
                width: 16px;
                margin-top: -5px;
                margin-bottom: -5px;
                border-radius: 8px;
            }}
            QPushButton {{
                background-color: {theme.bg_dark};
                color: {theme.text_primary};
                border: 1px solid {theme.border};
                padding: 6px 16px;
                border-radius: 6px;
                font-size: 11px;
                font-weight: 600;
            }}
            QPushButton:hover {{
                background-color: {theme.accent};
                color: {theme.bg_dark};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 16)
        layout.setSpacing(12)

        init_val = int(target_items[0].item_opacity * 100) if target_items else 100
        self.lbl_info = QLabel(f"Opacity: {init_val}%")
        self.lbl_info.setFont(QFont("Segoe UI", 10, QFont.Weight.Bold))
        layout.addWidget(self.lbl_info)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(5, 100)
        self.slider.setValue(init_val)
        self.slider.valueChanged.connect(self._on_slider_changed)
        layout.addWidget(self.slider)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_ok = QPushButton("Done")
        btn_ok.clicked.connect(self.accept)
        btn_row.addWidget(btn_ok)
        layout.addLayout(btn_row)

    def _on_slider_changed(self, value: int):
        self.lbl_info.setText(f"Opacity: {value}%")
        opacity = value / 100.0
        for it in self.target_items:
            it.set_item_opacity(opacity)


class ShortcutsHelpDialog(QDialog):
    """Keyboard & Mouse Shortcuts Dialog (BeeRef + Practice Mode)."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Reference Board — Keyboard & Mouse Shortcuts")
        self.resize(560, 480)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)

        theme = get_current_theme()
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {theme.bg_card};
                color: {theme.text_primary};
            }}
            QLabel {{
                color: {theme.text_primary};
            }}
            QTableWidget {{
                background-color: {theme.bg_dark};
                color: {theme.text_primary};
                border: 1px solid {theme.border};
                border-radius: 6px;
                gridline-color: {theme.border};
            }}
            QHeaderView::section {{
                background-color: {theme.bg_card};
                color: {theme.text_muted};
                border: none;
                border-bottom: 1px solid {theme.border};
                padding: 6px;
                font-weight: bold;
            }}
            QPushButton {{
                background-color: {theme.accent};
                color: {theme.bg_dark};
                border: none;
                border-radius: 6px;
                padding: 8px 24px;
                font-weight: bold;
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)

        lbl = QLabel("Reference Board & Practice Shortcuts")
        lbl.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
        layout.addWidget(lbl)

        table = QTableWidget(18, 2)
        table.setHorizontalHeaderLabels(["Action", "Shortcut / Gesture"])
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        table.verticalHeader().setVisible(False)
        table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)

        shortcuts = [
            ("Drag Reference Image", "Left Click & Drag Image"),
            ("Pan Canvas", "Middle Click / Space + Left Drag"),
            ("Zoom In / Out", "Mouse Wheel / Touch Pinch"),
            ("Toggle Mode (Reference Board / Practice)", "Tab"),
            ("Fit Scene (All References)", "1  or  F"),
            ("Fit Selection", "2"),
            ("Flip Horizontally", "H"),
            ("Flip Vertically", "V"),
            ("Grayscale Toggle", "G"),
            ("Invert Colors", "I"),
            ("Reset All Transforms", "R"),
            ("Optimal Auto-Pack", "Shift+O  or  P"),
            ("Normalize Height / Width / Size", "Shift+H / Shift+W / Shift+S"),
            ("Copy / Paste Reference", "Ctrl+C  /  Ctrl+V"),
            ("Insert Images / PDFs", "Ctrl+I"),
            ("Add Sticky Note", "Ctrl+T"),
            ("Save / Open Board", "Ctrl+S  /  Ctrl+O"),
            ("Export Board as Image", "Ctrl+Shift+E"),
            ("Pin Always On Top", "T"),
        ]

        for row, (act, sc) in enumerate(shortcuts):
            item_act = QTableWidgetItem(act)
            item_sc = QTableWidgetItem(sc)
            item_sc.setFont(QFont("Consolas", 10, QFont.Weight.Bold))
            table.setItem(row, 0, item_act)
            table.setItem(row, 1, item_sc)

        layout.addWidget(table)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)


class BeeRefContextMenu:
    """
    Constructs the exact requested menus:
    - build_image_menu: The Green Circled menu for right-clicking an image.
    - build_dock_menu / build_system_menu: The Red Circled menu for the bottom dock button (≡).
    - build_canvas_menu: For right-clicking empty canvas.
    """

    @staticmethod
    def build_image_menu(
        parent,
        canvas_view,
        main_window,
        target_item: CanvasRefItem
    ) -> QMenu:
        """
        GREEN CIRCLE MENU:
        Opened strictly when right-clicking on an image reference.
        Clean, focused, zero clutter.
        """
        menu = QMenu(parent)
        style_beeref_menu(menu)

        selected_items = [it for it in canvas_view.scene.selectedItems() if isinstance(it, CanvasRefItem)]
        active_items = selected_items if selected_items else [target_item]

        # 1. Flip Horizontally
        menu.addAction("🔄 Flip Horizontally\tH", lambda: canvas_view.flip_selected(vertical=False))
        # 2. Flip Vertically
        menu.addAction("🔃 Flip Vertically\tV", lambda: canvas_view.flip_selected(vertical=True))
        # 3. Rotate 90° CW
        menu.addAction("⟳ Rotate 90° CW", lambda: canvas_view.rotate_selected(cw=True))
        # 4. Rotate 90° CCW
        menu.addAction("⟲ Rotate 90° CCW", lambda: canvas_view.rotate_selected(cw=False))
        # 5. Grayscale
        menu.addAction("🌓 Grayscale\tG", lambda: canvas_view.toggle_grayscale_selected())
        # 6. Invert Colors
        menu.addAction("🔆 Invert Colors\tI", lambda: canvas_view.toggle_invert_selected())

        # 7. Opacity Submenu
        op_menu = menu.addMenu("💧 Opacity")
        style_beeref_menu(op_menu)
        for pct in [100, 75, 50, 25]:
            op_menu.addAction(f"{pct}%", lambda p=pct: canvas_view.set_selected_opacity(p / 100.0))
        op_menu.addSeparator()
        op_menu.addAction("Custom Opacity...", lambda: BeeRefContextMenu.show_opacity_dialog(canvas_view, active_items))

        # 8. Reset Transforms
        menu.addAction("↩ Reset Transforms\tR", lambda: canvas_view.reset_selected_transforms())

        menu.addSeparator()

        # Convenient item actions
        menu.addAction("📋 Copy Reference\tCtrl+C", canvas_view.copy_selected_to_clipboard)
        menu.addAction("✂ Cut Reference\tCtrl+X", canvas_view.cut_selected)
        menu.addAction("🗑 Delete Reference\tDel", canvas_view.delete_selected)
        menu.addSeparator()
        menu.addAction("⬆ Raise to Top\tPgUp", canvas_view.raise_selected_to_top)
        menu.addAction("⬇ Lower to Bottom\tPgDown", canvas_view.lower_selected_to_bottom)

        return menu

    @staticmethod
    def build_dock_menu(
        parent,
        canvas_view,
        main_window
    ) -> QMenu:
        """
        RED CIRCLE MENU:
        Opened strictly when clicking the hamburger button (≡) on the bottom floating dock.
        Full 1-to-1 BeeRef system menu structure.
        """
        menu = QMenu(parent)
        style_beeref_menu(menu)

        selected_items = [it for it in canvas_view.scene.selectedItems() if isinstance(it, CanvasRefItem)]
        has_sel = len(selected_items) > 0
        has_multi = len(selected_items) >= 2

        # =========================================================================
        # 1. FILE SUBMENU
        # =========================================================================
        m_file = menu.addMenu("📁 &File")
        style_beeref_menu(m_file)
        m_file.addAction("&New Scene\tCtrl+N", lambda: canvas_view.clear_scene_dialog(main_window))
        m_file.addAction("&Open Board...\tCtrl+O", main_window.open_board_dialog)
        m_file.addSeparator()
        m_file.addAction("Open PDF Reference Book...", main_window.open_pdf_dialog)
        m_file.addAction("Open Images / PDF Folder...", main_window.open_folder_dialog)
        m_file.addSeparator()
        m_file.addAction("&Save Board\tCtrl+S", main_window.save_board_dialog)
        m_file.addAction("Save Board &As...\tCtrl+Shift+S", main_window.save_board_as_dialog)
        m_file.addAction("E&xport Scene as Image...\tCtrl+Shift+E", main_window.export_board_dialog)
        m_file.addAction("Export &Images to Folder...", lambda: canvas_view.export_all_images_dialog(main_window))
        m_file.addSeparator()
        m_file.addAction("&Quit\tCtrl+Q", QApplication.quit)

        # =========================================================================
        # 2. EDIT SUBMENU
        # =========================================================================
        m_edit = menu.addMenu("✏ &Edit")
        style_beeref_menu(m_edit)
        m_edit.addAction("&Select All\tCtrl+A", canvas_view.select_all)
        m_edit.addAction("&Deselect All\tCtrl+Shift+A", canvas_view.deselect_all)
        m_edit.addAction("&Invert Selection", canvas_view.invert_selection)
        m_edit.addSeparator()
        act_cut = m_edit.addAction("Cu&t\tCtrl+X", canvas_view.cut_selected)
        act_cut.setEnabled(has_sel)
        act_copy = m_edit.addAction("&Copy\tCtrl+C", canvas_view.copy_selected_to_clipboard)
        act_copy.setEnabled(has_sel)
        m_edit.addAction("&Paste\tCtrl+V", canvas_view.paste_from_clipboard)
        act_del = m_edit.addAction("&Delete\tDel", canvas_view.delete_selected)
        act_del.setEnabled(has_sel)
        m_edit.addSeparator()
        act_top = m_edit.addAction("&Raise to Top\tPgUp", canvas_view.raise_selected_to_top)
        act_top.setEnabled(has_sel)
        act_bot = m_edit.addAction("&Lower to Bottom\tPgDown", canvas_view.lower_selected_to_bottom)
        act_bot.setEnabled(has_sel)

        # =========================================================================
        # 3. VIEW SUBMENU
        # =========================================================================
        m_view = menu.addMenu("👁 &View")
        style_beeref_menu(m_view)
        m_view.addAction("&Fit Scene\t1, F", canvas_view.fit_all_items)
        act_fitsel = m_view.addAction("Fit &Selection\t2", canvas_view.fit_selected_items)
        act_fitsel.setEnabled(has_sel)
        m_view.addAction("Reset &Zoom (1:1)", canvas_view.reset_zoom)
        m_view.addSeparator()
        m_view.addAction("&Fullscreen\tF11", main_window.toggle_fullscreen)
        m_view.addAction("&Always On Top\tT", main_window.toggle_always_on_top)
        m_view.addAction("Toggle &Scrollbars", canvas_view.toggle_scrollbars)

        # =========================================================================
        # 4. INSERT SUBMENU
        # =========================================================================
        m_insert = menu.addMenu("➕ &Insert")
        style_beeref_menu(m_insert)
        m_insert.addAction("&Images / PDF Documents...\tCtrl+I", main_window.open_folder_or_files_dialog)
        m_insert.addAction("&Text Note\tCtrl+T", lambda: canvas_view.add_text_note())

        # =========================================================================
        # 5. TRANSFORM SUBMENU
        # =========================================================================
        m_trans = menu.addMenu("🔀 &Transform")
        style_beeref_menu(m_trans)
        act_fliph = m_trans.addAction("Flip &Horizontally\tH", lambda: canvas_view.flip_selected(vertical=False))
        act_fliph.setEnabled(has_sel)
        act_flipv = m_trans.addAction("Flip &Vertically\tV", lambda: canvas_view.flip_selected(vertical=True))
        act_flipv.setEnabled(has_sel)
        act_rotcw = m_trans.addAction("Rotate 90° &Clockwise", lambda: canvas_view.rotate_selected(cw=True))
        act_rotcw.setEnabled(has_sel)
        act_rotccw = m_trans.addAction("Rotate 90° Counter-Clockwise", lambda: canvas_view.rotate_selected(cw=False))
        act_rotccw.setEnabled(has_sel)
        m_trans.addSeparator()
        act_rscale = m_trans.addAction("Reset &Scale", canvas_view.reset_scale_selected)
        act_rscale.setEnabled(has_sel)
        act_rrot = m_trans.addAction("Reset &Rotation", canvas_view.reset_rotation_selected)
        act_rrot.setEnabled(has_sel)
        act_rflip = m_trans.addAction("Reset &Flip", canvas_view.reset_flip_selected)
        act_rflip.setEnabled(has_sel)
        act_rcrop = m_trans.addAction("Reset Cro&p", canvas_view.reset_crop_selected)
        act_rcrop.setEnabled(has_sel)
        act_rall = m_trans.addAction("Reset &All Transforms\tR", canvas_view.reset_selected_transforms)
        act_rall.setEnabled(has_sel)

        # =========================================================================
        # 6. NORMALIZE SUBMENU
        # =========================================================================
        m_norm = menu.addMenu("📏 &Normalize")
        style_beeref_menu(m_norm)
        act_nh = m_norm.addAction("&Height\tShift+H", lambda: canvas_view.normalize_selected(mode='height'))
        act_nh.setEnabled(has_multi)
        act_nw = m_norm.addAction("&Width\tShift+W", lambda: canvas_view.normalize_selected(mode='width'))
        act_nw.setEnabled(has_multi)
        act_ns = m_norm.addAction("&Size (Area)\tShift+S", lambda: canvas_view.normalize_selected(mode='size'))
        act_ns.setEnabled(has_multi)

        # =========================================================================
        # 7. ARRANGE SUBMENU
        # =========================================================================
        m_arr = menu.addMenu("📐 &Arrange")
        style_beeref_menu(m_arr)
        act_pack = m_arr.addAction("&Optimal Pack\tShift+O, P", canvas_view.arrange_optimal)
        act_pack.setEnabled(has_multi or len(canvas_view.get_all_image_items()) >= 2)
        act_ahoriz = m_arr.addAction("&Horizontal (by name)", lambda: canvas_view.arrange_line(vertical=False))
        act_ahoriz.setEnabled(has_multi or len(canvas_view.get_all_image_items()) >= 2)
        act_avert = m_arr.addAction("&Vertical (by name)", lambda: canvas_view.arrange_line(vertical=True))
        act_avert.setEnabled(has_multi or len(canvas_view.get_all_image_items()) >= 2)
        act_asq = m_arr.addAction("&Square Grid (by name)", canvas_view.arrange_square)
        act_asq.setEnabled(has_multi or len(canvas_view.get_all_image_items()) >= 2)
        m_arr.addSeparator()
        act_al = m_arr.addAction("Align &Left", lambda: canvas_view.align_selected('left'))
        act_al.setEnabled(has_multi)
        act_ar = m_arr.addAction("Align &Right", lambda: canvas_view.align_selected('right'))
        act_ar.setEnabled(has_multi)
        act_at = m_arr.addAction("Align &Top", lambda: canvas_view.align_selected('top'))
        act_at.setEnabled(has_multi)
        act_ab = m_arr.addAction("Align &Bottom", lambda: canvas_view.align_selected('bottom'))
        act_ab.setEnabled(has_multi)

        # =========================================================================
        # 8. IMAGES SUBMENU
        # =========================================================================
        m_img = menu.addMenu("🖼 &Images")
        style_beeref_menu(m_img)
        act_op = m_img.addAction("Change &Opacity...", lambda: BeeRefContextMenu.show_opacity_dialog(canvas_view, selected_items))
        act_op.setEnabled(has_sel)
        act_gray = m_img.addAction("&Grayscale\tG", canvas_view.toggle_grayscale_selected)
        act_gray.setEnabled(has_sel)
        act_inv = m_img.addAction("&Invert Colors\tI", canvas_view.toggle_invert_selected)
        act_inv.setEnabled(has_sel)
        m_img.addSeparator()
        m_img.addAction("&Sample Color (Eyedropper)\tS", canvas_view.activate_eyedropper_mode)

        # =========================================================================
        # 9. PRACTICE MODE SUBMENU
        # =========================================================================
        m_prac = menu.addMenu("⏱ &Practice Mode")
        style_beeref_menu(m_prac)
        m_prac.addAction("Switch to Practice &Mode\tTab", main_window.toggle_view_mode)
        m_prac.addSeparator()
        act_send_sel = m_prac.addAction("Send &Selected Reference to Practice",
            lambda: main_window.start_practice_with_item(selected_items[0].ref_item) if selected_items else None)
        act_send_sel.setEnabled(has_sel)
        m_prac.addAction("Send &All Board References to Practice", main_window.send_all_canvas_to_practice)

        # =========================================================================
        # 10. THEMES SUBMENU
        # =========================================================================
        m_theme = menu.addMenu("🎨 &Themes")
        style_beeref_menu(m_theme)
        for key, pal in THEMES.items():
            act_th = m_theme.addAction(pal.name, lambda k=key: main_window.apply_theme(k))
            if key == get_current_theme().name:
                act_th.setCheckable(True)
                act_th.setChecked(True)

        # =========================================================================
        # 11. HELP SUBMENU
        # =========================================================================
        m_help = menu.addMenu("❓ &Help")
        style_beeref_menu(m_help)
        m_help.addAction("&Keyboard & Mouse Shortcuts...\tF1", lambda: ShortcutsHelpDialog(main_window).exec())
        m_help.addAction("&About Reference Board...", lambda: QMessageBox.about(
            main_window,
            "About Reference Board",
            "<b>Reference Board</b> — BeeRef + Line of Action Companion<br><br>"
            "Full 1-to-1 BeeRef reference moodboard system seamlessly fused with "
            "Line of Action gesture practice sessions.<br><br>"
            "Pure Black & White by default. Zero purple."
        ))

        return menu

    @staticmethod
    def build_canvas_menu(
        parent,
        canvas_view,
        main_window
    ) -> QMenu:
        """
        Opened when right-clicking on empty space on the canvas.
        Quick insertion, note, paste + system menu submenus.
        """
        menu = QMenu(parent)
        style_beeref_menu(menu)

        menu.addAction("➕ Insert Images / PDF...\tCtrl+I", main_window.open_folder_or_files_dialog)
        menu.addAction("📝 Add Text Note\tCtrl+T", lambda: canvas_view.add_text_note())
        menu.addAction("📋 Paste\tCtrl+V", canvas_view.paste_from_clipboard)
        menu.addAction("🔍 Fit Scene (All)\t1, F", canvas_view.fit_all_items)
        menu.addSeparator()

        # Add system submenus from dock menu
        sys_menu = BeeRefContextMenu.build_dock_menu(parent, canvas_view, main_window)
        for act in sys_menu.actions():
            menu.addAction(act)

        return menu

    @staticmethod
    def build_menu(
        parent,
        canvas_view,
        main_window,
        clicked_item: Optional[CanvasRefItem] = None
    ) -> QMenu:
        """
        Master builder:
        - If clicked on an image -> returns build_image_menu (Green Circle)
        - If clicked on empty canvas -> returns build_canvas_menu
        """
        selected_items = [it for it in canvas_view.scene.selectedItems() if isinstance(it, CanvasRefItem)]
        if clicked_item or selected_items:
            target = clicked_item or selected_items[0]
            return BeeRefContextMenu.build_image_menu(parent, canvas_view, main_window, target)
        else:
            return BeeRefContextMenu.build_canvas_menu(parent, canvas_view, main_window)

    @staticmethod
    def show_opacity_dialog(canvas_view, items: List[CanvasRefItem]):
        if not items:
            items = [it for it in canvas_view.scene.selectedItems() if isinstance(it, CanvasRefItem)]
        if items:
            dlg = OpacitySliderDialog(canvas_view, items)
            dlg.exec()
