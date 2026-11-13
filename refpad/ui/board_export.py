"""The board (or the selected images) as one PNG picture, rendered from the full-size copies."""
from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QImage, QPainter

from refpad import paths
from refpad.core import images

MAX_SIDE = 8000
MARGIN = 40.0   # board units around the pictures


def render_board(items, bg: QColor) -> QImage:
    """Runs on a worker thread. `items` are copies of the board items."""
    from refpad.ui.board_view import paint_grid, paint_note
    if not items:
        raise ValueError("Nothing to export")
    r = items[0].bounds()
    for it in items[1:]:
        r = r.united(it.bounds())
    r = r.adjusted(-MARGIN, -MARGIN, MARGIN, MARGIN)
    # As sharp as the sharpest picture, but never bigger than MAX_SIDE.
    k = max([1 / max(1e-6, it.scale) for it in items if not it.is_note] or [1.0])
    k = min(k, MAX_SIDE / max(r.width(), r.height()))
    out = QImage(max(1, round(r.width() * k)), max(1, round(r.height() * k)), QImage.Format.Format_RGB32)
    out.fill(bg)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    for it in items:
        b = it.bounds()
        target = QRectF((b.left() - r.left()) * k, (b.top() - r.top()) * k, b.width() * k, b.height() * k)
        if it.is_note:
            paint_note(p, it, target, it.scale * k)
            continue
        src = images.read_image(str(paths.IMG / it.image))
        if src is None:
            continue
        pic = images.item_picture(it, src)
        p.setOpacity(it.opacity)
        p.drawImage(target, pic)
        p.setOpacity(1.0)
        if it.grid:
            paint_grid(p, target, it.grid)
    p.end()
    return out
