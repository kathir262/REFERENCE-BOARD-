"""Building blocks shared by the main window and the floating window."""
from PySide6.QtCore import QEasingCurve, QPoint, QPropertyAnimation, QRectF, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QKeySequence, QPainter, QPen
from PySide6.QtWidgets import (QButtonGroup, QFrame, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QMenu,
                               QPushButton, QSizePolicy, QToolButton, QVBoxLayout, QWidget, QWidgetAction)

from refpad.ui import theme


# ----------------------------------------------------------------------------- buttons

class ToolButton(QToolButton):
    """Toolbar button driven by a QAction: icon above a short label (full window) or icon only (floating window).
    Enabled/checked state, tooltip and shortcut all come from the action."""

    def __init__(self, action: QAction, compact: bool = False, accent: bool = False, danger: bool = False, parent=None):
        super().__init__(parent)
        self.setDefaultAction(action)
        self.setIconSize(QSize(20, 20) if compact else QSize(22, 22))
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.setAutoRaise(True)
        self.setProperty("accent", accent)
        self.setProperty("danger", danger)
        if compact:
            self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            self.setFixedSize(36, 36)
        else:
            self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            self.setProperty("tool", True)


def make_action(parent, text: str, icon_name: str, fn=None, shortcut="", tip: str = "",
                accent: bool = False, danger: bool = False, checkable: bool = False) -> QAction:
    fill = theme.ACCENT if accent else theme.DANGER if danger else theme.TEXT
    act = QAction(theme.icon(icon_name, fill, theme.ACCENT if checkable else ""), text.replace("&", "&&"), parent)
    act.icon_name = icon_name
    act.setCheckable(checkable)
    keys = [shortcut] if isinstance(shortcut, str) and shortcut else list(shortcut or [])
    if keys:
        act.setShortcuts([QKeySequence(k) for k in keys])
    tip = tip or text
    if keys:
        tip += f"  ({QKeySequence(keys[0]).toString(QKeySequence.SequenceFormat.NativeText)})"
    act.setToolTip(tip)
    if fn is not None:
        act.triggered.connect(lambda _=False: fn())
    return act


class IconButton(QToolButton):
    def __init__(self, name: str, tip: str, size: int = 36, fill: str = theme.TEXT, parent=None):
        super().__init__(parent)
        self.setIcon(theme.icon(name, fill))
        self.setIconSize(QSize(20, 20))
        self.setFixedSize(size, size)
        self.setToolTip(tip)
        self.setAutoRaise(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.NoFocus)


def separator(compact: bool) -> QFrame:
    line = QFrame()
    line.setFixedSize(1, 22 if compact else 30)
    line.setStyleSheet(f"background: {theme.STROKE_STRONG};")
    line.setProperty("separator", True)
    return line


# ----------------------------------------------------------------------------- menus

def menu(parent=None) -> QMenu:
    m = QMenu(parent)
    m.setWindowFlag(Qt.WindowType.NoDropShadowWindowHint, False)
    m.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    m.setSeparatorsCollapsible(True)
    return m


def header(m: QMenu, text: str):
    label = QLabel(text.upper())
    act = QWidgetAction(m)
    act.setDefaultWidget(label)
    act.setEnabled(False)
    m.addAction(act)


def item(m: QMenu, text: str, icon_name: str, fn, enabled: bool = True, danger: bool = False, shortcut: str = ""):
    act = QAction(theme.icon(icon_name, theme.DANGER if danger else theme.TEXT_2), text.replace("&", "&&"), m)
    act.setEnabled(enabled)
    if shortcut:
        act.setShortcut(QKeySequence(shortcut))
        act.setShortcutVisibleInContextMenu(True)
    act.triggered.connect(fn)
    m.addAction(act)
    return act


# ----------------------------------------------------------------------------- adaptive toolbar

class AdaptiveToolbar(QWidget):
    """A row of tools that fits the space it has. When the window is too narrow the least important tools
    move into a "More" menu at the end, the same as on Android phones."""

    def __init__(self, compact: bool, floating: bool, parent=None):
        super().__init__(parent)
        self.compact = compact
        self.floating = floating       # painted as a pill over the content
        self._entries = []             # (widget, hide_rank or None)
        self._hidden: list = []
        self.lay = QHBoxLayout(self)
        pad = 14 if floating else 0
        if floating:
            self.lay.setContentsMargins(pad + 6, pad + 4, pad + 6, pad + 4)
        else:
            self.lay.setContentsMargins(6, 3, 6, 3)
        self.lay.setSpacing(2 if compact else 4)
        self.more = ToolButton(make_action(self, "More", "more", self._show_more), compact)
        self.more.hide()
        self._shadow_pad = pad
        if not floating:
            self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def add(self, w: QWidget, hide_rank=None):
        self._entries.append((w, hide_rank))
        self.lay.addWidget(w)
        return w

    def add_separator(self):
        return self.add(separator(self.compact))

    def finish(self):
        if not self.floating:
            self.lay.addStretch(1)
        self.lay.addWidget(self.more)

    def _natural(self) -> int:
        m = self.lay.contentsMargins()

        def width(w):   # what the layout will really give it (fixed-size buttons ignore their size hint)
            return w.sizeHint().expandedTo(w.minimumSize()).boundedTo(w.maximumSize()).width()

        widths = [width(w) for w, _ in self._entries if not w.isHidden()]
        if not self.more.isHidden():
            widths.append(width(self.more))
        return m.left() + m.right() + sum(widths) + self.lay.spacing() * max(0, len(widths) - 1)

    def fit(self, avail: int) -> int:
        """Shows as many tools as fit into `avail` pixels; returns the width the bar needs."""
        self._hidden = []
        for w, _ in self._entries:
            w.setVisible(not getattr(w, "_off", False))
        self.more.hide()
        if self._natural() <= avail:
            return self._natural()
        for w, _ in self._entries:
            if w.property("separator"):
                w.hide()
        self.more.show()
        order = sorted((e for e in self._entries if e[1] is not None and not e[0].isHidden()), key=lambda e: e[1])
        for w, _ in order:
            if self._natural() <= avail:
                break
            w.hide()
            self._hidden.append(w)
        return self._natural()

    def set_off(self, w: QWidget, off: bool):
        """Permanently hides a tool (independent of the fitting)."""
        w._off = off
        w.setVisible(not off)

    def _show_more(self):
        m = menu(self)
        for w in sorted(self._hidden, key=lambda w: self.lay.indexOf(w)):
            act = w.defaultAction() if isinstance(w, QToolButton) else None
            if act is not None:
                m.addAction(act)
        if m.isEmpty():
            return
        size = m.sizeHint()
        m.exec(self.more.mapToGlobal(QPoint(self.more.width() - size.width(), -size.height() - 6)))

    def paintEvent(self, e):
        if not self.floating:
            p = QPainter(self)
            p.fillRect(self.rect(), theme.color(theme.SURFACE))
            p.setPen(theme.color(theme.STROKE))
            p.drawLine(0, 0, self.width(), 0)
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(self._shadow_pad, self._shadow_pad - 2, -self._shadow_pad, -self._shadow_pad - 2)
        for i, a in ((10, 0.05), (6, 0.08), (3, 0.12)):     # soft shadow without a blur effect
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(0, 0, 0, round(255 * a)))
            p.drawRoundedRect(r.adjusted(-i, -i + 3, i, i + 3), 22 + i, 22 + i)
        p.setBrush(theme.color(theme.SURFACE, 0.97))
        p.setPen(QPen(theme.color(theme.STROKE_STRONG), 1))
        p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), 22, 22)


# ----------------------------------------------------------------------------- mode tabs

class Segments(QWidget):
    modeClicked = Signal(str)

    def __init__(self, compact: bool, parent=None):
        super().__init__(parent)
        self.lay = QHBoxLayout(self)
        self.lay.setContentsMargins(0, 0, 0, 0)
        self.group = QButtonGroup(self)
        self.buttons = {}
        self.show_counts = not compact
        self._counts = (0, 0)
        self._compact = None
        for mode, label, key in (("board", "Board", "Ctrl+1"), ("practice", "Practice", "Ctrl+2"), ("pdf", "PDF", "Ctrl+3")):
            b = QPushButton(label)
            b.setProperty("segment", True)
            b.setCheckable(True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.setToolTip(f"{label}  ({key})")
            b.clicked.connect(lambda _=False, m=mode: self.modeClicked.emit(m))
            self.group.addButton(b)
            self.lay.addWidget(b)
            self.buttons[mode] = b
        self.set_compact(compact)

    def set_compact(self, compact: bool):
        """Smaller tabs for narrow windows (a clear gap between them is kept either way)."""
        if compact == self._compact:
            return
        self._compact = compact
        self.lay.setSpacing(6 if compact else 10)
        for b in self.buttons.values():
            b.setProperty("compact", compact)
            b.style().unpolish(b)
            b.style().polish(b)
        self.updateGeometry()

    def set_mode(self, mode: str):
        self.buttons[mode].setChecked(True)

    def set_counts(self, board: int, practice: int):
        self._counts = (board, practice)
        self.refresh_counts()

    def refresh_counts(self):
        for mode, n in zip(("board", "practice"), self._counts):
            text = mode.capitalize() + (f"  {n}" if n and self.show_counts else "")
            if self.buttons[mode].text() != text:
                self.buttons[mode].setText(text)


# ----------------------------------------------------------------------------- practice HUD

class Hud(QFrame):
    """Countdown and pose number."""

    def __init__(self, compact: bool, parent=None):
        super().__init__(parent)
        self.setObjectName("Hud")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 2, 14, 2) if not compact else lay.setContentsMargins(10, 0, 10, 0)
        lay.setSpacing(10)
        self.time = QLabel("0:00")
        self.time.setObjectName("HudTime")
        self.pose = QLabel("")
        self.pose.setObjectName("HudPose")
        lay.addWidget(self.time)
        lay.addWidget(self.pose)
        self.setFixedHeight(30 if compact else 34)

    def set_short(self, short: bool):
        self.pose.setVisible(not short)

    def set(self, time_text: str, pose_text: str):
        if self.time.text() != time_text:
            self.time.setText(time_text)
        if self.pose.text() != pose_text:
            self.pose.setText(pose_text)


# ----------------------------------------------------------------------------- spinner

class Spinner(QWidget):
    def __init__(self, size: int = 16, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._angle = 0
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._step)

    def _step(self):
        self._angle = (self._angle + 9) % 360
        self.update()

    def showEvent(self, e):
        self._timer.start()

    def hideEvent(self, e):
        self._timer.stop()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        pen = QPen(theme.color(theme.ACCENT), 2.2)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        r = QRectF(self.rect()).adjusted(2, 2, -2, -2)
        p.drawArc(r, -self._angle * 16, 270 * 16)


# ----------------------------------------------------------------------------- status chip

class StatusChip(QFrame):
    """Short messages at the bottom ("Image deleted  UNDO", "Adding images… 3/12")."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("Chip")
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 6, 8, 6)
        lay.setSpacing(10)
        self.spinner = Spinner(16)
        self.text = QLabel()
        self.text.setObjectName("ChipText")
        self.undo_btn = QPushButton("UNDO")
        self.undo_btn.setObjectName("ChipUndo")
        self.undo_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.undo_btn.clicked.connect(self._undo)
        lay.addWidget(self.spinner)
        lay.addWidget(self.text)
        lay.addWidget(self.undo_btn)
        self._undo_fn = None
        self._hide_timer = QTimer(self)
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self.fade_out)
        self._fx = QGraphicsOpacityEffect(self)
        self._fx.setOpacity(1.0)
        self.setGraphicsEffect(self._fx)
        self._fx.setEnabled(False)
        self._anim = QPropertyAnimation(self._fx, b"opacity", self)
        self._anim.setDuration(160)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.finished.connect(self._anim_done)
        self.hide()

    def show_message(self, text: str, busy: bool = False, undo=None, action_label: str = "UNDO"):
        self.text.setText(text)
        self.spinner.setVisible(busy)
        self._undo_fn = undo
        self.undo_btn.setText(action_label)
        self.undo_btn.setVisible(undo is not None)
        self.layout().setContentsMargins(14, 6, 8 if undo else 16, 6)
        self.adjustSize()
        self._place()
        if self.isHidden() or self._anim.endValue() == 0.0:
            self._fade(1.0)
        self.raise_()
        self._hide_timer.start(30000 if busy else 6500 if undo else 3500)

    def _place(self):
        par = self.parentWidget()
        if par is None:
            return
        bottom = getattr(par, "chip_bottom", lambda: par.height() - 16)()
        self.move((par.width() - self.width()) // 2, bottom - self.height())

    def _undo(self):
        fn, self._undo_fn = self._undo_fn, None
        self.fade_out()
        if fn:
            fn()

    def fade_out(self):
        if not self.isHidden():
            self._fade(0.0)

    def _fade(self, to: float):
        self._anim.stop()
        self._fx.setEnabled(True)
        if to > 0:
            self.show()
            self._fx.setOpacity(0.0 if self._fx.opacity() >= 1.0 and self.isHidden() else self._fx.opacity())
        self._anim.setStartValue(self._fx.opacity())
        self._anim.setEndValue(to)
        self._anim.start()

    def _anim_done(self):
        if self._anim.endValue() == 0.0:
            self.hide()
            self._undo_fn = None
        self._fx.setEnabled(False)   # no off-screen rendering while it just sits there

    def reposition(self):
        if self.isVisible():
            self._place()


# ----------------------------------------------------------------------------- empty states

class EmptyState(QFrame):
    """Card shown when the board, practice list or PDF reader is empty."""

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("EmptyCard")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(36, 32, 36, 26)
        self.lay.setSpacing(10)
        self.icon = QLabel()
        self.icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.icon.setFixedHeight(76)
        self.title = QLabel()
        self.title.setObjectName("EmptyTitle")
        self.title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body = QLabel()
        self.body.setObjectName("EmptyBody")
        self.body.setWordWrap(True)
        self.body.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.primary = QPushButton()
        self.primary.setProperty("kind", "primary")
        self.row = QHBoxLayout()
        self.row.setSpacing(10)
        self.secondary = QPushButton()
        self.secondary.setProperty("kind", "secondary")
        self.tertiary = QPushButton()
        self.tertiary.setProperty("kind", "secondary")
        self.row.addWidget(self.secondary)
        self.row.addWidget(self.tertiary)
        self.link = QPushButton()
        self.link.setProperty("kind", "link")
        self.tip = QLabel()
        self.tip.setObjectName("EmptyTip")
        self.tip.setWordWrap(True)
        self.tip.setAlignment(Qt.AlignmentFlag.AlignCenter)
        for w in (self.primary, self.secondary, self.tertiary, self.link):
            w.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lay.addWidget(self.icon)
        self.lay.addWidget(self.title)
        self.lay.addWidget(self.body)
        self.lay.addSpacing(10)
        self.lay.addWidget(self.primary)
        self.lay.addLayout(self.row)
        self.lay.addWidget(self.link, 0, Qt.AlignmentFlag.AlignCenter)
        self.lay.addWidget(self.tip)
        self._handlers = {}
        for btn in (self.primary, self.secondary, self.tertiary, self.link):
            btn.clicked.connect(lambda _=False, b=btn: self._handlers.get(b, lambda: None)())
        self.hide()   # shown only once it has content

    def set_content(self, icon_name, title, body, primary, secondary=None, tertiary=None, link=None, tip=""):
        self.icon.setPixmap(_icon_circle(theme.pixmap(icon_name, theme.ACCENT, 30)))
        self.title.setText(title)
        self.body.setText(body)
        for btn, spec in ((self.primary, primary), (self.secondary, secondary), (self.tertiary, tertiary), (self.link, link)):
            btn.setVisible(spec is not None)
            if spec:
                btn.setText(spec[0].replace("&", "&&"))
                self._handlers[btn] = spec[1]
        self.tip.setText(tip)
        self.tip.setVisible(bool(tip))

    def place(self, area_w: int, area_h: int, top: int, bottom: int):
        w = min(440, area_w - 32)
        self.setFixedWidth(max(260, w))
        self.adjustSize()
        h = self.sizeHint().height()
        y = top + max(8, (area_h - top - bottom - h) // 2)
        self.setGeometry((area_w - self.width()) // 2, y, self.width(), h)


def _icon_circle(pm):
    from PySide6.QtGui import QPixmap
    dpr = pm.devicePixelRatio()
    size = 72
    out = QPixmap(round(size * dpr), round(size * dpr))
    out.setDevicePixelRatio(dpr)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(theme.color(theme.ACCENT, 0.16))
    p.drawEllipse(QRectF(0, 0, size, size))
    iw = pm.width() / dpr
    p.drawPixmap(QPoint(round((size - iw) / 2), round((size - iw) / 2)), pm)
    p.end()
    return out
