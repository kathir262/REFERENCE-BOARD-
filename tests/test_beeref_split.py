import sys
import os
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
sys.stdout.reconfigure(encoding='utf-8')

from PySide6.QtWidgets import QApplication
from refpad.ui.main_window import MainWindow
from refpad.ui.beeref_menu import BeeRefContextMenu, ImportDestinationDialog
from refpad.models.item import RefItem
from refpad.ui.canvas_item import CanvasRefItem
from refpad.ui.themes import THEMES

app = QApplication.instance() or QApplication(sys.argv)

class TestBeeRefSplit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.win = MainWindow()
        cls.win.resize(1000, 700)

    def test_themes_no_purple(self):
        for name, theme in THEMES.items():
            for attr in ['bg_dark', 'bg_card', 'accent', 'accent_hover', 'border']:
                val = getattr(theme, attr)
                self.assertNotIn('#7e57f6', val.lower(), f"Found purple in {name}.{attr}: {val}")

    def test_dock_menu_red_circle(self):
        dock_menu = BeeRefContextMenu.build_dock_menu(self.win.floating_dock, self.win.canvas_view, self.win)
        dock_titles = [act.text() for act in dock_menu.actions()]
        expected_dock = ['&File', '&Edit', '&View', '&Insert', '&Transform', '&Normalize', '&Arrange', '&Images', '&Practice Mode', '&Themes', '&Help']
        for exp in expected_dock:
            self.assertTrue(any(exp in t for t in dock_titles), f"Missing {exp} in dock menu!")

    def test_image_menu_green_circle(self):
        item = RefItem(source_type='file', name='test_ref')
        c_item = CanvasRefItem(item)
        self.win.canvas_view.scene.addItem(c_item)

        img_menu = BeeRefContextMenu.build_image_menu(self.win.canvas_view, self.win.canvas_view, self.win, c_item)
        img_titles = [act.text() for act in img_menu.actions()]
        expected_img = ['Flip Horizontally', 'Flip Vertically', 'Rotate 90° CW', 'Rotate 90° CCW', 'Grayscale', 'Invert Colors', 'Opacity', 'Reset Transforms']
        for exp in expected_img:
            self.assertTrue(any(exp in t for t in img_titles), f"Missing {exp} in image menu!")

    def test_mode_separation_import(self):
        # 1. Canvas destination only
        items_canvas = [RefItem(source_type='file', name=f'canvas_{i}') for i in range(3)]
        self.win.canvas_view.scene.clear()
        self.win.session_engine.items = []
        self.win._apply_loaded_items(items_canvas, destination='canvas')

        canvas_items = [it for it in self.win.canvas_view.scene.items() if isinstance(it, CanvasRefItem)]
        self.assertEqual(len(canvas_items), 3)
        self.assertEqual(len(self.win.session_engine.items), 0)

        # 2. Practice destination only
        items_practice = [RefItem(source_type='file', name=f'practice_{i}') for i in range(2)]
        self.win._apply_loaded_items(items_practice, destination='action')
        self.assertEqual(len(self.win.session_engine.items), 2)
        self.assertEqual(len([it for it in self.win.canvas_view.scene.items() if isinstance(it, CanvasRefItem)]), 3)

        # 3. Both destination
        items_both = [RefItem(source_type='file', name=f'both_{i}') for i in range(4)]
        self.win._apply_loaded_items(items_both, destination='both')
        self.assertEqual(len(self.win.session_engine.items), 4)
        self.assertEqual(len([it for it in self.win.canvas_view.scene.items() if isinstance(it, CanvasRefItem)]), 7)

    def test_canvas_menu(self):
        canvas_menu = BeeRefContextMenu.build_canvas_menu(self.win.canvas_view, self.win.canvas_view, self.win)
        canvas_titles = [act.text() for act in canvas_menu.actions()]
        self.assertTrue(any("Insert" in t for t in canvas_titles))
        self.assertTrue(any("Add Text Note" in t for t in canvas_titles))

if __name__ == '__main__':
    unittest.main()
