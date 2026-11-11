"""About RefPad (with the privacy policy and update settings) and the update dialog."""
import threading
import time

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices, QPixmap
from PySide6.QtWidgets import (QApplication, QCheckBox, QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton,
                               QTextBrowser, QVBoxLayout)

from refpad import __version__, paths
from refpad.core import images, updater
from refpad.settings import settings

PRIVACY_HTML = """
<h3 style="color:#F4F4F5">Privacy policy</h3>
<p><b>RefPad is free, with no ads, no accounts, no analytics and no tracking.</b></p>
<p><b>Your files stay on your computer.</b> Pictures you add to the board are copied into RefPad's own folder
(<i>%LOCALAPPDATA%\\RefPad</i>) so the board still works if the originals move. PDFs and practice folders are
opened from where they are. RefPad never uploads, shares or sells any of your files or data.</p>
<p><b>Update check.</b> The only time RefPad uses the internet is to look for a newer version of RefPad on
GitHub (github.com), at most once a day, and when you choose to download an update. This is an ordinary web
request: it contains no personal information and nothing about your files. Like any website, GitHub can see
your IP address; see GitHub's privacy statement. You can switch automatic checks off below; RefPad then only
connects when you click <i>Check for updates</i>.</p>
<p><b>Clipboard.</b> RefPad reads the clipboard only when you paste, and writes to it only when you copy.</p>
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
