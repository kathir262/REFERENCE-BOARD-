"""Bringing pictures and PDFs into RefPad: file pickers, drag and drop, folders and the clipboard.

All decoding and saving happens on background threads; images appear on the board one by one as
they finish, so the window never freezes, even for big folders or long PDFs.
"""
import os
import re
from pathlib import Path

from PySide6.QtGui import QGuiApplication, QTransform

from refpad.core import images, pdf
from refpad.core.store import PRACTICE, PDF, BoardItem, Pose

BOARD_PAGE_SIDE = 1800
BOARD_FOLDER_MAX = 60
PRACTICE_FOLDER_MAX = 5000


def plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n:,} {word}s"


def is_pdf(path: str) -> bool:
    return path.lower().endswith(".pdf")


def split_paths(paths):
    """(images, pdfs, folders) from a list of dropped or picked paths."""
    imgs, pdfs, folders = [], [], []
    for p in paths:
        if os.path.isdir(p):
            folders.append(p)
        elif is_pdf(p):
            pdfs.append(p)
        elif images.is_image(p):
            imgs.append(p)
    return imgs, pdfs, folders


def _natural(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def scan_folder(folder: str, limit: int):
    """Pictures in a folder and its sub-folders, in natural order (img2 before img10)."""
    found = []
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted((d for d in dirs if not d.startswith((".", "$"))), key=_natural)
        for f in sorted(files, key=_natural):
            if not f.startswith((".", "~")) and images.is_image(f):
                found.append(os.path.join(root, f))
                if len(found) >= limit + 1:
                    return found
    return found


def item_image(item: BoardItem):
    """The board image with its flip, rotation and black & white applied (for copying)."""
    from refpad import paths
    img = images.cache.large(item.image) or images.read_image(str(paths.IMG / item.image))
    if img is None:
        return None
    if item.gray:
        img = images.grayscale(img)
    if item.rot or item.flip:
        t = QTransform()
        if item.flip:
            t.scale(-1, 1)
        t.rotate(90 * item.rot)
        img = img.transformed(t)
    return img


class Importer:
    def __init__(self, state, engine):
        self.state = state
        self.engine = engine

    # ------------------------------------------------------------------ board

    def images_to_board(self, paths):
        paths = list(paths)
        if paths:
            self._to_board(len(paths), lambda: (images.read_image(p) for p in paths))

    def qimages_to_board(self, imgs):
        imgs = [i for i in imgs if i is not None and not i.isNull()]
        if imgs:
            self._to_board(len(imgs), lambda: iter(imgs))

    def _to_board(self, total: int, source):
        st = self.state
        counts = {"ok": 0, "bad": 0}
        st.busy(f"Adding {plural(total, 'image')}…")

        def on_item(v):
            name, w, h = v
            item = BoardItem(name, w, h)
            item.fit_new()
            st.add_items([item])
            counts["ok"] += 1
            if counts["ok"] + counts["bad"] < total:
                st.busy(f"Adding images… {counts['ok'] + counts['bad']}/{total}")

        def on_bad(_):
            counts["bad"] += 1

        def work():
            for img in source():
                if img is None:
                    images.post(on_bad)
                    continue
                images.post(on_item, images.store_image(img))

        def finished(result):
            if isinstance(result, Exception):
                st.notify(f"Stopped adding images: {result}")
            elif counts["bad"] and counts["ok"]:
                st.notify(f"Added {plural(counts['ok'], 'image')} · couldn't open {counts['bad']}")
            elif counts["bad"]:
                st.notify("Couldn't open that picture" if counts["bad"] == 1 else f"Couldn't open those {counts['bad']} pictures")
            else:
                st.notify(f"Added {plural(counts['ok'], 'image')}")

        images.run_async(work, finished)

    def folder_to_board(self, folder: str):
        self._scan(folder, BOARD_FOLDER_MAX, self._folder_to_board)

    def _folder_to_board(self, found):
        if not found:
            return self.state.notify("No pictures in that folder")
        if len(found) > BOARD_FOLDER_MAX:
            found = found[:BOARD_FOLDER_MAX]
            self.state.notify(f"Adding the first {BOARD_FOLDER_MAX} pictures (use Practice for big folders)")
        self.images_to_board(found)

    def pdf_pages_to_board(self, path: str, pages):
        """Adds the chosen PDF pages to the board one at a time (light on memory); can be stopped."""
        pages = list(pages)
        if not pages:
            return
        st = self.state
        board = st.items        # the import stops if another board is opened meanwhile
        stop = {"now": False}
        done = {"added": 0}
        n = len(pages)

        def progress(k):
            st.task.emit(f"Adding pages to the board… {k}/{n}", lambda: stop.__setitem__("now", True))

        def step(k):
            if stop["now"] or st.items is not board:
                a = done["added"]
                return st.notify(f"Stopped · {plural(a, 'page')} added" if a else "Stopped")
            if k >= n:
                return st.notify(f"Added {plural(done['added'], 'page')} to the board")
            progress(k + 1)
            self.engine.render_once(path, pages[k], BOARD_PAGE_SIDE, lambda img: stored(k, img))

        def stored(k, img):
            if img is None:
                return step(k + 1)
            images.run_async(lambda: images.store_image(img), lambda v: added(k, v))

        def added(k, v):
            if isinstance(v, Exception):
                return st.notify(f"Stopped adding pages: {v}")
            if st.items is board and not stop["now"]:
                item = BoardItem(*v)
                item.fit_new()
                st.add_items([item])
                done["added"] += 1
            step(k + 1)

        step(0)

    def page_to_board(self, path: str, page: int):
        st = self.state
        st.busy(f"Adding page {page + 1} to the board…")

        def stored(v):
            if isinstance(v, Exception):
                return st.notify(f"Couldn't add the page: {v}")
            item = BoardItem(*v)
            item.fit_new()
            st.add_items([item])
            st.notify(f"Page {page + 1} added to the board")

        def rendered(img):
            if img is None:
                return st.notify("Couldn't render that page")
            images.run_async(lambda: images.store_image(img), stored)

        self.engine.render_once(path, page, BOARD_PAGE_SIDE, rendered)

    # ------------------------------------------------------------------ practice

    def images_to_practice(self, paths):
        poses = [Pose("file", os.path.abspath(p)) for p in paths if images.is_image(p)]
        if poses:
            self.state.add_practice(poses, jump=True)
            self.state.set_mode(PRACTICE)
            self.state.notify(f"Added {plural(len(poses), 'image')} to practice")

    def qimages_to_practice(self, imgs):
        imgs = [i for i in imgs if i is not None and not i.isNull()]
        if not imgs:
            return

        def done(result):
            if isinstance(result, Exception):
                return self.state.notify(f"Couldn't add the image: {result}")
            self.state.add_practice([Pose("img", name) for name, _, _ in result], jump=True)
            self.state.set_mode(PRACTICE)

        images.run_async(lambda: [images.store_image(i) for i in imgs], done)

    def board_to_practice(self, items):
        poses = [Pose("img", it.image) for it in items]
        if poses:
            self.state.add_practice(poses, jump=True)
            self.state.set_mode(PRACTICE)
            self.state.notify(f"Practising with {plural(len(poses), 'board image')}")

    def folder_to_practice(self, folder: str):
        def go(found):
            if not found:
                return self.state.notify("No pictures in that folder")
            if len(found) > PRACTICE_FOLDER_MAX:
                found = found[:PRACTICE_FOLDER_MAX]
            self.state.add_practice([Pose("file", p) for p in found], jump=True)
            self.state.set_mode(PRACTICE)
            self.state.notify(f"Practising with {plural(len(found), 'picture')} from “{Path(folder).name}”")

        self._scan(folder, PRACTICE_FOLDER_MAX, go)

    def pdf_to_practice(self, path: str, start: int = 0):
        def go(info):
            st = self.state
            key = pdf.norm(path)
            existing = [i for i, p in enumerate(st.practice) if p.kind == "pdf" and pdf.norm(p.ref) == key]
            if len(existing) == info.count:   # already in the list: just jump to the page
                st.go_to_pose(existing[min(start, info.count - 1)])
            else:
                first = len(st.practice)
                st.add_practice([Pose("pdf", path, i) for i in range(info.count)], jump=True)
                st.go_to_pose(first + min(start, info.count - 1))
            st.set_mode(PRACTICE)
            st.notify(f"Practising with “{Path(path).stem}” · {plural(info.count, 'page')}")

        self.with_info(path, go)

    # ------------------------------------------------------------------ PDF reader

    def pdf_to_reader(self, path: str):
        self.engine.forget(path)
        self.state.open_doc(os.path.abspath(path))
        self.state.set_mode(PDF)

    # ------------------------------------------------------------------ clipboard

    def paste(self, to_practice: bool = False, pick_pdf=None) -> bool:
        """Pastes pictures (or picture files) from the Windows clipboard. False if there was nothing usable."""
        clip = QGuiApplication.clipboard()
        md = clip.mimeData()
        if md is None:
            return False
        if md.hasUrls():
            local = [u.toLocalFile() for u in md.urls() if u.isLocalFile()]
            imgs, pdfs, folders = split_paths(local)
            if imgs:
                (self.images_to_practice if to_practice else self.images_to_board)(imgs)
            for p in pdfs:
                if pick_pdf:
                    pick_pdf(p)
            for f in folders:
                (self.folder_to_practice if to_practice else self.folder_to_board)(f)
            if imgs or pdfs or folders:
                return True
        if md.hasImage():
            img = clip.image()
            if not img.isNull():
                (self.qimages_to_practice if to_practice else self.qimages_to_board)([img])
                return True
        text = md.text().strip().strip('"') if md.hasText() else ""
        if text and len(text) < 1000 and os.path.exists(text):
            imgs, pdfs, folders = split_paths([text])
            if imgs:
                (self.images_to_practice if to_practice else self.images_to_board)(imgs)
                return True
            if pdfs and pick_pdf:
                pick_pdf(pdfs[0])
                return True
            if folders:
                (self.folder_to_practice if to_practice else self.folder_to_board)(folders[0])
                return True
        return False

    def copy_items(self, items) -> bool:
        if not items:
            return False
        img = item_image(items[-1])
        if img is None:
            return False
        QGuiApplication.clipboard().setImage(img)
        self.state.notify("Image copied")
        return True

    # ------------------------------------------------------------------ helpers

    def _scan(self, folder: str, limit: int, then):
        self.state.busy(f"Looking in “{Path(folder).name}”…")
        images.run_async(lambda: scan_folder(folder, limit),
                         lambda found: then([] if isinstance(found, Exception) else found))

    def with_info(self, path: str, then):
        """Calls then(info) once the PDF's page count is known; shows a message if it can't be opened."""
        def check(info):
            if info.error or info.count <= 0:
                self.state.notify(info.error or "This PDF has no pages.")
            else:
                then(info)

        info = self.engine.info(path)
        if info is not None and info.error:   # try again: the file may be back
            self.engine.forget(path)
            info = self.engine.info(path)
        if info is not None:
            return check(info)
        key = pdf.norm(path)
        self.state.busy(f"Opening “{Path(path).stem}”…")

        def ready(k):
            if k == key:
                self.engine.infoReady.disconnect(ready)
                check(self.engine.info(path))

        self.engine.infoReady.connect(ready)


importer = None


def init_importer(state, engine) -> Importer:
    global importer
    importer = Importer(state, engine)
    return importer
