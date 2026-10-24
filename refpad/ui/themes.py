"""
Theme manager and color palettes for RefPad.
Zero purple anywhere. Default is pure Black & White (Monochrome).
"""
from dataclasses import dataclass
from typing import Dict
from PySide6.QtGui import QColor

@dataclass
class ThemePalette:
    name: str
    bg_dark: str          # Main background
    bg_card: str          # Card / HUD / Dock background
    bg_card_translucent: str
    accent: str           # Primary accent (pure white, rose, amber, cobalt)
    accent_hover: str
    text_primary: str     # Main text
    text_muted: str       # Secondary text
    border: str           # Subtle borders
    dot_grid: str         # Canvas dot grid color
    ring_track: str       # Timer ring background track

THEMES: Dict[str, ThemePalette] = {
    "black_white": ThemePalette(
        name="Black & White (Monochrome)",
        bg_dark="#000000",
        bg_card="#111111",
        bg_card_translucent="rgba(17, 17, 17, 240)",
        accent="#ffffff",
        accent_hover="#cccccc",
        text_primary="#ffffff",
        text_muted="#888888",
        border="rgba(255, 255, 255, 45)",
        dot_grid="rgba(255, 255, 255, 25)",
        ring_track="rgba(255, 255, 255, 35)"
    ),
    "rose": ThemePalette(
        name="Rose Blossom",
        bg_dark="#140f13",
        bg_card="#1f151c",
        bg_card_translucent="rgba(31, 21, 28, 240)",
        accent="#fb7185",             # Warm rose
        accent_hover="#f43f5e",
        text_primary="#fff1f2",
        text_muted="#fda4af",
        border="rgba(251, 113, 133, 50)",
        dot_grid="rgba(251, 113, 133, 25)",
        ring_track="rgba(251, 113, 133, 35)"
    ),
    "amber": ThemePalette(
        name="Studio Amber",
        bg_dark="#101114",
        bg_card="#181a20",
        bg_card_translucent="rgba(24, 26, 32, 240)",
        accent="#f59e0b",             # Warm amber gold
        accent_hover="#d97706",
        text_primary="#fef3c7",
        text_muted="#d97706",
        border="rgba(245, 158, 11, 45)",
        dot_grid="rgba(245, 158, 11, 20)",
        ring_track="rgba(245, 158, 11, 30)"
    ),
    "paper": ThemePalette(
        name="Clean Paper (Light)",
        bg_dark="#f3f4f6",
        bg_card="#ffffff",
        bg_card_translucent="rgba(255, 255, 255, 240)",
        accent="#111827",             # Crisp ink black
        accent_hover="#374151",
        text_primary="#111827",
        text_muted="#6b7280",
        border="rgba(0, 0, 0, 35)",
        dot_grid="rgba(0, 0, 0, 20)",
        ring_track="rgba(0, 0, 0, 30)"
    )
}

current_theme_key = "black_white"  # Pure Black & White by default

def get_current_theme() -> ThemePalette:
    return THEMES.get(current_theme_key, THEMES["black_white"])

def set_current_theme(key: str) -> ThemePalette:
    global current_theme_key
    if key in THEMES:
        current_theme_key = key
    return get_current_theme()
