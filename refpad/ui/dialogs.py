"""About RefPad (with the privacy policy and update settings) and the update dialog."""
import threading
import time

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (QApplication, QButtonGroup, QCheckBox, QDialog, QFrame, QHBoxLayout, QLabel,
                               QProgressBar, QPushButton, QScrollArea, QTextBrowser, QVBoxLayout, QWidget)

from refpad import __version__, paths
from refpad.core import images, updater
from refpad.settings import settings
from refpad.ui import theme

PRIVACY_HTML = """
<h3 style="color:#F4F4F5">Privacy policy</h3>
<p><b>RefPad is free, with no ads, no accounts, no analytics and no tracking.</b></p>
<p><b>Your files stay on your computer.</b> Pictures you add to the board are copied into RefPad's own folder
(<i>%LOCALAPPDATA%\\RefPad</i>) so the board still works if the originals move. PDFs and practice folders are
opened from where they are. RefPad never uploads, shares or sells any of your files or data.</p>
<p><b>Update check.</b> Apart from pictures you drag in from web pages (below), the only time RefPad uses the
internet is to look for a newer version of RefPad on GitHub (github.com), at most once a day, and when you choose
to download an update. This is an ordinary web request: it contains no personal information and nothing about your
files. Like any website, GitHub can see your IP address; see GitHub's privacy statement. You can switch automatic
checks off below; RefPad then only connects when you click <i>Check for updates</i>. The Microsoft Store version
never does this: the Store keeps it up to date.</p>
<p><b>Pictures from web pages.</b> When you drag a picture from a web page into RefPad, RefPad downloads that
picture from its web address, just like your browser would. Nothing else is sent.</p>
<p><b>Clipboard.</b> RefPad reads the clipboard only when you paste, and writes to it only when you copy
(including a colour you pick).</p>
<p><b>Practice history.</b> The poses and minutes you practise are counted on this PC only, to show your progress.
You can clear them in Practice history.</p>
<p><b>Removing your data.</b> Use <i>Clear board</i> and <i>Clear practice list</i>, or delete the folder
<i>%LOCALAPPDATA%\\RefPad</i>. Uninstalling RefPad means deleting its program folder.</p>
<p><b>Children.</b> RefPad collects no data from anyone, including children.</p>
<p>The full policy, which also covers RefPad for Android, is published with the project on GitHub.</p>
"""


def _title(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("DialogTitle")
    return lab


def _muted(text: str) -> QLabel:
    lab = QLabel(text)
    lab.setObjectName("Muted")
    lab.setWordWrap(True)
    return lab


def _button(text: str, kind: str = "secondary") -> QPushButton:
    b = QPushButton(text)
    b.setProperty("kind", kind)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    return b


class AboutDialog(QDialog):
    def __init__(self, parent, open_update):
        super().__init__(parent)
        self.open_update = open_update
        self.setWindowTitle("About RefPad")
        self.resize(560, 640)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(12)

        head = QHBoxLayout()
        logo = QLabel()
        logo.setPixmap(QPixmap(str(paths.resource("refpad/assets/icon-128.png"))).scaled(
            56, 56, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        head.addWidget(logo)
        col = QVBoxLayout()
        col.addWidget(_title(f"RefPad {__version__}"))
        col.addWidget(_muted("Reference board, timed gesture practice and PDF reader for artists."))
        head.addLayout(col, 1)
        lay.addLayout(head)

        self.status = _muted("")
        row = QHBoxLayout()
        self.check_btn = _button("Check for updates")
        self.check_btn.clicked.connect(self._check)
        row.addWidget(self.check_btn)
        row.addWidget(self.status, 1)
        lay.addLayout(row)
        self.auto = QCheckBox("Check for updates automatically (once a day)")
        self.auto.setChecked(bool(settings["auto_update"]))
        self.auto.toggled.connect(lambda on: settings.__setitem__("auto_update", on))
        lay.addWidget(self.auto)
        if paths.is_store_app():
            # The Microsoft Store updates this copy; RefPad itself never checks GitHub.
            self.check_btn.hide()
            self.auto.hide()
            self.status.setText("Updates come from the Microsoft Store.")

        text = QTextBrowser()
        text.setOpenExternalLinks(True)
        text.setHtml(PRIVACY_HTML)
        lay.addWidget(text, 1)

        bottom = QHBoxLayout()
        data_btn = _button("Open data folder")
        data_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.DATA))))
        site_btn = _button("Project page")
        site_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(updater.RELEASES_PAGE)))
        close = _button("Close", "primary")
        close.clicked.connect(self.accept)
        bottom.addWidget(data_btn)
        bottom.addWidget(site_btn)
        bottom.addStretch(1)
        bottom.addWidget(close)
        lay.addLayout(bottom)

    def _check(self):
        self.check_btn.setEnabled(False)
        self.status.setText("Checking…")

        def work():
            try:
                rel = updater.check()
                settings["last_update_check"] = time.time()
                return rel
            except updater.UpdateError as e:
                return e

        def done(result):
            if not self.isVisible():
                return
            self.check_btn.setEnabled(True)
            if isinstance(result, Exception):
                self.status.setText(str(result))
            elif result is None:
                self.status.setText(f"You have the latest version ({__version__}).")
            else:
                self.status.setText(f"RefPad {result.version_text} is available.")
                self.accept()
                self.open_update(result)

        images.run_async(work, done)


WEBSITE = "https://huashijie-pro.vercel.app/apps/refpad.html"


def _section(text: str) -> QLabel:
    lab = QLabel(text.upper())
    lab.setObjectName("Section")
    return lab


def _choices(options, current, on_pick) -> QWidget:
    """A row of round toggle buttons (like the Board / Practice / PDF tabs); exactly one is on."""
    row = QWidget()
    lay = QHBoxLayout(row)
    lay.setContentsMargins(0, 0, 0, 0)
    lay.setSpacing(6)
    group = QButtonGroup(row)
    group.setExclusive(True)
    for key, label in options:
        b = QPushButton(label)
        b.setCheckable(True)
        b.setChecked(key == current)
        b.setProperty("segment", True)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(lambda _=False, k=key: on_pick(k))
        group.addButton(b)
        lay.addWidget(b)
    lay.addStretch(1)
    return row


class SettingsDialog(QDialog):
    """Everything you set once, in one place (the same sections as the Android app's Settings screen)."""

    def __init__(self, win):
        super().__init__(win)
        self.win = win
        self.setWindowTitle("Settings")
        self.resize(560, 660)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 16)
        outer.setSpacing(10)
        scroll = QScrollArea(objectName="SettingsScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget(objectName="SettingsBody")
        lay = QVBoxLayout(body)
        lay.setContentsMargins(24, 20, 24, 8)
        lay.setSpacing(10)
        lay.addWidget(_title("Settings"))

        # Updates
        lay.addWidget(_section("Updates"))
        self.card = QFrame(objectName="UpdateCard")
        cl = QHBoxLayout(self.card)
        cl.setContentsMargins(14, 10, 10, 10)
        self.card_text = QLabel("")
        self.card_text.setWordWrap(True)
        self.card_btn = _button("Update now", "primary")
        self.card_btn.clicked.connect(self._open_update)
        cl.addWidget(self.card_text, 1)
        cl.addWidget(self.card_btn)
        lay.addWidget(self.card)
        self.status = _muted("")
        row = QHBoxLayout()
        self.check_btn = _button("Check for updates")
        self.check_btn.clicked.connect(self._check)
        row.addWidget(self.check_btn)
        row.addWidget(self.status, 1)
        lay.addLayout(row)
        self.auto = QCheckBox("Check for updates automatically (once a day)")
        self.auto.setChecked(bool(settings["auto_update"]))
        self.auto.toggled.connect(lambda on: settings.__setitem__("auto_update", on))
        lay.addWidget(self.auto)
        if paths.is_store_app():
            self.check_btn.hide()
            self.auto.hide()
            self.status.setText("The Microsoft Store keeps this copy of RefPad up to date.")
        else:
            self.status.setText(f"You have RefPad {__version__}.")
        self._show_card()

        # Board
        lay.addWidget(_section("Board and practice background"))
        lay.addWidget(_choices((("dark", "Dark"), ("grey", "Neutral grey"), ("light", "Light")),
                               settings["board_bg"], win.set_background))
        lay.addWidget(_muted("Neutral grey is best for judging colours and values."))

        # Tool bar
        lay.addWidget(_section("Tool bar"))
        lay.addWidget(_choices((("bottom", "Bottom"), ("left", "Left side"), ("right", "Right side")),
                               settings["toolbar_side"], win.set_toolbar_side))
        hide = QCheckBox("Fold the tool bar into a small round button")
        hide.setChecked(bool(settings["toolbar_hidden"]))
        hide.toggled.connect(win.set_toolbar_hidden)
        lay.addWidget(hide)
        lay.addWidget(_muted("You can also drag the bar by its handle to the left, the right or the bottom. "
                             "Right-click the round button for all the tools."))

        # Practice
        lay.addWidget(_section("Practice"))
        chime = QCheckBox("Soft chime when the pose changes")
        chime.setChecked(win.a_chime.isChecked())
        chime.toggled.connect(lambda on: (win.a_chime.setChecked(on), win.toggle_chime()))
        lay.addWidget(chime)
        memory = QCheckBox("Memory mode: each pose hides after its time, then you draw it from memory")
        memory.setChecked(win.timer.memory)
        memory.toggled.connect(lambda on: on != win.timer.memory and win.toggle_memory())
        lay.addWidget(memory)
        hist = _button("Practice history")
        hist.clicked.connect(win.show_history)
        lay.addWidget(hist, 0, Qt.AlignmentFlag.AlignLeft)

        # About
        lay.addWidget(_section("About"))
        lay.addWidget(_muted(f"RefPad {__version__} · reference board, timed gesture practice and PDF reader for artists. "
                             "Free, no ads, no accounts, no tracking."))
        about_row = QHBoxLayout()
        for text, fn in (("About and privacy", self._about),
                         ("Open data folder", lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.DATA)))),
                         ("Website", lambda: QDesktopServices.openUrl(QUrl(WEBSITE)))):
            b = _button(text)
            b.clicked.connect(fn)
            about_row.addWidget(b)
        about_row.addStretch(1)
        lay.addLayout(about_row)
        lay.addStretch(1)
        scroll.setWidget(body)
        outer.addWidget(scroll, 1)

        bottom = QHBoxLayout()
        bottom.setContentsMargins(24, 0, 24, 0)
        bottom.addStretch(1)
        close = _button("Close", "primary")
        close.clicked.connect(self.accept)
        bottom.addWidget(close)
        outer.addLayout(bottom)

    def _show_card(self):
        rel = self.win.update_rel
        self.card.setVisible(rel is not None)
        if rel is not None:
            self.card_text.setText(f"<b>RefPad {rel.version_text} is available.</b><br>"
                                   "Your board, practice list and PDFs are kept.")

    def _open_update(self):
        rel = self.win.update_rel
        if rel is not None:
            self.accept()
            self.win.open_update(rel)

    def _about(self):
        self.accept()
        self.win.show_about()

    def _check(self):
        self.check_btn.setEnabled(False)
        self.status.setText("Checking…")

        def work():
            try:
                rel = updater.check()
                settings["last_update_check"] = time.time()
                return rel
            except updater.UpdateError as e:
                return e

        def done(result):
            if not self.isVisible():
                return
            self.check_btn.setEnabled(True)
            if isinstance(result, Exception):
                self.status.setText(str(result))
            elif result is None:
                self.win.set_update_available(None)
                self.status.setText(f"You have the latest version ({__version__}).")
            else:
                self.win.set_update_available(result)
                self.status.setText(f"RefPad {result.version_text} is ready to install.")
            self._show_card()

        images.run_async(work, done)


class UpdateDialog(QDialog):
    def __init__(self, parent, rel: updater.Release, before_restart):
        super().__init__(parent)
        self.rel = rel
        self.before_restart = before_restart
        self._cancel = False
        self._new_dir = None
        self.setWindowTitle("Update RefPad")
        self.resize(520, 460)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(12)
        lay.addWidget(_title(f"RefPad {rel.version_text} is available"))
        size = f" · {rel.zip_size / 1024 / 1024:.0f} MB download" if rel.zip_size else ""
        lay.addWidget(_muted(f"You have version {__version__}{size}. Your board, practice list and PDFs are kept."))
        notes = QTextBrowser()
        notes.setOpenExternalLinks(True)
        notes.setMarkdown(rel.notes.strip() or "No release notes.")
        lay.addWidget(notes, 1)
        self.bar = QProgressBar()
        self.bar.setRange(0, 1000)
        self.bar.hide()
        lay.addWidget(self.bar)
        self.msg = _muted("")
        self.msg.hide()
        lay.addWidget(self.msg)

        row = QHBoxLayout()
        self.skip = _button("Skip this version")
        self.skip.clicked.connect(self._skip)
        self.later = _button("Later")
        self.later.clicked.connect(self._later)
        self.go = _button("Update now", "primary")
        self.go.clicked.connect(self._go)
        row.addWidget(self.skip)
        row.addStretch(1)
        row.addWidget(self.later)
        row.addWidget(self.go)
        lay.addLayout(row)
        self.self_update = updater.can_self_update()
        if not self.self_update:
            self.go.setText("Open download page")

    def _skip(self):
        settings["skip_version"] = self.rel.version_text
        self.reject()

    def _later(self):
        self._cancel = True
        self.reject()

    def _say(self, text: str):
        self.msg.setText(text)
        self.msg.show()

    def _go(self):
        if self._new_dir is not None:
            self.before_restart()
            updater.install_and_restart(self._new_dir)
            QApplication.instance().quit()
            return
        if not self.self_update:
            QDesktopServices.openUrl(QUrl(self.rel.page_url))
            self.accept()
            return
        self.go.setEnabled(False)
        self.skip.setEnabled(False)
        self.later.setText("Cancel")
        self.bar.setValue(0)
        self.bar.show()
        self._say("Downloading…")
        last = [0.0]

        def progress(got, total):
            now = time.monotonic()
            if now - last[0] > 0.08:
                last[0] = now
                images.post(self._progress, (got, total))

        def work():
            try:
                return updater.download(self.rel, progress, lambda: self._cancel)
            except updater.UpdateError as e:
                return e

        def done(result):
            if self._cancel:
                return
            self.later.setText("Later")
            if isinstance(result, Exception):
                self.bar.hide()
                self.go.setEnabled(True)
                self.skip.setEnabled(True)
                self.go.setText("Try again")
                self._say(str(result))
                return
            self._new_dir = result
            self.bar.setValue(1000)
            self._say("Downloaded and verified. RefPad will close and open again in a few seconds.")
            self.go.setText("Restart and update")
            self.go.setEnabled(True)

        threading.Thread(target=lambda: images.post(done, work()), daemon=True).start()

    def _progress(self, v):
        got, total = v
        if total:
            self.bar.setValue(round(1000 * got / total))
            self._say(f"Downloading… {got / 1024 / 1024:.1f} of {total / 1024 / 1024:.1f} MB")

    def reject(self):
        self._cancel = True
        super().reject()


class _Bars(QWidget):
    """Minutes practised on each of the last 14 days."""

    def __init__(self, days):
        super().__init__()
        self.days = days
        self.setMinimumHeight(170)

    def paintEvent(self, e):
        from PySide6.QtCore import QRectF
        from PySide6.QtGui import QPainter
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        n = len(self.days)
        w, h = self.width(), self.height()
        top, bottom = 20, 34
        peak = max([d["seconds"] for _, d in self.days] + [60])
        slot = w / max(1, n)
        f = p.font()
        f.setPixelSize(11)
        p.setFont(f)
        for i, (day, d) in enumerate(self.days):
            mins = d["seconds"] / 60
            bh = (h - top - bottom) * d["seconds"] / peak
            x = i * slot + slot * 0.18
            bw = slot * 0.64
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(theme.color(theme.ACCENT if i == n - 1 else theme.ACCENT_PRESSED, 1.0 if d["seconds"] else 0.25))
            p.drawRoundedRect(QRectF(x, h - bottom - max(3, bh), bw, max(3, bh)), 4, 4)
            p.setPen(theme.color(theme.TEXT_2))
            if mins >= 1:
                p.drawText(QRectF(i * slot, h - bottom - bh - 18, slot, 16), Qt.AlignmentFlag.AlignCenter, f"{mins:.0f}")
            label = "Today" if i == n - 1 else day.strftime("%a")[:2]
            p.setPen(theme.color(theme.MUTED if i < n - 1 else theme.TEXT))
            p.drawText(QRectF(i * slot - 6, h - bottom + 6, slot + 12, 16), Qt.AlignmentFlag.AlignCenter, label)


class HistoryDialog(QDialog):
    def __init__(self, parent):
        from refpad.core import history
        super().__init__(parent)
        self.setWindowTitle("Practice history")
        self.resize(560, 420)
        s = history.summary()
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 22, 24, 20)
        lay.setSpacing(14)
        lay.addWidget(_title("Practice history"))

        def fmt(sec):
            m = round(sec / 60)
            return f"{m // 60} h {m % 60} min" if m >= 60 else f"{m} min"

        cards = QHBoxLayout()
        for label, big, small in (("Today", f"{s['today']['poses']} poses", fmt(s["today"]["seconds"])),
                                  ("Last 7 days", f"{s['week']['poses']} poses", fmt(s["week"]["seconds"])),
                                  ("Streak", f"{s['streak']} day{'s' if s['streak'] != 1 else ''}", "in a row"),
                                  ("All time", f"{s['total']['poses']} poses", fmt(s["total"]["seconds"]))):
            box = QVBoxLayout()
            a = _muted(label)
            b = QLabel(big)
            b.setStyleSheet(f"font-size: 19px; font-weight: 700; color: {theme.ACCENT};")
            c = _muted(small)
            for w in (a, b, c):
                box.addWidget(w)
            cards.addLayout(box, 1)
        lay.addLayout(cards)
        lay.addWidget(_muted("Minutes practised per day"))
        lay.addWidget(_Bars(s["days"]), 1)
        lay.addWidget(_muted("A pose counts once you have spent at least half its time on it. "
                             "Your history stays on this PC."))
        row = QHBoxLayout()
        clear = _button("Clear history")
        clear.clicked.connect(self._clear)
        close = _button("Close", "primary")
        close.clicked.connect(self.accept)
        row.addWidget(clear)
        row.addStretch(1)
        row.addWidget(close)
        lay.addLayout(row)

    def _clear(self):
        from PySide6.QtWidgets import QMessageBox
        from refpad.core import history
        if QMessageBox.question(self, "Clear history", "Delete your practice history? This can't be undone.") == \
                QMessageBox.StandardButton.Yes:
            history.clear()
            self.accept()
