"""Studio dark palette (same as Android), the app style sheet and the icon set."""
from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from refpad.ui.icon_paths import ICONS

BG = "#0E0E10"
SURFACE = "#17171A"
RAISED = "#222227"
STROKE = "#2C2C33"
STROKE_STRONG = "#3F3F46"
ACCENT = "#FACC15"
ACCENT_PRESSED = "#EAB308"
TEXT = "#F4F4F5"
TEXT_2 = "#A1A1AA"
MUTED = "#71717A"
DISABLED = "#46464E"
ON_ACCENT = "#0A0A0B"
DANGER = "#F87171"

FONT_FAMILY = "Segoe UI Variable Text"

# Board / practice backgrounds: dark (default), neutral grey (judging colours), light.
BACKGROUNDS = {"dark": ("#0E0E10", "#2A2A31"), "grey": ("#76767A", "#6A6A6E"), "light": ("#E8E8EB", "#D2D2D8")}


def board_colors():
    from refpad.settings import settings
    bg, dot = BACKGROUNDS.get(settings["board_bg"], BACKGROUNDS["dark"])
    return QColor(bg), QColor(dot)


def color(hex_: str, alpha: float = 1.0) -> QColor:
    c = QColor(hex_)
    c.setAlphaF(alpha)
    return c


def app_font() -> QFont:
    f = QFont(FONT_FAMILY)
    if not f.exactMatch():
        f = QFont("Segoe UI")
    f.setPointSizeF(9.5)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


# ----------------------------------------------------------------------------- icons

_renderers: dict[str, QSvgRenderer] = {}
_icons: dict[tuple, QIcon] = {}


def _renderer(name: str, fill: str) -> QSvgRenderer:
    key = name + fill
    r = _renderers.get(key)
    if r is None:
        vw, vh, paths = ICONS[name]
        body = "".join(f'<path d="{d}" fill="{fill}" fill-opacity="{a}"/>' for d, a in paths)
        svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {vw:g} {vh:g}">{body}</svg>'
        r = _renderers[key] = QSvgRenderer(QByteArray(svg.encode()))
    return r


def pixmap(name: str, fill: str = TEXT, size: int = 20, dpr: float = 2.0) -> QPixmap:
    pm = QPixmap(round(size * dpr), round(size * dpr))
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    _renderer(name, fill).render(p, QRectF(0, 0, pm.width(), pm.height()))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return pm


def icon(name: str, fill: str = TEXT, checked_fill: str = "") -> QIcon:
    """A crisp icon for any screen scale; greyed automatically when disabled."""
    key = (name, fill, checked_fill)
    ic = _icons.get(key)
    if ic is None:
        ic = QIcon()
        for size in (16, 20, 24, 32):
            for dpr in (1.0, 1.5, 2.0):
                ic.addPixmap(pixmap(name, fill, size, dpr), QIcon.Mode.Normal, QIcon.State.Off)
                ic.addPixmap(pixmap(name, DISABLED, size, dpr), QIcon.Mode.Disabled, QIcon.State.Off)
                if checked_fill:
                    ic.addPixmap(pixmap(name, checked_fill, size, dpr), QIcon.Mode.Normal, QIcon.State.On)
        _icons[key] = ic
    return ic


ICON_SIZE = QSize(20, 20)


# ----------------------------------------------------------------------------- style sheet

STYLE = f"""
QWidget {{ color: {TEXT}; }}
QToolTip {{ background: {RAISED}; color: {TEXT}; border: 1px solid {STROKE_STRONG}; padding: 4px 8px; border-radius: 6px; }}

#TopBar {{ background: {SURFACE}; border-bottom: 1px solid {STROKE}; }}
#FloatHeader {{ background: {SURFACE}; border-bottom: 1px solid {STROKE}; }}
#AppTitle {{ font-size: 15px; font-weight: 700; color: {TEXT}; padding-right: 6px; }}
QPushButton#BoardName {{ background: transparent; border: none; border-radius: 10px; color: {TEXT}; font-size: 15px; font-weight: 700; padding: 6px 10px; text-align: left; }}
QPushButton#BoardName:hover {{ background: {RAISED}; }}

QPushButton[segment="true"] {{
    background: transparent; color: {TEXT_2}; border: 1px solid {STROKE_STRONG};
    border-radius: 17px; padding: 0 16px; min-height: 34px; font-size: 13px; font-weight: 600;
}}
QPushButton[segment="true"]:hover {{ background: {RAISED}; color: {TEXT}; }}
QPushButton[segment="true"]:checked {{ background: {ACCENT}; color: {ON_ACCENT}; border-color: {ACCENT}; }}
QPushButton[segment="true"][compact="true"] {{ min-height: 28px; border-radius: 14px; padding: 0 11px; font-size: 12px; }}

QToolButton {{ background: transparent; border: none; border-radius: 10px; padding: 4px; color: {TEXT}; }}
QToolButton:hover {{ background: {RAISED}; }}
QToolButton:pressed {{ background: {STROKE_STRONG}; }}
QToolButton:checked {{ background: rgba(250, 204, 21, 0.16); color: {ACCENT}; }}
QToolButton:disabled {{ color: {DISABLED}; }}
QToolButton[tool="true"] {{ font-size: 11px; font-weight: 600; padding: 6px 4px 4px 4px; min-width: 54px; }}
QToolButton[accent="true"] {{ color: {ACCENT}; }}
QToolButton[danger="true"] {{ color: {DANGER}; }}
QToolButton::menu-indicator {{ image: none; width: 0; }}
QToolButton#WindowClose:hover {{ background: #C42B1C; }}

QPushButton[kind="primary"] {{
    background: {ACCENT}; color: {ON_ACCENT}; border: none; border-radius: 12px;
    min-height: 44px; padding: 0 22px; font-size: 14px; font-weight: 700;
}}
QPushButton[kind="primary"]:hover {{ background: #FDD835; }}
QPushButton[kind="primary"]:pressed {{ background: {ACCENT_PRESSED}; }}
QPushButton[kind="secondary"] {{
    background: {RAISED}; color: {TEXT}; border: 1px solid {STROKE_STRONG}; border-radius: 12px;
    min-height: 40px; padding: 0 18px; font-size: 13px; font-weight: 600;
}}
QPushButton[kind="secondary"]:hover {{ background: #2A2A30; }}
QPushButton[kind="link"] {{ background: transparent; border: none; color: {ACCENT}; font-size: 13px; font-weight: 600; padding: 6px; }}
QPushButton[kind="link"]:hover {{ text-decoration: underline; }}
QPushButton:disabled {{ color: {DISABLED}; }}

#EmptyCard {{ background: {SURFACE}; border: 1px solid {STROKE}; border-radius: 22px; }}
#EmptyTitle {{ font-size: 21px; font-weight: 700; }}
#EmptyBody {{ font-size: 13px; color: {TEXT_2}; }}
#EmptyTip {{ font-size: 12px; color: {MUTED}; }}

#Chip {{ background: {RAISED}; border: 1px solid {STROKE_STRONG}; border-radius: 18px; }}
#ChipText {{ font-size: 13px; }}
#ChipUndo {{ background: transparent; border: none; color: {ACCENT}; font-weight: 700; font-size: 12px; padding: 4px 8px; }}

#Hud {{ background: {RAISED}; border: 1px solid {STROKE}; border-radius: 17px; }}
#HudTime {{ font-size: 15px; font-weight: 700; color: {ACCENT}; }}
#HudPose {{ font-size: 12px; color: {TEXT_2}; }}
#PageLabel {{ font-size: 13px; font-weight: 600; color: {TEXT}; padding: 0 6px; }}

QMenu {{ background: {RAISED}; border: 1px solid {STROKE_STRONG}; border-radius: 12px; padding: 6px; }}
QMenu::item {{ padding: 8px 28px 8px 12px; border-radius: 8px; font-size: 13px; }}
QMenu::item:selected {{ background: #2E2E35; }}
QMenu::item:disabled {{ color: {DISABLED}; }}
QMenu::icon {{ padding-left: 10px; }}
QMenu::separator {{ height: 1px; background: {STROKE}; margin: 5px 8px; }}
QMenu QLabel {{ color: {MUTED}; font-size: 11px; font-weight: 700; padding: 8px 12px 4px 12px; }}

QDialog {{ background: {SURFACE}; }}
QTextBrowser {{ background: {BG}; border: 1px solid {STROKE}; border-radius: 10px; padding: 10px; color: {TEXT_2}; }}
QCheckBox {{ spacing: 8px; font-size: 13px; }}
QCheckBox::indicator {{ width: 18px; height: 18px; border-radius: 5px; border: 1px solid {STROKE_STRONG}; background: {RAISED}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QProgressBar {{ background: {RAISED}; border: none; border-radius: 4px; height: 8px; text-align: center; color: transparent; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 4px; }}
QLabel#DialogTitle {{ font-size: 18px; font-weight: 700; }}
QLabel#Muted {{ color: {TEXT_2}; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {STROKE_STRONG}; border-radius: 4px; min-height: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
"""
