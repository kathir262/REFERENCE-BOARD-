"""All of RefPad's data: the board, the practice list and the recent PDFs.

There is one shared instance, `state`, used by every view (the same idea as DataManager on Android).
Changes are saved automatically a moment after they happen, to %LOCALAPPDATA%\\RefPad\\board.
"""
import itertools
import json
import math
import os
import random
import time
import dataclasses
from dataclasses import dataclass, field
from pathlib import Path

from PySide6.QtCore import QObject, QRectF, QTimer, Signal

from refpad import paths

BOARD, PRACTICE, PDF = "board", "practice", "pdf"
MODES = (BOARD, PRACTICE, PDF)
MAX_DOCS = 10
GAP = 40.0
NEW_ITEM_SIDE = 480.0  # long side of a newly added image, in board units
INTERVALS = (30, 45, 60, 120, 180, 300, 600)

_ids = itertools.count(1)


NOTE_WIDTH = 320.0      # width of a new note, in board units
NOTE_FONT = 22.0        # note text size at scale 1, in board units
NOTE_PAD = 16.0


@dataclass(eq=False)
class BoardItem:
    image: str          # file name inside board/img ("" for a note)
    w: int              # pixel size of the stored image (for a note: its box size at scale 1)
    h: int
    cx: float = 0.0     # centre on the board
    cy: float = 0.0
    scale: float = 1.0
    rot: int = 0        # quarter turns clockwise
    flip: bool = False
    gray: bool = False
    id: int = field(default_factory=lambda: next(_ids))
    crop: tuple = None  # (x, y, w, h) of the picture that shows, in image pixels; None = all of it
    opacity: float = 1.0
    locked: bool = False
    grid: int = 0       # 0 = no grid, otherwise an N x N grid over the picture
    values: int = 0     # 0 = off, otherwise the picture in that many grey steps
    blur: bool = False  # "squint": blurred, to judge the big shapes
    note: str = ""      # a text note instead of a picture

    @property
    def is_note(self) -> bool:
        return not self.image

    @property
    def cw(self) -> float:
        """Width of the part that shows (cropped), before rotation, in image pixels."""
        return self.crop[2] if self.crop else self.w

    @property
    def ch(self) -> float:
        return self.crop[3] if self.crop else self.h

    @property
    def ew(self) -> float:
        return (self.ch if self.rot % 2 else self.cw) * self.scale

    @property
    def eh(self) -> float:
        return (self.cw if self.rot % 2 else self.ch) * self.scale

    def bounds(self) -> QRectF:
        ew, eh = self.ew, self.eh
        return QRectF(self.cx - ew / 2, self.cy - eh / 2, ew, eh)

    def move_to(self, left: float, top: float):
        self.cx = left + self.ew / 2
        self.cy = top + self.eh / 2

    def fit_new(self):
        self.scale = 1.0 if self.is_note else NEW_ITEM_SIDE / max(self.w, self.h, 1)

    def reset(self):
        self.rot, self.flip, self.gray = 0, False, False
        self.values, self.blur, self.opacity, self.grid = 0, False, 1.0, 0
        self.fit_new()

    def copy(self) -> "BoardItem":
        """A new item that looks the same (new id)."""
        d = dataclasses.replace(self)
        d.id = next(_ids)
        return d

    def to_json(self) -> dict:
        d = {"img": self.image, "w": self.w, "h": self.h, "cx": round(self.cx, 2), "cy": round(self.cy, 2),
             "s": round(self.scale, 5), "rot": self.rot, "flip": self.flip, "gray": self.gray}
        if self.crop:
            d["crop"] = [round(v, 1) for v in self.crop]
        if self.opacity < 1:
            d["opacity"] = round(self.opacity, 2)
        if self.locked:
            d["locked"] = True
        if self.grid:
            d["grid"] = self.grid
        if self.values:
            d["values"] = self.values
        if self.blur:
            d["blur"] = True
        if self.note:
            d["note"] = self.note
        return d

    @staticmethod
    def from_json(d: dict) -> "BoardItem":
        it = BoardItem(str(d.get("img") or ""), int(d["w"]), int(d["h"]), float(d.get("cx", 0)), float(d.get("cy", 0)),
                       float(d.get("s", 1)), int(d.get("rot", 0)) % 4, bool(d.get("flip")), bool(d.get("gray")))
        crop = d.get("crop")
        if isinstance(crop, list) and len(crop) == 4 and crop[2] > 0 and crop[3] > 0:
            it.crop = tuple(float(v) for v in crop)
        it.opacity = max(0.1, min(1.0, float(d.get("opacity", 1))))
        it.locked = bool(d.get("locked"))
        it.grid = max(0, min(12, int(d.get("grid", 0))))
        it.values = int(d.get("values", 0)) if int(d.get("values", 0)) in (0, 2, 3, 4, 5) else 0
        it.blur = bool(d.get("blur"))
        it.note = str(d.get("note") or "")
        return it


def note_item(text: str, cx: float, cy: float) -> BoardItem:
    it = BoardItem("", round(NOTE_WIDTH), 100, cx, cy, 1.0, note=text)
    size_note(it)
    return it


def size_note(it: BoardItem):
    """Sets a note's height to fit its text (width stays)."""
    from PySide6.QtGui import QFont, QFontMetricsF
    f = QFont("Segoe UI")
    f.setPixelSize(round(NOTE_FONT))
    fm = QFontMetricsF(f)
    inner = it.w - 2 * NOTE_PAD
    lines = 0
    for para in (it.note or " ").split("\n"):
        lines += max(1, math.ceil(fm.horizontalAdvance(para or " ") / max(1.0, inner * 0.97)))
    it.h = round(lines * fm.lineSpacing() + 2 * NOTE_PAD)


@dataclass(eq=False)
class Pose:
    kind: str      # "img" = copy stored by RefPad, "file" = picture on disk, "pdf" = page of a PDF
    ref: str       # image name, file path or PDF path
    page: int = 0

    @property
    def key(self) -> str:
        return f"{self.kind}:{self.ref}:{self.page}"

    def to_json(self) -> list:
        return [self.kind, self.ref, self.page]

    @staticmethod
    def from_json(v) -> "Pose":
        return Pose(str(v[0]), str(v[1]), int(v[2]) if len(v) > 2 else 0)


@dataclass(eq=False)
class Doc:
    path: str
    title: str
    pages: int = 0
    page: int = 0          # reading position: page index …
    offset: float = 0.0    # … and how far down that page (0..1)
    zoom: float = 1.0      # 1 = the page width fits the window
    spread: bool = False   # two pages side by side
    bookmarks: list = field(default_factory=list)   # page indexes

    @property
    def key(self) -> str:
        return os.path.normcase(os.path.abspath(self.path))

    def to_json(self) -> dict:
        d = {"path": self.path, "title": self.title, "pages": self.pages, "page": self.page,
             "offset": round(self.offset, 4), "zoom": round(self.zoom, 4)}
        if self.spread:
            d["spread"] = True
        if self.bookmarks:
            d["bm"] = sorted(set(self.bookmarks))
        return d

    @staticmethod
    def from_json(d: dict) -> "Doc":
        return Doc(str(d["path"]), str(d.get("title") or Path(d["path"]).stem), int(d.get("pages", 0)),
                   int(d.get("page", 0)), float(d.get("offset", 0)), float(d.get("zoom", 1)),
                   bool(d.get("spread")), [int(x) for x in d.get("bm", []) if isinstance(x, int)])


def doc_title(path: str) -> str:
    return Path(path).stem


class State(QObject):
    boardChanged = Signal()        # items added, removed or edited
    itemsMoved = Signal()          # an item is being dragged or resized (redraw only)
    itemsAdded = Signal(list)      # new items, so the board can bring them into view
    practiceChanged = Signal()     # the list of poses changed
    poseChanged = Signal()         # a different pose is showing
    docsChanged = Signal()         # recent PDFs changed (or the open one)
    modeChanged = Signal(str)
    boardFileChanged = Signal()    # the board's file name or its saved/unsaved state changed
    boardReplaced = Signal()       # a different board was opened or a new one started
    status = Signal(str, bool, object)   # message, busy, undo callback (or None)
    task = Signal(str, object)           # long job in progress: message, stop callback

    def __init__(self):
        super().__init__()
        self.items: list[BoardItem] = []
        self.practice: list[Pose] = []
        self.practice_index = 0
        self.docs: list[Doc] = []
        self.mode = BOARD
        self.interval = 60
        self.practice_flip = False
        self.practice_gray = False
        self.view = None               # saved board camera [cx, cy, zoom]
        self.board_path = None         # the .refpad file this board belongs to (None = untitled)
        self.board_dirty = False       # changed since it was last saved to that file
        self.board_suggested = ""      # name to offer when saving an untitled board
        self.screen_aspect = 16 / 9    # set by the board view, used to lay out rows
        self._save_timer = QTimer(self)
        self._save_timer.setSingleShot(True)
        self._save_timer.setInterval(800)
        self._save_timer.timeout.connect(self.save_now)
        self._undo: list = []          # board as it was before each change
        self._redo: list = []
        self._merge_key = None
        self._merge_until = 0.0
        self.load()
        self._shot = self._take()

    # ------------------------------------------------------------------ messages

    def notify(self, text: str, undo=None):
        self.status.emit(text, False, undo)

    def busy(self, text: str):
        self.status.emit(text, True, None)

    # ------------------------------------------------------------------ mode

    def set_mode(self, mode: str):
        if mode in MODES and mode != self.mode:
            self.mode = mode
            self.modeChanged.emit(mode)
            self.schedule_save()

    # ------------------------------------------------------------------ board

    def add_items(self, new: list, place: bool = True):
        if not new:
            return
        for item in new:
            if place:
                self._place(item)
            self.items.append(item)
        self._record("add")
        self._set_dirty(True)
        self.boardChanged.emit()
        self.itemsAdded.emit(list(new))
        self.schedule_save()

    def _row_width(self, area: float) -> float:
        return math.sqrt(area * self.screen_aspect) * 1.15

    def _place(self, item: BoardItem):
        """Puts a new image in the first free spot next to the others (rows grow with the board)."""
        if not self.items:
            item.move_to(0, 0)
            return
        w, h = item.ew, item.eh
        rects = [it.bounds() for it in self.items]
        min_left = min(r.left() for r in rects)
        max_bottom = max(r.bottom() for r in rects)
        area = sum(r.width() * r.height() for r in rects) + w * h
        row_limit = max(1200.0, w, self._row_width(area))
        candidates = []
        for r in rects:
            candidates.append((r.top(), r.right() + GAP))
            candidates.append((r.bottom() + GAP, r.left()))
        candidates.sort()
        half = GAP / 2
        for y, x in candidates:
            if x + w > min_left + row_limit:
                continue
            test = QRectF(x - half, y - half, w + GAP, h + GAP)
            if not any(r.intersects(test) for r in rects):
                item.move_to(x, y)
                return
        item.move_to(min_left, max_bottom + GAP)

    def auto_arrange(self):
        """Lays every image out in tidy rows that suit the window shape."""
        if not self.items:
            return
        area = sum(it.ew * it.eh for it in self.items)
        row_limit = max(max(it.ew for it in self.items), self._row_width(area))
        x = y = row_h = 0.0
        for it in self.items:
            if x > 0 and x + it.ew > row_limit:
                x, y, row_h = 0.0, y + row_h + GAP, 0.0
            it.move_to(x, y)
            x += it.ew + GAP
            row_h = max(row_h, it.eh)
        self.edited()

    def edited(self, merge: str = None):
        """Call after any finished change to the board: redraws, saves and can be undone."""
        self._record(merge)
        self._set_dirty(True)
        self.boardChanged.emit()
        self.schedule_save()

    # ------------------------------------------------------------------ undo / redo

    def _take(self) -> list:
        return [dataclasses.replace(it) for it in self.items]

    def _record(self, merge: str = None):
        """Remembers the board as it was before the change just made."""
        now = time.monotonic()
        if not (merge and merge == self._merge_key and now < self._merge_until):
            self._undo.append(self._shot)
            del self._undo[:-100]
        self._merge_key, self._merge_until = merge, now + 2.0
        self._redo.clear()
        self._shot = self._take()

    @property
    def can_undo(self) -> bool:
        return bool(self._undo)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo)

    def _restore(self, snap: list):
        self.items[:] = [dataclasses.replace(it) for it in snap]   # same list: running imports keep their board
        self._shot = self._take()
        self._merge_key = None
        self._set_dirty(True)
        self.boardChanged.emit()
        self.schedule_save()

    def undo(self):
        if not self._undo:
            return self.notify("Nothing to undo")
        self._redo.append(self._take())
        self._restore(self._undo.pop())

    def redo(self):
        if not self._redo:
            return self.notify("Nothing to redo")
        self._undo.append(self._take())
        self._restore(self._redo.pop())

    def _forget_history(self):
        self._undo.clear()
        self._redo.clear()
        self._merge_key = None
        self._shot = self._take()

    def moved(self):
        """Call while dragging or resizing: redraws without saving."""
        self.itemsMoved.emit()

    def remove_items(self, gone: list):
        gone = [it for it in gone if it in self.items]
        if not gone:
            return
        positions = sorted(((self.items.index(it), it) for it in gone), key=lambda p: p[0])
        for it in gone:
            self.items.remove(it)
        self.edited()

        def undo():
            for i, it in positions:
                self.items.insert(min(i, len(self.items)), it)
            self.edited()

        self.notify("Image deleted" if len(gone) == 1 else f"{len(gone)} images deleted", undo)

    def clear_board(self):
        if not self.items:
            return
        old = list(self.items)
        self.items.clear()
        self.edited()

        def undo():
            self.items[:0] = old
            self.edited()

        self.notify("Board cleared", undo)

    def bring_to_front(self, items: list):
        for it in items:
            if it in self.items:
                self.items.remove(it)
                self.items.append(it)
        self.edited()

    def send_to_back(self, items: list):
        for it in reversed(items):
            if it in self.items:
                self.items.remove(it)
                self.items.insert(0, it)
        self.edited()

    # ------------------------------------------------------------------ board files

    @property
    def board_name(self) -> str:
        if self.board_path:
            return Path(self.board_path).stem
        return self.board_suggested or "Untitled board"

    def _set_dirty(self, dirty: bool):
        if dirty != self.board_dirty:
            self.board_dirty = dirty
            self.boardFileChanged.emit()

    def mark_saved(self, path: str):
        self.board_path = path
        self.board_suggested = ""
        self.board_dirty = False
        self.boardFileChanged.emit()
        self.schedule_save()

    def replace_board(self, items: list, path=None, view=None, suggested: str = ""):
        """Shows a different board (opened from a file, or a new empty one)."""
        self.items = list(items)
        self._forget_history()
        self.board_path = path
        self.board_suggested = suggested
        self.board_dirty = False
        self.view = view
        self.boardChanged.emit()
        self.boardReplaced.emit()
        self.boardFileChanged.emit()
        self.schedule_save()

    # ------------------------------------------------------------------ practice

    @property
    def pose(self):
        if not self.practice:
            return None
        return self.practice[self.practice_index % len(self.practice)]

    def set_practice(self, poses: list, start: int = 0):
        self.practice = list(poses)
        self.practice_index = max(0, min(start, len(self.practice) - 1)) if self.practice else 0
        self.practiceChanged.emit()
        self.poseChanged.emit()
        self.schedule_save()

    def add_practice(self, poses: list, jump: bool = False):
        """Adds poses to the end of the list; with jump=True the first new pose shows straight away."""
        if not poses:
            return
        first_new = len(self.practice)
        self.practice.extend(poses)
        self.practiceChanged.emit()
        if jump or first_new == 0:
            self.practice_index = first_new
            self.poseChanged.emit()
        self.schedule_save()

    def clear_practice(self):
        if not self.practice:
            return
        old, old_index = list(self.practice), self.practice_index
        self.set_practice([])

        def undo():
            self.set_practice(old, old_index)

        self.notify("Practice list cleared", undo)

    def shuffle_practice(self):
        if len(self.practice) > 1:
            current = self.pose
            random.shuffle(self.practice)
            self.practice.remove(current)
            self.practice.insert(0, current)
            self.practice_index = 0
            self.practiceChanged.emit()
            self.poseChanged.emit()
            self.schedule_save()

    def go_to_pose(self, index: int):
        if not self.practice:
            return
        index %= len(self.practice)
        if index != self.practice_index:
            self.practice_index = index
            self.poseChanged.emit()
            self.schedule_save()

    def next_pose(self):
        self.go_to_pose(self.practice_index + 1)

    def prev_pose(self):
        self.go_to_pose(self.practice_index - 1)

    def drop_missing_pose(self, pose: Pose):
        """A pose whose file or PDF has gone away."""
        if pose in self.practice:
            i = self.practice.index(pose)
            self.practice.remove(pose)
            if self.practice_index > i or self.practice_index >= len(self.practice):
                self.practice_index = max(0, self.practice_index - 1) if self.practice_index > i else 0
            self.practiceChanged.emit()
            self.poseChanged.emit()
            self.schedule_save()

    # ------------------------------------------------------------------ PDFs

    @property
    def doc(self):
        """The PDF showing in the reader (the most recent one)."""
        return self.docs[0] if self.docs else None

    def find_doc(self, path: str):
        key = os.path.normcase(os.path.abspath(path))
        return next((d for d in self.docs if d.key == key), None)

    def open_doc(self, path: str, pages: int = 0) -> Doc:
        doc = self.find_doc(path) or Doc(path, doc_title(path), pages)
        if pages:
            doc.pages = pages
        if doc in self.docs:
            self.docs.remove(doc)
        self.docs.insert(0, doc)
        del self.docs[MAX_DOCS:]
        self.docsChanged.emit()
        self.schedule_save()
        return doc

    def remove_doc(self, doc: Doc):
        if doc not in self.docs:
            return
        i = self.docs.index(doc)
        self.docs.remove(doc)
        self.docsChanged.emit()
        self.schedule_save()

        def undo():
            if doc not in self.docs:
                self.docs.insert(min(i, len(self.docs)), doc)
                self.docsChanged.emit()
                self.schedule_save()

        self.notify(f"Removed “{doc.title}” from recent", undo)

    # ------------------------------------------------------------------ saving

    def schedule_save(self):
        self._save_timer.start()

    def save_now(self):
        self._save_timer.stop()
        data = {
            "version": 1,
            "mode": self.mode,
            "items": [it.to_json() for it in self.items],
            "practice": [p.to_json() for p in self.practice],
            "practice_index": self.practice_index,
            "interval": self.interval,
            "practice_flip": self.practice_flip,
            "practice_gray": self.practice_gray,
            "docs": [d.to_json() for d in self.docs],
            "view": self.view,
            "board_path": self.board_path,
            "board_dirty": self.board_dirty,
            "board_suggested": self.board_suggested,
        }
        tmp = paths.STATE_FILE.with_suffix(".tmp")
        try:
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(data, f, separators=(",", ":"))
            os.replace(tmp, paths.STATE_FILE)
        except OSError as e:
            self.notify(f"Couldn't save the board: {e.strerror or e}")

    def load(self):
        try:
            with open(paths.STATE_FILE, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError):
            data = {}
        img_dir = paths.IMG
        for d in data.get("items", []):
            try:
                it = BoardItem.from_json(d)
            except (KeyError, ValueError, TypeError):
                continue
            if it.is_note or (img_dir / it.image).exists():
                self.items.append(it)
        for v in data.get("practice", []):
            try:
                self.practice.append(Pose.from_json(v))
            except (IndexError, ValueError, TypeError):
                continue
        self.practice_index = int(data.get("practice_index", 0)) if self.practice else 0
        self.practice_index = max(0, min(self.practice_index, len(self.practice) - 1)) if self.practice else 0
        self.interval = int(data.get("interval", 60)) if int(data.get("interval", 60)) in INTERVALS else 60
        self.practice_flip = bool(data.get("practice_flip"))
        self.practice_gray = bool(data.get("practice_gray"))
        for d in data.get("docs", []):
            try:
                self.docs.append(Doc.from_json(d))
            except (KeyError, ValueError, TypeError):
                continue
        mode = data.get("mode", BOARD)
        self.mode = mode if mode in MODES else BOARD
        view = data.get("view")
        self.view = view if isinstance(view, list) and len(view) == 3 else None
        self.board_path = data.get("board_path") or None
        self.board_dirty = bool(data.get("board_dirty"))
        self.board_suggested = str(data.get("board_suggested") or "")
        self.delete_unused_images()

    def delete_unused_images(self):
        """Removes stored pictures that nothing uses any more (runs at start-up, after undo is no longer possible)."""
        used = {it.image for it in self.items if it.image} | {p.ref for p in self.practice if p.kind == "img"}
        keep = used | {preview_name(n) for n in used}
        try:
            for f in paths.IMG.iterdir():
                if f.name not in keep and f.is_file():
                    try:
                        f.unlink()
                    except OSError:
                        pass
        except OSError:
            pass


def preview_name(name: str) -> str:
    stem, ext = os.path.splitext(name)
    return f"{stem}_p{ext}"


state = None  # created by main() once the QApplication exists


def init_state() -> State:
    global state
    state = State()
    return state
