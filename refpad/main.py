"""Starts RefPad for Windows.

Only one RefPad runs at a time: opening a picture or PDF with RefPad while it is already open sends the
file to the open window instead of starting a second copy.
"""
import getpass
import hashlib
import json
import os
import sys

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QColor, QPalette
from PySide6.QtNetwork import QLocalServer, QLocalSocket
from PySide6.QtWidgets import QApplication

from refpad import APP_NAME, __version__
from refpad.ui import theme


def _server_name() -> str:
    try:
        user = getpass.getuser()
    except Exception:
        user = "user"
    return "RefPad-" + hashlib.sha1(user.encode("utf-8", "replace")).hexdigest()[:12]


def _send_to_running(paths) -> bool:
    sock = QLocalSocket()
    sock.connectToServer(_server_name())
    if not sock.waitForConnected(400):
        return False
    sock.write(QByteArray(json.dumps({"open": paths}).encode("utf-8")))
    sock.waitForBytesWritten(1000)
    sock.disconnectFromServer()
    return True


def _palette() -> QPalette:
    p = QPalette()
    for role, c in ((QPalette.ColorRole.Window, theme.SURFACE), (QPalette.ColorRole.WindowText, theme.TEXT),
                    (QPalette.ColorRole.Base, theme.BG), (QPalette.ColorRole.AlternateBase, theme.RAISED),
                    (QPalette.ColorRole.Text, theme.TEXT), (QPalette.ColorRole.Button, theme.RAISED),
                    (QPalette.ColorRole.ButtonText, theme.TEXT), (QPalette.ColorRole.Highlight, theme.ACCENT),
                    (QPalette.ColorRole.HighlightedText, theme.ON_ACCENT), (QPalette.ColorRole.ToolTipBase, theme.RAISED),
                    (QPalette.ColorRole.ToolTipText, theme.TEXT), (QPalette.ColorRole.PlaceholderText, theme.MUTED)):
        p.setColor(role, QColor(c))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(theme.DISABLED))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(theme.DISABLED))
    return p


def _log_crashes():
    """Unexpected errors go to %LOCALAPPDATA%\\RefPad\\refpad.log instead of closing the app."""
    import traceback
    from refpad import paths
    log = paths.DATA / "refpad.log"

    def hook(kind, value, tb):
        try:
            if log.exists() and log.stat().st_size > 512 * 1024:
                log.unlink()
            with open(log, "a", encoding="utf-8") as f:
                f.write("".join(traceback.format_exception(kind, value, tb)) + "\n")
        except OSError:
            pass
        sys.__excepthook__(kind, value, tb)

    sys.excepthook = hook


def start(argv):
    """Creates the app and window. Returns (app, window, state), or (None, None, None) when the files were
    handed to an already running RefPad."""
    _log_crashes()
    sys.setswitchinterval(0.002)   # keep the window responsive while pictures load in the background
    if os.name == "nt":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("RefPad.RefPad")
        except Exception:
            pass
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication.instance() or QApplication(argv)
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(APP_NAME)
    app.setStyle("Fusion")
    app.setPalette(_palette())
    app.setFont(theme.app_font())
    app.setStyleSheet(theme.STYLE)

    flags = {a for a in argv[1:] if a.startswith("--")}
    files = [os.path.abspath(a) for a in argv[1:] if not a.startswith("--") and os.path.exists(a)]
    if _send_to_running(files):
        return None, None, None

    # Heavy modules only after we know this is the one running copy.
    from refpad.core import images, importer, pdf, store, updater
    from refpad.core.timer import PracticeTimer
    from refpad.ui.window import MainWindow

    images.init()
    images.init_cache()
    engine = pdf.init_engine()
    state = store.init_state()
    timer = PracticeTimer(state)
    imp = importer.init_importer(state, engine)
    updater.cleanup_leftovers()

    win = MainWindow(state, timer, engine, imp)
    win.show_initial()

    server = QLocalServer()
    QLocalServer.removeServer(_server_name())
    server.listen(_server_name())

    def on_connection():
        conn = server.nextPendingConnection()
        if conn is None:
            return

        def read():
            try:
                msg = json.loads(bytes(conn.readAll()).decode("utf-8"))
            except ValueError:
                return
            if win.isMinimized():
                win.showNormal()
            win.raise_()
            win.activateWindow()
            if msg.get("open"):
                win.open_paths(msg["open"])

        conn.readyRead.connect(read)
        conn.disconnected.connect(conn.deleteLater)

    server.newConnection.connect(on_connection)

    if files:
        QTimer.singleShot(250, lambda: win.open_paths(files))
    if "--updated" in flags:
        QTimer.singleShot(600, lambda: win.after_update(True))
    elif "--update-failed" in flags:
        QTimer.singleShot(600, lambda: win.after_update(False))

    win._server = server
    return app, win, state


def main() -> int:
    app, win, state = start(sys.argv)
    if app is None:
        return 0
    code = app.exec()
    state.save_now()
    return code


if __name__ == "__main__":
    sys.exit(main())
