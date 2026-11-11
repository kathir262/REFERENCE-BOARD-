"""New / Open / Save / Save as / Recent boards.

A board with a file saves itself when you switch to another board or close RefPad, so you never lose work.
Only an untitled board with pictures asks whether to save it first.
"""
import os
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox

from refpad.core import boards, images
from refpad.core.store import BOARD
from refpad.settings import settings
from refpad.ui.widgets import header, item

MAX_RECENT = 10


class BoardFiles:
    def __init__(self, win, state):
        self.win = win
        self.state = state
        self._saving = False
        self._queue = []

    # ------------------------------------------------------------------ recent list

    def recent(self) -> list:
        out = [p for p in settings["recent_boards"] or [] if os.path.exists(p)]
        return out[:MAX_RECENT]

    def _remember(self, path: str):
        key = os.path.normcase(os.path.abspath(path))
        rest = [p for p in settings["recent_boards"] or [] if os.path.normcase(os.path.abspath(p)) != key]
        settings["recent_boards"] = [path] + rest[:MAX_RECENT - 1]

    # ------------------------------------------------------------------ saving

    def _snapshot(self):
        st = self.state
        b = self.win.board
        return [it.to_json() for it in st.items], [round(b.cx, 2), round(b.cy, 2), round(b.zoom, 5)]

    def save(self, then=None) -> bool:
        """Ctrl+S. Returns False when the user cancelled the Save dialog."""
        if not self.state.board_path:
            return self.save_as(then)
        self._write(self.state.board_path, then)
        return True

    def save_as(self, then=None) -> bool:
        st = self.state
        folder = Path(st.board_path).parent if st.board_path else boards.default_folder()
        folder.mkdir(parents=True, exist_ok=True)
        path, _ = QFileDialog.getSaveFileName(self.win, "Save board", str(folder / (st.board_name + boards.EXT)),
                                              "RefPad boards (*.refpad)")
        if not path:
            return False
        if not path.lower().endswith(boards.EXT):
            path += boards.EXT
        self._write(path, then)
        return True

    def _write(self, path: str, then=None):
        """Saves the board as it is right now; writes happen one after another on a worker thread."""
        items_json, view = self._snapshot()
        self._queue.append((path, items_json, view, then))
        if not self._saving:
            self._next()

    def _next(self):
        if not self._queue:
            return
        self._saving = True
        path, items_json, view, then = self._queue.pop(0)
        st = self.state
        st.busy(f"Saving “{Path(path).stem}”…")

        def done(result):
            self._saving = False
            if isinstance(result, Exception):
                st.notify(str(result))
            else:
                same = st.board_path and os.path.normcase(os.path.abspath(st.board_path)) == os.path.normcase(os.path.abspath(path))
                if same or st.board_path is None:
                    st.mark_saved(path)
                self._remember(path)
                st.notify(f"Saved “{Path(path).stem}”")
            if then:
                then()
            self._next()

        images.run_async(lambda: boards.write_board(path, items_json, view), done)

    def save_now_if_needed(self):
        """On close: a board that has a file is written straight away (it only takes a moment)."""
        st = self.state
        if st.board_path and st.board_dirty and st.items:
            items_json, view = self._snapshot()
            try:
                boards.write_board(st.board_path, items_json, view)
                st.mark_saved(st.board_path)
                self._remember(st.board_path)
            except boards.BoardError:
                pass   # the board itself is still kept by RefPad and comes back next time

    def _before_switch(self, then):
        """Makes sure the current board is safe before showing another one, then calls then()."""
        st = self.state
        if not st.items or not st.board_dirty:
            return then()
        if st.board_path:              # has a file: save it quietly
            return self._write(st.board_path, then)
        box = QMessageBox(self.win)
        box.setWindowTitle("Save this board?")
        box.setText(f"Save “{st.board_name}” before opening another board?")
        box.setInformativeText(f"It has {len(st.items)} picture{'s' if len(st.items) != 1 else ''}. "
                               "If you don't save it, it's gone once you switch.")
        save = box.addButton("Save…", QMessageBox.ButtonRole.AcceptRole)
        dont = box.addButton("Don't save", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save)
        box.exec()
        if box.clickedButton() is save:
            self.save_as(then)
        elif box.clickedButton() is dont:
            then()

    # ------------------------------------------------------------------ new / open

    def new_board(self):
        def go():
            self.state.replace_board([], None, None)
            self.state.set_mode(BOARD)
            self.state.notify("New board")
        self._before_switch(go)

    def open_dialog(self):
        folder = boards.default_folder()
        start = str(folder) if folder.exists() else ""
        path, _ = QFileDialog.getOpenFileName(self.win, "Open a board", start, boards.FILTER)
        if path:
            self.open(path)

    def open(self, path: str):
        st = self.state
        if st.board_path and os.path.normcase(os.path.abspath(st.board_path)) == os.path.normcase(os.path.abspath(path)):
            # The file of the board that is showing: bring back the saved version from disk.
            if st.items and not st.board_dirty:
                st.set_mode(BOARD)
                st.notify(f"“{Path(path).stem}” is already open")
                return
            if st.items and not self._confirm_revert(Path(path).stem):
                return
            return self._load(path)
        self._before_switch(lambda: self._load(path))

    def _confirm_revert(self, name: str) -> bool:
        box = QMessageBox(self.win)
        box.setWindowTitle("Open the saved board?")
        box.setText(f"Go back to the saved version of “{name}”?")
        box.setInformativeText("The changes you made since you last saved it will be lost.")
        ok = box.addButton("Open saved version", QMessageBox.ButtonRole.AcceptRole)
        box.addButton("Cancel", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(ok)
        box.exec()
        return box.clickedButton() is ok

    def _load(self, path: str):
        self.state.busy(f"Opening “{Path(path).stem}”…")
        images.run_async(lambda: boards.read_board(path), lambda res: self._opened(path, res))

    def _opened(self, path: str, res):
        st = self.state
        if isinstance(res, Exception):
            msg = str(res) if isinstance(res, boards.BoardError) else "This board file can't be opened."
            st.notify(msg)
            return
        own = res.kind == "refpad" or res.kind == "refpad-v1"
        st.replace_board(res.items, path if own else None, res.view, "" if own else Path(path).stem)
        if own:
            self._remember(path)
        st.set_mode(BOARD)
        n = len(res.items)
        extra = f" · {res.missing} picture{'s' if res.missing != 1 else ''} couldn't be found" if res.missing else ""
        older = " (from RefPad 1.0; it will be saved in the new format)" if res.kind == "refpad-v1" else ""
        if res.kind == "bee":
            older = " (from BeeRef; use Save as to keep it as a RefPad board)"
        st.notify(f"Opened “{Path(path).stem}” · {n} picture{'s' if n != 1 else ''}{extra}{older}")

    # ------------------------------------------------------------------ menu

    def fill_menu(self, m, with_header: bool = True):
        st = self.state
        if with_header:
            header(m, st.board_name + ("  •  not saved" if st.board_dirty and st.items else ""))
        item(m, "New board", "add", self.new_board, shortcut="Ctrl+N")
        item(m, "Open board…", "folder", self.open_dialog, shortcut="Ctrl+O")
        item(m, "Save board", "copy", self.save, enabled=bool(st.items) or bool(st.board_path), shortcut="Ctrl+S")
        item(m, "Save board as…", "copy", self.save_as, enabled=bool(st.items), shortcut="Ctrl+Shift+S")
        rec = self.recent()
        current = os.path.normcase(os.path.abspath(st.board_path)) if st.board_path else ""
        others = [p for p in rec if os.path.normcase(os.path.abspath(p)) != current]
        if others:
            header(m, "Recent boards")
            for p in others[:8]:
                item(m, Path(p).stem, "history", lambda p=p: self.open(p))
