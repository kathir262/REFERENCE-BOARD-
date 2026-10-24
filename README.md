# RefPad (BeeRef + Line of Action)

A sleek, lightweight, floating picture-in-picture reference companion designed specifically for digital artists (Clip Studio Paint, Photoshop, Krita, Blender) and traditional sketchers.

RefPad combines two indispensable tools:
1. **Line of Action Practice Mode**: Timed gesture/pose drawing engine with a circular countdown ring HUD, interval options (30s, 1m, 2m, 3m, 5m, custom), warm-up ladders, and auto-advancing poses.
2. **BeeRef Infinite Board Mode**: Infinite 2D zoomable and pannable reference canvas where you can arrange moodboards, scale and compare poses, and tile references side-by-side.

---

## Key Features

* **Floating Frameless Window**:
  - Always-on-top toggle (`📌` or `T`) to hover persistently over Clip Studio Paint or Photoshop.
  - Tablet-friendly: drag anywhere to move, resize smoothly from any edge or corner.
  - Opacity slider (`20%` to `100%`, or shortcuts `[` and `]`).
* **Folder & PDF Ingestion**:
  - Drag and drop an entire folder of reference images (JPG, PNG, WEBP, BMP).
  - Open or drop any anatomy/figure drawing PDF book (powered by PyMuPDF for instant high-DPI rasterization).
  - PDFs inside folders are also automatically extracted!
* **Line of Action Timed Practice**:
  - Circular countdown timer HUD with live remaining time and pose badge (e.g. `2 MINUTE POSE`).
  - Warm-up ladder mode: `5 × 30s` $\rightarrow$ `5 × 1m` $\rightarrow$ `2 × 5m`.
  - Pause, skip, restart timer, and soft audio chime on pose switch.
* **BeeRef Infinite Reference Board**:
  - Infinite 2D canvas with smooth mouse wheel zooming and middle-click panning.
  - Auto-arrange grid button (`⊞ Tile Grid`) to organize dozens of references cleanly.
  - Double-click any image on the canvas to immediately launch a timed practice session from it!
* **Artist Power Tools**:
  - Horizontal Mirroring (`H`): Checks anatomy balance and flips perspective.
  - Grayscale Mode (`G`): Analyzes tonal values and lighting hierarchy.
  - Silhouette Mode (`C`): Isolates gesture lines and shapes with high-contrast thresholding.

---

## Keyboard Express Keys

| Shortcut | Action |
| :--- | :--- |
| `Tab` | **Toggle between Practice Mode (Line of Action) & Board Mode (BeeRef)** |
| `Space` | Play / Pause timer |
| `Right Arrow` or `D` | Skip forward to next pose |
| `Left Arrow` or `A` | Go back to previous pose |
| `R` | Restart current pose timer |
| `H` | Flip horizontal (mirror) |
| `G` | Grayscale / B&W toggle |
| `C` | High-contrast silhouette toggle |
| `T` | Pin Always-On-Top toggle |
| `[` / `]` | Decrease / Increase window opacity |
| `Middle Drag` | Pan canvas / image |
| `Mouse Wheel` | Zoom in / out |

---

## Installation & Running

RefPad runs on Python 3.10+ (tested with Python 3.12).

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Launch RefPad
python run.py
```

You can also pass a folder or PDF directly from the terminal:
```bash
python run.py "C:\Path\To\My\GesturePoses"
python run.py "C:\Path\To\AnatomyBook.pdf"
```
