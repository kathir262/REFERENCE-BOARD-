"""Undo/redo, crop, notes, value steps and squint."""
from PySide6.QtCore import QPointF
from PySide6.QtGui import QColor, QImage

from refpad import paths
from refpad.core import images
from refpad.core.store import BoardItem, State, note_item


def _pics(n):
    out = []
    for i in range(n):
        name = f"u{i}.jpg"
        (paths.IMG / name).write_bytes(b"x")
        it = BoardItem(name, 400, 300)
        it.fit_new()
        out.append(it)
    return out


def test_undo_redo(app):
    st = State()
    st.items.clear()
    st._forget_history()
    st.add_items(_pics(3))
    assert st.can_undo and not st.can_redo
    st.items[0].flip = True
    st.edited()
    st.undo()
    assert not st.items[0].flip and len(st.items) == 3
    st.redo()
    assert st.items[0].flip
    st.undo()
    st.undo()
    assert st.items == [] and not st.can_undo
    st.redo()
    assert len(st.items) == 3


def test_one_import_is_one_undo_step(app):
    st = State()
    st.items.clear()
    st._forget_history()
    for it in _pics(5):             # pictures arriving one by one from the same import
        st.add_items([it])
    st.undo()
    assert st.items == []


def test_undo_keeps_running_imports_on_the_same_board(app):
    st = State()
    board = st.items
    st.add_items(_pics(1))
    st.undo()
    assert st.items is board        # importers check this to know the board wasn't switched


def test_crop_and_look_survive_saving(app):
    it = BoardItem("a.jpg", 400, 300, crop=(10.0, 20.0, 200.0, 100.0), opacity=0.5, locked=True, grid=3,
                   values=4, blur=True)
    it.scale = 2
    assert (it.ew, it.eh) == (400, 200)        # cropped part, scaled
    it.rot = 1
    assert (it.ew, it.eh) == (200, 400)
    again = BoardItem.from_json(it.to_json())
    assert (again.crop, again.opacity, again.locked, again.grid, again.values, again.blur) == \
           ((10.0, 20.0, 200.0, 100.0), 0.5, True, 3, 4, True)


def test_crop_keeps_the_picture_in_place(app):
    from refpad.ui.board_view import BoardView, item_transform
    it = BoardItem("a.jpg", 400, 300, cx=100, cy=50, scale=1.5, rot=1, flip=True)
    before = item_transform(it).map(QPointF(250, 120))
    BoardView._set_crop(it, (100, 50, 200, 150))
    after = item_transform(it).map(QPointF(250, 120))
    assert abs(before.x() - after.x()) < 1e-6 and abs(before.y() - after.y()) < 1e-6
    BoardView._set_crop(it, None)
    assert abs(it.cx - 100) < 1e-6 and abs(it.cy - 50) < 1e-6


def test_value_steps_and_squint(app):
    img = QImage(64, 64, QImage.Format.Format_RGB32)
    for x in range(64):
        for y in range(64):
            img.setPixelColor(x, y, QColor(x * 4, x * 4, x * 4))
    three = images.posterize(img, 3)
    assert {QColor(three.pixel(x, 5)).red() for x in range(64)} == {0, 128, 255}
    blurred = images.squint(img)
    assert blurred.size() == img.size()


def test_notes(app):
    n = note_item("Short", 0, 0)
    tall = note_item("A much longer note that needs several lines to fit in the box at its width\nand a second paragraph", 0, 0)
    assert n.is_note and tall.h > n.h and n.w == tall.w
    assert BoardItem.from_json(tall.to_json()).note == tall.note
