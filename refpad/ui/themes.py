"""
Theme manager and color palettes for RefPad.
Supports Pure Black & White (Monochrome), Rose Blossom, Midnight Violet, and Clean Paper.
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
    accent: str           # Primary accent (e.g. violet, rose, pure white)
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
        bg_card="#0f0f0f",
        bg_card_translucent="rgba(15, 15, 15, 235)",
        accent="#ffffff",
        accent_hover="#e0e0e0",
        text_primary="#ffffff",
        text_muted="#888888",
        border="rgba(255, 255, 255, 38)",
        dot_grid="rgba(255, 255, 255, 22)",
        ring_track="rgba(255, 255, 255, 35)"
    ),
    "rose": ThemePalette(
        name="Rose Blossom",
        bg_dark="#140f13",
        bg_card="#1f151c",
        bg_card_translucent="rgba(31, 21, 28, 235)",
        accent="#fb7185",             # Warm rose
        accent_hover="#f43f5e",
        text_primary="#fff1f2",
        text_muted="#fda4af",
        border="rgba(251, 113, 133, 45)",
        dot_grid="rgba(251, 113, 133, 20)",
        ring_track="rgba(251, 113, 133, 35)"
    ),
    "midnight": ThemePalette(
        name="Midnight Violet (Default)",
        bg_dark="#0e1015",
        bg_card="#161820",
        bg_card_translucent="rgba(22, 24, 32, 235)",
        accent="#7e57f6",             # Electric violet
        accent_hover="#906bf9",
        text_primary="#f0f3f6",
        text_muted="#8b949e",
        border="rgba(255, 255, 255, 28)",
        dot_grid="rgba(255, 255, 255, 14)",
        ring_track="rgba(255, 255, 255, 30)"
    ),
    "paper": ThemePalette(
        name="Clean Paper (Light)",
        bg_dark="#f3f4f6",
        bg_card="#ffffff",
        bg_card_translucent="rgba(255, 255, 255, 235)",
        accent="#2563eb",             # Sketch blue
        accent_hover="#1d4ed8",
        text_primary="#111827",
        text_muted="#6b7280",
        border="rgba(0, 0, 0, 30)",
        dot_grid="rgba(0, 0, 0, 16)",
        ring_track="rgba(0, 0, 0, 25)"
    )
}

current_theme_key = "black_white"  # Defaulting to user's desired Black & White

def get_current_theme() -> ThemePalette:
    return THEMES.get(current_theme_key, THEMES["black_white"])

def set_current_theme(key: str) -> ThemePalette:
    global current_theme_key
    if key in THEMES:
        current_theme_key = key
    return get_current_theme()
