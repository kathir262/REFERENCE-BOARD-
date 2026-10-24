"""
RefPad Entrypoint.
Initializes QApplication, dark palette, handles CLI paths, and presents MainWindow.
"""
import sys
import os
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor, QPalette, QIcon
from PySide6.QtCore import Qt

from refpad.ui.main_window import MainWindow

def apply_artist_dark_theme(app: QApplication):
    """Sets a refined dark theme optimized for long digital painting sessions."""
    app.setStyle("Fusion")
    palette = QPalette()
    dark_color = QColor(18, 20, 24)
    text_color = QColor(240, 243, 246)

    palette.setColor(QPalette.ColorRole.Window, dark_color)
    palette.setColor(QPalette.ColorRole.WindowText, text_color)
    palette.setColor(QPalette.ColorRole.Base, QColor(14, 15, 18))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(24, 26, 32))
    palette.setColor(QPalette.ColorRole.ToolTipBase, text_color)
    palette.setColor(QPalette.ColorRole.ToolTipText, dark_color)
    palette.setColor(QPalette.ColorRole.Text, text_color)
    palette.setColor(QPalette.ColorRole.Button, QColor(28, 31, 38))
    palette.setColor(QPalette.ColorRole.ButtonText, text_color)
    palette.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    palette.setColor(QPalette.ColorRole.Link, QColor(126, 87, 246))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(126, 87, 246))
    palette.setColor(QPalette.ColorRole.HighlightedText, Qt.GlobalColor.white)
    app.setPalette(palette)

def main():
    app = QApplication(sys.argv)
    app.setApplicationName("RefPad")
    app.setOrganizationName("RefPadApp")

    apply_artist_dark_theme(app)

    window = MainWindow()
    window.show()

    # If user provided a folder or PDF path as CLI argument
    if len(sys.argv) > 1:
        target = sys.argv[1]
        if os.path.exists(target):
            window.handle_incoming_files([target])

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
