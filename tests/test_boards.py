"""Board files (.refpad), old RefPad 1.0 boards, BeeRef boards, and the PDF page-number box."""
import base64
import json
import sqlite3
import zipfile

import pytest
from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtGui import QColor, QImage

from refpad import paths
from refpad.core import boards, images
from refpad.ui.pdf_pages import pages_text, parse_pages


def _picture(w=300, h=200, color="#c0392b") -> QImage:
    img = QImage(w, h, QImage.Format.Format_RGB32)
    img.fill(QColor(color))
    return img


def _png_bytes(img: QImage) -> bytes:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    img.save(buf, "PNG")
    return bytes(buf.data())


def test_save_and_open_board_file(app, tmp_path):
    from refpad.core.store import BoardItem
    items = []
    for i, c in enumerate(("#c0392b", "#27ae60", "#2980b9")):
        name, w, h = images.store_image(_picture(400 + i * 50, 300, c))
        it = BoardItem(name, w, h, cx=i * 500.0, cy=10.0, scale=0.5 + i, rot=i, flip=i == 1, gray=i == 2)
        items.append(it)
    items.append(BoardItem(items[0].image, items[0].w, items[0].h, cx=-300))   # same picture twice
    path = tmp_path / "Manga ch3.refpad"
    boards.write_board(str(path), [it.to_json() for it in items], [1.0, 2.0, 0.75])

    with zipfile.ZipFile(path) as z:
        names = z.namelist()
    assert "board.json" in names and len([n for n in names if n.startswith("images/") and "_p." not in n]) == 3

    # Pretend this is another PC: RefPad's picture folder doesn't have these pictures.
    for it in items:
        (paths.IMG / it.image).unlink(missing_ok=True)
    loaded = boards.read_board(str(path))
    assert loaded.kind == "refpad" and loaded.missing == 0 and loaded.view == [1.0, 2.0, 0.75]
    assert [(i.w, i.h, i.cx, i.cy, i.rot, i.flip, i.gray) for i in loaded.items] == \
           [(i.w, i.h, i.cx, i.cy, i.rot, i.flip, i.gray) for i in items]
    assert all((paths.IMG / i.image).exists() for i in loaded.items)
    assert loaded.items[0].image == loaded.items[3].image


def _wait(app, cond, timeout=10):
    import time
    end = time.time() + timeout
    while not cond() and time.time() < end:
        app.processEvents()
        time.sleep(0.01)
    return cond()


def test_opening_the_boards_own_file_brings_back_the_saved_version(app, tmp_path):
    """The board was emptied (or changed) and you open its file again: you get the saved board back."""
    from refpad.core.store import BoardItem, State
    from refpad.ui.board_files import BoardFiles
    names = [images.store_image(_picture(200 + i * 10, 150))[0] for i in range(2)]
    path = tmp_path / "Chapter 1.refpad"
    boards.write_board(str(path), [BoardItem(n, 200, 150, cx=i * 300.0).to_json() for i, n in enumerate(names)], None)
    st = State()
    st.items.clear()
    files = BoardFiles(None, st)
    files.open(str(path))
    assert _wait(app, lambda: len(st.items) == 2) and st.board_path == str(path)
    st.clear_board()
    assert st.items == [] and st.board_dirty
    files.open(str(path))                       # used to do nothing here
    assert _wait(app, lambda: len(st.items) == 2) and not st.board_dirty
    st.items[0].flip = True
    st.edited()
    files._confirm_revert = lambda name: False  # "Cancel": keep the change
    files.open(str(path))
    app.processEvents()
    assert st.items[0].flip and st.board_dirty
    files._confirm_revert = lambda name: True   # "Open saved version"
    files.open(str(path))
    assert _wait(app, lambda: not st.board_dirty) and not st.items[0].flip


def test_saving_over_an_old_format_file_keeps_a_backup(app, tmp_path):
    path = tmp_path / "old.refpad"
    path.write_text('{"version": "1.0", "items": []}', encoding="utf-8")
    boards.write_board(str(path), [], None)
    assert zipfile.is_zipfile(path)
    assert (tmp_path / "old.old.refpad").read_text(encoding="utf-8").startswith('{"version"')


def test_opens_refpad_1_boards(app, tmp_path):
    pic = tmp_path / "pose.png"
    _picture(200, 100).save(str(pic))
    data = {"version": "1.0", "items": [
        {"source_type": "file", "file_path": str(pic), "x": 10, "y": 20, "scale": 2.0, "rotation": 90,
         "is_flipped_h": True, "is_grayscale": False},
        {"source_type": "clipboard", "file_path": "", "x": 0, "y": 0, "scale": 1.0,
         "embedded_data": base64.b64encode(_png_bytes(_picture(50, 50))).decode()},
        {"source_type": "file", "file_path": str(tmp_path / "gone.jpg"), "x": 0, "y": 0, "scale": 1.0},
    ]}
    path = tmp_path / "v1.refpad"
    path.write_text(json.dumps(data), encoding="utf-8")
    loaded = boards.read_board(str(path))
    assert loaded.kind == "refpad-v1" and len(loaded.items) == 2 and loaded.missing == 1
    first = loaded.items[0]
    assert (first.rot, first.flip) == (1, True)
    assert abs(first.cx - (10 + 200 * 2.0 / 2)) < 0.01 and abs(first.cy - (20 + 100 * 2.0 / 2)) < 0.01
    assert abs(first.w * first.scale - 400) < 0.5   # same size on the board as before


def test_opens_beeref_boards(app, tmp_path):
    path = tmp_path / "board.bee"
    con = sqlite3.connect(path)
    con.executescript("""
        CREATE TABLE items (id INTEGER PRIMARY KEY, type TEXT, x REAL, y REAL, z REAL, scale REAL,
                            rotation REAL, flip INTEGER, data JSON);
        CREATE TABLE sqlar (name TEXT PRIMARY KEY, item_id INTEGER, mode INT, mtime INT, sz INT, data BLOB);
    """)
    con.execute("INSERT INTO items VALUES (1, 'pixmap', 5, 6, 1, 0.5, 0, -1, '{\"grayscale\": true}')")
    con.execute("INSERT INTO sqlar VALUES ('0001.png', 1, 0, 0, 0, ?)", (_png_bytes(_picture(120, 80)),))
    con.execute("INSERT INTO items VALUES (2, 'text', 0, 0, 2, 1, 0, 1, '{\"text\": \"note\"}')")
    con.commit()
    con.close()
    loaded = boards.read_board(str(path))
    assert loaded.kind == "bee" and len(loaded.items) == 1
    it = loaded.items[0]
    assert it.flip and it.gray and abs(it.w * it.scale - 60) < 0.5


def test_bad_files_give_a_clear_message(app, tmp_path):
    bad = tmp_path / "x.refpad"
    bad.write_bytes(b"not a board")
    with pytest.raises(boards.BoardError):
        boards.read_board(str(bad))
    with pytest.raises(boards.BoardError, match="can't be found"):
        boards.read_board(str(tmp_path / "missing.refpad"))


@pytest.mark.parametrize("text,count,expected", [
    ("1-5, 8", 20, [0, 1, 2, 3, 4, 7]),
    ("12-", 14, [11, 12, 13]),
    ("-3", 10, [0, 1, 2]),
    ("3 1 2", 5, [0, 1, 2]),
    ("5-3", 9, [2, 3, 4]),
    ("0", 5, None),
    ("40", 30, None),
    ("abc", 5, None),
])
def test_page_numbers(text, count, expected):
    assert parse_pages(text, count) == expected


def test_page_numbers_round_trip():
    assert pages_text([0, 1, 2, 3, 7, 10, 11]) == "1-4, 8, 11-12"
    assert parse_pages(pages_text([0, 1, 2, 3, 7, 10, 11]), 20) == [0, 1, 2, 3, 7, 10, 11]
