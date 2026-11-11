"""Makes the Windows icon (refpad/assets/refpad.ico + icon-128.png) from the store icon, as a rounded tile.

    py -3.12 tools/make_win_icon.py
"""
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "play-store/icon-512.png"
OUT = ROOT / "refpad/assets"
SIZES = (16, 20, 24, 32, 40, 48, 64, 96, 128, 256)


def tile(size: int) -> Image.Image:
    big = 1024
    src = Image.open(SRC).convert("RGBA").resize((big, big), Image.LANCZOS)
    inset = 0 if size <= 32 else round(big * 0.03)      # small sizes use every pixel
    body = src.resize((big - 2 * inset, big - 2 * inset), Image.LANCZOS)
    mask = Image.new("L", body.size, 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, body.width - 1, body.height - 1], radius=round(body.width * 0.2), fill=255)
    out = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    out.paste(body, (inset, inset), mask)
    return out.resize((size, size), Image.LANCZOS)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    images = [tile(s) for s in SIZES]
    images[-1].save(OUT / "refpad.ico", sizes=[(s, s) for s in SIZES], append_images=images[:-1])
    tile(128).save(OUT / "icon-128.png")
    print("wrote", OUT / "refpad.ico", "and icon-128.png")


if __name__ == "__main__":
    main()
