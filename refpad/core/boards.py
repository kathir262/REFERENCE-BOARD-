"""Board files: keep each board (for example one per manga chapter) in its own .refpad file and switch between them.

A .refpad file is a zip with board.json and the pictures inside, so it can be moved to another folder or PC.
Also opens boards saved by RefPad 1.0 (JSON .refpad) and BeeRef (.bee).
Runs on a worker thread; nothing here touches the UI.
"""
import base64
import json
import os
import sqlite3
import zipfile
import zlib
from pathlib import Path

from PySide6.QtCore import QSize, QStandardPaths
from PySide6.QtGui import QImage

from refpad import paths
from refpad.core import images
from refpad.core.store import BoardItem, preview_name

EXT = ".refpad"
FORMAT = 1
FILTER = "RefPad boards (*.refpad);;BeeRef boards (*.bee);;All files (*.*)"


class BoardError(Exception):
    pass


def default_folder() -> Path:
    docs = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation) or str(Path.home())
    return Path(docs) / "RefPad Boards"


def is_board_file(path: str) -> bool:
    return path.lower().endswith((EXT, ".bee"))


# ----------------------------------------------------------------------------- saving

def write_board(path: str, items_json: list, view):
    """Writes the board to `path` (atomically: a half-written file never replaces a good one)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and not zipfile.is_zipfile(target):
        # An old RefPad 1.0 / other format file: keep it as a backup instead of overwriting it.
        backup = target.with_name(target.stem + ".old" + target.suffix)
        if not backup.exists():
            os.replace(target, backup)
    tmp = target.with_name(f"{target.name}.{os.urandom(3).hex()}.saving")   # unique: saves may overlap
    names = []
    for d in items_json:
        if d.get("img") and d["img"] not in names:
            names.append(d["img"])
    try:
        with zipfile.ZipFile(tmp, "w") as z:
            board = {"app": "RefPad", "format": FORMAT, "view": view,
                     "items": [dict(d, img="images/" + d["img"]) if d.get("img") else d for d in items_json]}
            z.writestr("board.json", json.dumps(board, indent=1), compress_type=zipfile.ZIP_DEFLATED)
            for name in names:
                for n in (name, preview_name(name)):
                    src = paths.IMG / n
                    if src.exists():   # pictures are already compressed: store them as they are
                        z.write(src, "images/" + n, compress_type=zipfile.ZIP_STORED)
                    elif n == name:
                        raise BoardError(f"A picture of this board is missing ({name}).")
        os.replace(tmp, target)
    except OSError as e:
        raise BoardError(f"Couldn't save the board: {e.strerror or e}") from e
    finally:
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass


# ----------------------------------------------------------------------------- opening

class Loaded:
    def __init__(self, items, view=None, missing=0, kind="refpad"):
        self.items = items
        self.view = view
        self.missing = missing
        self.kind = kind          # "refpad", "refpad-v1" or "bee"


def read_board(path: str) -> Loaded:
    if not os.path.exists(path):
        raise BoardError("That board file can't be found. It may have been moved or deleted.")
    try:
        if zipfile.is_zipfile(path):
            return _read_zip(path)
        with open(path, "rb") as f:
            head = f.read(16)
        if head.startswith(b"SQLite format 3"):
            return _read_bee(path)
        return _read_v1(path)
    except BoardError:
        raise
    except (OSError, ValueError, KeyError, zipfile.BadZipFile, sqlite3.Error) as e:
        raise BoardError("This board file is damaged or isn't a RefPad board.") from e


def _keep(name: str, data: bytes) -> str:
    """Puts a picture from a board file into RefPad's picture folder (reusing it if it's already there)."""
    dest = paths.IMG / name
    if dest.exists() and dest.stat().st_size == len(data):
        return name
    if dest.exists():   # same name, different picture: pick a new name
        stem, ext = os.path.splitext(name)
        name = f"{stem}{os.urandom(3).hex()}{ext}"
        dest = paths.IMG / name
    dest.write_bytes(data)
    return name


def _read_zip(path: str) -> Loaded:
    with zipfile.ZipFile(path) as z:
        board = json.loads(z.read("board.json").decode("utf-8"))
        if board.get("app") != "RefPad":
            raise BoardError("This zip file isn't a RefPad board.")
        if int(board.get("format", 1)) > FORMAT:
            raise BoardError("This board was saved by a newer RefPad. Please update RefPad to open it.")
        files = set(z.namelist())
        items, missing, done = [], 0, {}
        for d in board.get("items", []):
            arc = d.get("img", "")
            if not arc and d.get("note") is not None:   # a text note
                items.append(BoardItem.from_json(dict(d, img="")))
                continue
            if arc not in files:
                missing += 1
                continue
            if arc not in done:
                name = _keep(os.path.basename(arc), z.read(arc))
                prev_arc = "images/" + preview_name(os.path.basename(arc))
                if prev_arc in files:
                    pv = paths.IMG / preview_name(name)
                    if not pv.exists():
                        pv.write_bytes(z.read(prev_arc))
                done[arc] = name
            items.append(BoardItem.from_json(dict(d, img=done[arc])))
    view = board.get("view")
    return Loaded(items, view if isinstance(view, list) and len(view) == 3 else None, missing)


def _item_from(img: QImage, left: float, top: float, scale_px: float, rotation: float, flip: bool, gray: bool):
    """A board item from a picture placed the way older apps describe it (top-left corner and scale)."""
    w0, h0 = img.width(), img.height()
    name, w, h = images.store_image(img)
    it = BoardItem(name, w, h)
    it.scale = scale_px * w0 / max(1, w)   # the stored copy may be smaller than the original
    it.rot = round((rotation or 0) / 90) % 4
    it.flip, it.gray = bool(flip), bool(gray)
    it.cx = left + w0 * scale_px / 2
    it.cy = top + h0 * scale_px / 2
    return it


def _read_v1(path: str) -> Loaded:
    """Boards saved by RefPad 1.0 (JSON with links to the original pictures)."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    items, missing = [], 0
    base = Path(path).parent
    pdfs = {}
    for d in data.get("items", []):
        img = None
        if d.get("embedded_data"):
            img = QImage.fromData(base64.b64decode(d["embedded_data"]))
        src = d.get("file_path") or ""
        if (img is None or img.isNull()) and src:
            p = src if os.path.isabs(src) else str(base / src)
            if d.get("source_type") == "pdf":
                img = _render_pdf_page(pdfs, p, int(d.get("page_num", 0)))
            elif os.path.exists(p):
                img = images.read_image(p)
        if img is None or img.isNull():
            missing += 1
            continue
        items.append(_item_from(images.normalize(img), float(d.get("x", 0)), float(d.get("y", 0)),
                                float(d.get("scale", 1) or 1), d.get("rotation", 0), d.get("is_flipped_h"),
                                d.get("is_grayscale")))
    return Loaded(items, None, missing, "refpad-v1")


def _render_pdf_page(cache: dict, path: str, page: int):
    """RefPad 1.0 drew PDF pages at 2x (144 dpi); render them the same size so the layout matches."""
    from PySide6.QtPdf import QPdfDocument
    doc = cache.get(path)
    if doc is None:
        doc = QPdfDocument()
        if doc.load(path) != QPdfDocument.Error.None_:
            cache[path] = False
            return None
        cache[path] = doc
    if not doc or not 0 <= page < doc.pageCount():
        return None
    s = doc.pagePointSize(page)
    return doc.render(page, QSize(round(s.width() * 2), round(s.height() * 2)))


def _read_bee(path: str) -> Loaded:
    """Boards saved by BeeRef (.bee, an SQLite database with the pictures inside)."""
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        rows = con.execute("""SELECT items.x, items.y, items.scale, items.rotation, items.flip, items.data, sqlar.data
                              FROM items JOIN sqlar ON sqlar.item_id = items.id
                              ORDER BY items.z""").fetchall()
    finally:
        con.close()
    items, missing = [], 0
    for x, y, scale, rotation, flip, meta, blob in rows:
        img = QImage.fromData(blob) if blob else QImage()
        if img.isNull() and blob:   # SQLite archives may store data zlib-compressed
            try:
                img = QImage.fromData(zlib.decompress(blob))
            except zlib.error:
                pass
        if img.isNull():
            missing += 1
            continue
        try:
            gray = bool(json.loads(meta or "{}").get("grayscale"))
        except ValueError:
            gray = False
        items.append(_item_from(images.normalize(img), float(x or 0), float(y or 0), float(scale or 1),
                                rotation, (flip or 1) < 0, gray))
    return Loaded(items, None, missing, "bee")
