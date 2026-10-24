"""
High-DPI vector icons drawn with QPainter for ultra-crisp modern UI.
No blurry emojis or low-res PNGs.
"""
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QPainterPath
from PySide6.QtCore import Qt, QRectF, QPointF

def draw_play_icon(painter: QPainter, rect: QRectF, color: QColor):
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QBrush(color))
    painter.setPen(Qt.PenStyle.NoPen)
    path = QPainterPath()
    # Triangle
    cx = rect.center().x() + 1
    cy = rect.center().y()
    s = min(rect.width(), rect.height()) * 0.42
    path.moveTo(cx - s * 0.7, cy - s)
    path.lineTo(cx + s * 0.9, cy)
    path.lineTo(cx - s * 0.7, cy + s)
    path.closeSubpath()
    painter.drawPath(path)
    painter.restore()

def draw_pause_icon(painter: QPainter, rect: QRectF, color: QColor):
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QBrush(color))
    painter.setPen(Qt.PenStyle.NoPen)
    cx = rect.center().x()
    cy = rect.center().y()
    w = 3.5
    h = min(rect.width(), rect.height()) * 0.75
    gap = 4.0
    painter.drawRoundedRect(QRectF(cx - gap - w, cy - h / 2, w, h), 1.5, 1.5)
    painter.drawRoundedRect(QRectF(cx + gap, cy - h / 2, w, h), 1.5, 1.5)
    painter.restore()

def draw_skip_next_icon(painter: QPainter, rect: QRectF, color: QColor):
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QBrush(color))
    painter.setPen(Qt.PenStyle.NoPen)
    cx = rect.center().x()
    cy = rect.center().y()
    s = min(rect.width(), rect.height()) * 0.38
    # Arrow
    p = QPainterPath()
    p.moveTo(cx - s, cy - s)
    p.lineTo(cx + s * 0.3, cy)
    p.lineTo(cx - s, cy + s)
    p.closeSubpath()
    painter.drawPath(p)
    # Bar
    painter.drawRoundedRect(QRectF(cx + s * 0.4, cy - s, 2.5, s * 2), 1, 1)
    painter.restore()

def draw_skip_prev_icon(painter: QPainter, rect: QRectF, color: QColor):
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setBrush(QBrush(color))
    painter.setPen(Qt.PenStyle.NoPen)
    cx = rect.center().x()
    cy = rect.center().y()
    s = min(rect.width(), rect.height()) * 0.38
    # Bar
    painter.drawRoundedRect(QRectF(cx - s * 0.7, cy - s, 2.5, s * 2), 1, 1)
    # Arrow
    p = QPainterPath()
    p.moveTo(cx + s, cy - s)
    p.lineTo(cx - s * 0.3, cy)
    p.lineTo(cx + s, cy + s)
    p.closeSubpath()
    painter.drawPath(p)
    painter.restore()

def draw_flip_icon(painter: QPainter, rect: QRectF, color: QColor):
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(color, 1.8)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    cx = rect.center().x()
    cy = rect.center().y()
    s = min(rect.width(), rect.height()) * 0.35
    # Center dashed line
    pen_dash = QPen(QColor(color.red(), color.green(), color.blue(), 100), 1.2, Qt.PenStyle.DashLine)
    painter.setPen(pen_dash)
    painter.drawLine(QPointF(cx, cy - s * 1.2), QPointF(cx, cy + s * 1.2))
    # Two opposing triangles
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    p1 = QPainterPath()
    p1.moveTo(cx - s * 0.2, cy - s * 0.8)
    p1.lineTo(cx - s * 1.1, cy)
    p1.lineTo(cx - s * 0.2, cy + s * 0.8)
    p1.closeSubpath()
    painter.drawPath(p1)

    p2 = QPainterPath()
    p2.moveTo(cx + s * 0.2, cy - s * 0.8)
    p2.lineTo(cx + s * 1.1, cy)
    p2.lineTo(cx + s * 0.2, cy + s * 0.8)
    p2.closeSubpath()
    painter.drawPath(p2)
    painter.restore()

def draw_grayscale_icon(painter: QPainter, rect: QRectF, color: QColor):
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx = rect.center().x()
    cy = rect.center().y()
    r = min(rect.width(), rect.height()) * 0.38
    # Circle outline
    painter.setPen(QPen(color, 1.8))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QPointF(cx, cy), r, r)
    # Filled half
    p = QPainterPath()
    p.moveTo(cx, cy - r)
    p.arcTo(QRectF(cx - r, cy - r, r * 2, r * 2), 90, 180)
    p.closeSubpath()
    painter.setBrush(QBrush(color))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawPath(p)
    painter.restore()

def draw_pin_icon(painter: QPainter, rect: QRectF, color: QColor, pinned: bool):
    painter.save()
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    cx = rect.center().x()
    cy = rect.center().y()
    pen = QPen(color, 1.8)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(QBrush(color) if pinned else Qt.BrushStyle.NoBrush)
    # Modern pushpin shape
    s = min(rect.width(), rect.height()) * 0.35
    path = QPainterPath()
    path.moveTo(cx - s * 0.6, cy - s)
    path.lineTo(cx + s * 0.6, cy - s)
    path.lineTo(cx + s * 0.3, cy)
    path.lineTo(cx - s * 0.3, cy)
    path.closeSubpath()
    painter.drawPath(path)
    # Needle
    painter.drawLine(QPointF(cx, cy), QPointF(cx, cy + s))
    painter.restore()
