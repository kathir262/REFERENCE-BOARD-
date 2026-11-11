"""PDF pages on demand, rendered on one background thread with Qt's PDF engine (PDFium).

Views say which pages they want right now (`want`), most important first. Pages nobody wants any more
are dropped from the queue, so scrolling fast through a 1,000-page book never piles up work.
Rendered pages are kept in memory up to a budget, least recently used pages go first.
"""
import os
import threading
from collections import OrderedDict, namedtuple

from PySide6.QtCore import QObject, QRect, QSize, Qt, Signal
from PySide6.QtGui import QImage, QPainter
from PySide6.QtPdf import QPdfDocument, QPdfDocumentRenderOptions

# A rendered piece of a page: the whole page at `width` px wide (clip None),
# or the part (x, y, w, h) of the page rendered at `width` px wide (sharp zoomed-in detail).
Key = namedtuple("Key", "path page width clip")

MAX_PAGE_WIDTH = 2400   # wider than this, the viewer renders only the visible part
IDLE_CLOSE_SEC = 30


class PdfInfo:
    __slots__ = ("count", "sizes", "error")

    def __init__(self, count=0, sizes=None, error=""):
        self.count = count
        self.sizes = sizes or []   # page sizes in points: [(w, h), …]
        self.error = error

    def aspect(self, page: int) -> float:
        """Height / width of a page."""
        if 0 <= page < len(self.sizes):
            w, h = self.sizes[page]
            if w > 0:
                return h / w
        return 1.414


_ERRORS = {
    "FileNotFound": "The PDF file can't be found. It may have been moved or deleted.",
    "InvalidFileFormat": "This file isn't a PDF, or it is damaged.",
    "IncorrectPassword": "This PDF is password-protected.",
    "UnsupportedSecurityScheme": "This PDF is protected in a way RefPad can't open.",
}


def norm(path: str) -> str:
    return os.path.normcase(os.path.abspath(path))


def _flatten(img: QImage) -> QImage:
    """Pages with transparent areas are put on white paper (also the fastest format to draw)."""
    if not img.hasAlphaChannel():
        return img
    out = QImage(img.size(), QImage.Format.Format_RGB32)
    out.fill(Qt.GlobalColor.white)
    p = QPainter(out)
    p.drawImage(0, 0, img)
    p.end()
    return out


class PdfEngine(QObject):
    infoReady = Signal(str)       # normalised path
    pageReady = Signal(object)    # Key
    _done = Signal(object, object)

    def __init__(self, budget_mb: int = 256):
        super().__init__()
        self._cache = OrderedDict()   # Key -> QImage
        self._bytes = 0
        self._budget = budget_mb * 1024 * 1024
        self._infos: dict[str, PdfInfo] = {}
        self._info_pending: set[str] = set()
        self._wanted = OrderedDict()  # owner -> [Key] (most recent owner last)
        self._cv = threading.Condition()
        self._info_jobs: list = []
        self._render_jobs: list = []
        self._once_jobs: list = []
        self._inflight: set = set()
        self._failed: set = set()     # pieces that could not be rendered (not retried)
        self._done.connect(self._on_done)
        threading.Thread(target=self._run, name="refpad-pdf", daemon=True).start()

    # ------------------------------------------------------------------ public (UI thread)

    def info(self, path: str):
        """Page count and sizes, or None while the PDF is being opened."""
        key = norm(path)
        info = self._infos.get(key)
        if info is None and key not in self._info_pending:
            self._info_pending.add(key)
            with self._cv:
                self._info_jobs.append(("info", key))
                self._cv.notify()
        return info

    def forget(self, path: str):
        """Look at the file again next time (e.g. it was missing before)."""
        key = norm(path)
        self._infos.pop(key, None)
        self._failed = {k for k in self._failed if k.path != key}

    def page(self, key: Key):
        img = self._cache.get(key)
        if img is not None:
            self._cache.move_to_end(key)
        return img

    def best_page(self, path: str, page: int, width: int):
        """Closest whole-page render already in memory (used while the exact one renders)."""
        best, best_w = None, 0
        for k, img in self._cache.items():
            if k.path == path and k.page == page and k.clip is None:
                # Prefer the smallest render at least as wide as needed, else the widest.
                if best is None or (best_w < width and k.width > best_w) or (width <= k.width < best_w):
                    best, best_w = img, k.width
        return best

    def want(self, owner, keys):
        """The pieces `owner` needs now, most important first. Replaces its previous wish list."""
        self._wanted[owner] = list(keys)
        self._wanted.move_to_end(owner)
        self._rebuild()

    def release(self, owner):
        if self._wanted.pop(owner, None) is not None:
            self._rebuild()

    def render_once(self, path: str, page: int, long_side: int, callback):
        """A single page as a picture (for adding to the board); callback(QImage or None) on the UI thread."""
        with self._cv:
            self._once_jobs.append(("once", norm(path), page, long_side, callback))
            self._cv.notify()

    def trim(self):
        """Frees rendered pages that no view needs right now."""
        wanted = {k for keys in self._wanted.values() for k in keys}
        for k in [k for k in self._cache if k not in wanted]:
            self._bytes -= self._cache.pop(k).sizeInBytes()

    # ------------------------------------------------------------------ internals

    def _rebuild(self):
        jobs, seen = [], set()
        with self._cv:
            for owner in reversed(self._wanted):
                for k in self._wanted[owner]:
                    if k not in seen and k not in self._cache and k not in self._inflight and k not in self._failed:
                        seen.add(k)
                        jobs.append(("render", k))
            self._render_jobs = jobs
            if jobs:
                self._cv.notify()

    def _on_done(self, job, result):
        kind = job[0]
        if kind == "info":
            self._info_pending.discard(job[1])
            self._infos[job[1]] = result
            self.infoReady.emit(job[1])
        elif kind == "render":
            key = job[1]
            with self._cv:
                self._inflight.discard(key)
            if isinstance(result, QImage):
                old = self._cache.pop(key, None)
                if old is not None:
                    self._bytes -= old.sizeInBytes()
                self._cache[key] = result
                self._bytes += result.sizeInBytes()
                while self._bytes > self._budget and len(self._cache) > 1:
                    _, img = self._cache.popitem(last=False)
                    self._bytes -= img.sizeInBytes()
                self.pageReady.emit(key)
            else:
                self._failed.add(key)
        elif kind == "once":
            job[4](result if isinstance(result, QImage) else None)

    def _run(self):
        docs = OrderedDict()   # path -> QPdfDocument, owned by this thread
        while True:
            with self._cv:
                while not (self._info_jobs or self._render_jobs or self._once_jobs):
                    if not self._cv.wait(timeout=IDLE_CLOSE_SEC) and docs:
                        docs.clear()   # idle: close the files
                if self._info_jobs:
                    job = self._info_jobs.pop(0)
                elif self._render_jobs:
                    job = self._render_jobs.pop(0)
                    self._inflight.add(job[1])
                else:
                    job = self._once_jobs.pop(0)
            try:
                result = self._handle(job, docs)
            except Exception:
                result = None
            self._done.emit(job, result)

    def _open(self, docs, path):
        doc = docs.get(path)
        if doc is not None:
            docs.move_to_end(path)
            return doc, ""
        doc = QPdfDocument()
        err = doc.load(path)
        if err != QPdfDocument.Error.None_ or doc.pageCount() <= 0:
            name = getattr(err, "name", str(err))
            return None, _ERRORS.get(name, "This PDF can't be opened.")
        docs[path] = doc
        while len(docs) > 3:
            docs.popitem(last=False)
        return doc, ""

    def _handle(self, job, docs):
        kind = job[0]
        if kind == "info":
            doc, error = self._open(docs, job[1])
            if doc is None:
                return PdfInfo(error=error)
            sizes = []
            for i in range(doc.pageCount()):
                s = doc.pagePointSize(i)
                sizes.append((s.width(), s.height()))
            return PdfInfo(len(sizes), sizes)

        if kind == "render":
            key = job[1]
            doc, _ = self._open(docs, key.path)
            if doc is None or not 0 <= key.page < doc.pageCount():
                return None
            s = doc.pagePointSize(key.page)
            full = QSize(key.width, max(1, round(key.width * s.height() / max(s.width(), 1))))
            if key.clip is None:
                return _flatten(doc.render(key.page, full))
            x, y, w, h = key.clip
            opts = QPdfDocumentRenderOptions()
            opts.setScaledSize(full)
            opts.setScaledClipRect(QRect(x, y, w, h))
            return _flatten(doc.render(key.page, QSize(w, h), opts))

        # "once": a page as a picture whose long side is `long_side`
        _, path, page, long_side, _cb = job
        doc, _ = self._open(docs, path)
        if doc is None or not 0 <= page < doc.pageCount():
            return None
        s = doc.pagePointSize(page)
        if s.width() >= s.height():
            size = QSize(long_side, max(1, round(long_side * s.height() / max(s.width(), 1))))
        else:
            size = QSize(max(1, round(long_side * s.width() / max(s.height(), 1))), long_side)
        return _flatten(doc.render(page, size))


engine = None


def init_engine() -> PdfEngine:
    global engine
    engine = PdfEngine()
    return engine
