"""Reading, storing and caching pictures, with all heavy work on background threads.

Every board image is stored twice: a copy capped at 2560 px and a 512 px preview. The board draws the
preview while an image is small on screen and only loads the large copy for images you zoom into, so
even a board with hundreds of pictures stays light on memory.
"""
import os
import uuid
from collections import OrderedDict

from PySide6.QtCore import QObject, QThreadPool, Qt, Signal
from PySide6.QtGui import QImage, QImageReader

from refpad import paths
from refpad.core.store import preview_name

MAX_SIDE = 2560
PREVIEW_SIDE = 512
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".jfif", ".webp", ".bmp", ".gif", ".tif", ".tiff", ".tga"}

pool = QThreadPool()
pool.setMaxThreadCount(max(2, min(3, (os.cpu_count() or 4) // 2)))
pool.setExpiryTimeout(20000)


class _Relay(QObject):
    done = Signal(object, object)

    def __init__(self):
        super().__init__()
        self.done.connect(lambda fn, value: fn(value))


_relay = None


def init():
    """Call once on the UI thread after the QApplication exists."""
    global _relay
    if _relay is None:
        _relay = _Relay()


def post(fn, value=None):
    """From any thread: run fn(value) on the UI thread."""
    _relay.done.emit(fn, value)


def run_async(fn, on_done=None):
    """Runs fn() on a worker thread, then on_done(result) on the UI thread.
    If fn raises, on_done receives the exception instead of a result."""
    def job():
        try:
            result = fn()
        except Exception as e:  # reported to the caller, never crashes the app
            result = e
        if on_done is not None:
            _relay.done.emit(on_done, result)

    pool.start(job)


def is_image(path: str) -> bool:
    return os.path.splitext(path)[1].lower() in IMAGE_EXTS


def normalize(img: QImage) -> QImage:
    """The pixel formats Qt draws fastest."""
    fmt = QImage.Format.Format_ARGB32_Premultiplied if img.hasAlphaChannel() else QImage.Format.Format_RGB32
    return img if img.format() == fmt else img.convertToFormat(fmt)


def fit(img: QImage, side: int) -> QImage:
    if max(img.width(), img.height()) <= side:
        return img
    return img.scaled(side, side, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation)


def read_image(path: str, max_side: int = MAX_SIDE):
    """Decodes a picture file (honouring camera rotation); huge photos are shrunk while reading. None if unreadable."""
    reader = QImageReader(path)
    reader.setAutoTransform(True)
    reader.setAllocationLimit(1024)
    size = reader.size()
    if size.isValid() and max(size.width(), size.height()) > max_side * 1.25:
        reader.setScaledSize(size.scaled(max_side, max_side, Qt.AspectRatioMode.KeepAspectRatio))
    img = reader.read()
    if img.isNull():
        return None
    return normalize(fit(img, max_side))


def grayscale(img: QImage) -> QImage:
    return normalize(img.convertToFormat(QImage.Format.Format_Grayscale8))


def store_image(img: QImage):
    """Saves a picture into the board folder (worker thread). Returns (name, width, height)."""
    img = normalize(fit(img, MAX_SIDE))
    alpha = img.hasAlphaChannel()
    name = uuid.uuid4().hex[:16] + (".png" if alpha else ".jpg")
    if not img.save(str(paths.IMG / name), None, -1 if alpha else 92):
        raise OSError("Couldn't save the picture (is the disk full?)")
    fit(img, PREVIEW_SIDE).save(str(paths.IMG / preview_name(name)), None, -1 if alpha else 85)
    return name, img.width(), img.height()


def _load_preview(name: str):
    p = paths.IMG / preview_name(name)
    img = read_image(str(p), PREVIEW_SIDE) if p.exists() else None
    if img is None:  # preview missing: make it again from the large copy
        big = read_image(str(paths.IMG / name))
        if big is None:
            return None
        img = normalize(fit(big, PREVIEW_SIDE))
        img.save(str(p), None, -1 if img.hasAlphaChannel() else 85)
    return img


class ImageCache(QObject):
    """Pictures in memory. Previews stay loaded; large copies are kept within a memory budget."""

    changed = Signal()

    def __init__(self, budget_mb: int = 480):
        super().__init__()
        self._previews: dict[str, QImage] = {}
        self._gray_previews: dict[str, QImage] = {}
        self._large = OrderedDict()      # key -> QImage, least recently used first
        self._bytes = 0
        self._budget = budget_mb * 1024 * 1024
        self._pending: set[str] = set()
        self._failed: set[str] = set()

    # Board images (stored copies) -------------------------------------------

    def preview(self, name: str, gray: bool = False):
        img = self._previews.get(name)
        if img is None:
            self._request("p:" + name, lambda: _load_preview(name))
            return None
        if gray:
            g = self._gray_previews.get(name)
            if g is None:
                g = self._gray_previews[name] = grayscale(img)
            return g
        return img

    def large(self, name: str):
        """The 2560 px copy of a board image, or None while it loads."""
        return self._get("img:" + name, lambda: read_image(str(paths.IMG / name)))

    # Pictures on disk (practice from a folder) -------------------------------

    def file(self, path: str):
        return self._get("file:" + path, lambda: read_image(path))

    def failed(self, kind: str, ref: str) -> bool:
        return f"{kind}:{ref}" in self._failed

    # ---------------------------------------------------------------------------

    def _get(self, key, loader):
        img = self._large.get(key)
        if img is not None:
            self._large.move_to_end(key)
            return img
        self._request(key, loader)
        return None

    def _request(self, key, loader):
        if key in self._pending or key in self._failed:
            return
        self._pending.add(key)
        run_async(loader, lambda img, key=key: self._loaded(key, img))

    def _loaded(self, key, img):
        self._pending.discard(key)
        if not isinstance(img, QImage) or img.isNull():
            self._failed.add(key)
            self.changed.emit()
            return
        if key.startswith("p:"):
            self._previews[key[2:]] = img
        else:
            self._large[key] = img
            self._bytes += img.sizeInBytes()
            while self._bytes > self._budget and len(self._large) > 1:
                _, old = self._large.popitem(last=False)
                self._bytes -= old.sizeInBytes()
        self.changed.emit()

    def trim(self):
        """Frees the large copies (e.g. when the window is minimised)."""
        self._large.clear()
        self._bytes = 0
        self._gray_previews.clear()


cache = None


def init_cache() -> ImageCache:
    global cache
    cache = ImageCache()
    return cache
