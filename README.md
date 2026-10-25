# Reference Board (RefPad)

Desktop companion application fusing **BeeRef** (infinite reference moodboard with image transforms, arrangement, and context menus) and **Line of Action** (timed gesture and figure drawing practice engine with circular countdown HUD).

Designed specifically for digital painters (Clip Studio Paint, Photoshop, Krita, Blender) and traditional sketchers who need a high-performance, distraction-free floating desktop reference tool.

---

## Architecture & Concept

Reference Board bridges the gap between passive reference organization and active gesture practice:

1. **Reference Board Mode (BeeRef Architecture)**:
   - Infinite 2D zoomable and pannable canvas.
   - 1-to-1 BeeRef image operations: horizontal/vertical flips, 90-degree rotations, grayscale value study, color inversion, opacity slider, crop, and Z-order layering.
   - Optimal automatic packing and alignment algorithms.
   - Vibrant studio yellow highlight border on selected references.
   - Dual context menus: focused image menu on right-clicking references, and complete BeeRef system menu on the floating dock.

2. **Practice Mode (Line of Action Architecture)**:
   - Timed gesture drawing sessions with a circular countdown ring HUD.
   - Configurable pose durations: 30s, 45s, 1m, 2m, 3m, 5m, 10m, and warm-up ladders (30s -> 1m -> 5m).
   - Clean keyboard controls: pause, skip, restart, flip, grayscale, and audio chimes on pose transitions.

3. **Strict Mode Separation**:
   - Reference Board and Practice Mode operate independently.
   - Smart Import Destination selector lets you route incoming references (PDFs, images, folders) to the Reference Board, Practice Mode, or both.

4. **Zero Purple Theme Engine**:
   - Pure Black & White (Monochrome) default theme for maximum visual contrast without distracting color casts.
   - Available themes: Black & White, Rose Blossom, Studio Amber, Deep Cobalt, Paper White.

---

## Key Features

- **High-DPI PDF & Folder Ingestion**:
  - Open multi-page art and anatomy PDF books directly (powered by PyMuPDF).
  - Drag and drop folders; nested image files and PDF documents are extracted automatically.
  - Paste images directly from the clipboard (`Ctrl+V`).

- **Floating Frameless Window**:
  - Borderless glass window with draggable top header and flexible multi-edge resizing.
  - Pin Always-On-Top (`T`) to float above full-screen drawing software.
  - Auto-dimming glass dock that wakes on mouse movement.

- **Direct Image Context Menu (Green Circle)**:
  - Right-clicking any image provides instant access to direct transforms: Flip H/V, Rotate 90 CW/CCW, Grayscale, Invert, Opacity, Reset Transforms, Copy, Cut, Delete, Layering.

- **Full System Menu (Red Circle)**:
  - Clicking the menu button on the floating dock opens full BeeRef system submenus: File, Edit, View, Insert, Transform, Normalize, Arrange, Images, Practice Mode, Themes, Help.

- **Yellow Selection Highlighting**:
  - Selected reference images feature a high-contrast 3px studio yellow border with corner grip handles and floating name badge.

---

## Keyboard and Mouse Shortcuts

### Navigation & Canvas
| Shortcut | Action |
| :--- | :--- |
| `Left Click + Drag` | Move reference image on canvas |
| `Middle Click + Drag` | Pan canvas |
| `Space + Left Drag` | Pan canvas (alternative) |
| `Mouse Wheel` | Smooth zoom in / out |
| `Tab` | Toggle between Reference Board and Practice Mode |
| `1` or `F` | Fit entire scene (all references in view) |
| `2` | Fit selected reference in view |
| `Double Click Item` | Focus and fit item in view |

### Image Transforms (BeeRef)
| Shortcut | Action |
| :--- | :--- |
| `H` | Flip horizontally (mirror check) |
| `V` | Flip vertically |
| `G` | Toggle grayscale (tonal value check) |
| `I` | Invert colors |
| `R` | Reset all image transformations |
| `Shift + O` or `P` | Optimal auto-pack and arrange references |
| `Shift + H` | Normalize height across selected references |
| `Shift + W` | Normalize width across selected references |
| `Shift + S` | Normalize size (area) across selected references |
| `PgUp` | Raise reference to top |
| `PgDown` | Lower reference to bottom |

### File & Session Operations
| Shortcut | Action |
| :--- | :--- |
| `Ctrl + O` | Open Reference Board file |
| `Ctrl + S` | Save Reference Board file |
| `Ctrl + Shift + S` | Save Reference Board As |
| `Ctrl + Shift + E` | Export canvas scene as PNG/JPG image |
| `Ctrl + I` | Insert images or PDF books |
| `Ctrl + T` | Add sticky text note to canvas |
| `Ctrl + C` / `Ctrl + V` | Copy / Paste reference image |
| `Del` | Delete selected reference |
| `Ctrl + A` | Select all references |
| `Ctrl + Shift + A` | Deselect all |
| `T` | Toggle Always-On-Top pin |
| `F11` | Toggle Fullscreen |
| `F1` | Open Shortcuts Help Dialog |

### Practice Mode Controls
| Shortcut | Action |
| :--- | :--- |
| `Space` | Play / Pause gesture timer |
| `Right Arrow` or `D` | Skip to next pose |
| `Left Arrow` or `A` | Go back to previous pose |
| `R` | Restart timer for current pose |

---

## Project Structure

```text
├── refpad/
│   ├── engine/
│   │   ├── audio.py            # Synthesized audio feedback cues
│   │   ├── session_engine.py   # Practice session countdown state machine
│   │   └── source_manager.py   # Multi-format image & PDF ingestion
│   ├── models/
│   │   ├── board.py            # Board serialization (.refpad / .bee JSON format)
│   │   └── item.py             # RefItem core model & transformation pipeline
│   ├── ui/
│   │   ├── action_view.py      # Line of Action gesture practice viewport
│   │   ├── beeref_menu.py      # 1-to-1 BeeRef menu engine & import destination dialog
│   │   ├── canvas_item.py      # Movable reference tile with yellow selection border
│   │   ├── canvas_view.py      # Infinite 2D graphics scene & layout arrange engine
│   │   ├── floating_dock.py    # Auto-dimming glass control toolbar
│   │   ├── icons.py            # Vector icon renderers
│   │   ├── main_window.py      # Frameless container, title bar, resize handlers
│   │   ├── themes.py           # Color palettes (Pure B&W default, zero purple)
│   │   ├── timer_hud.py        # Circular countdown ring display
│   │   └── widgets.py          # Custom UI components
│   └── main.py                 # Application entrypoint
├── tests/
│   └── test_beeref_split.py    # Automated test suite
├── run.py                      # Root launcher script
├── requirements.txt            # Python dependencies
└── README.md                   # Documentation
```

---

## One-Click Download & Launch (No Python Needed)

### Option 1: Direct Single-File Executable (.exe)
1. Download **[ReferenceBoard.exe](https://github.com/kathir262/REFERENCE-BOARD-/releases/download/v1.0.0/ReferenceBoard.exe)** (96.2 MB) from the [v1.0.0 Releases](https://github.com/kathir262/REFERENCE-BOARD-/releases/tag/v1.0.0).
2. Double-click `ReferenceBoard.exe` to run immediately. No installation or folder extraction required.

### Option 2: One-Click Desktop Installer
1. Clone or download this repository.
2. Double-click `install.bat`.
3. It will install Reference Board to `%LocalAppData%\Programs\ReferenceBoard`, create a Desktop icon and Start Menu shortcut, and launch the application automatically.

---

## Installation & Running from Source

### Prerequisites
- Python 3.10, 3.11, or 3.12 (64-bit recommended)
- Windows 10 / 11

### Setup
```bash
# Clone the repository
git clone https://github.com/kathir262/REFERENCE-BOARD-.git
cd REFERENCE-BOARD-

# Install dependencies
pip install -r requirements.txt

# Run application
python run.py
```

### CLI Launch with Arguments
You can open a folder of reference images or a PDF art book directly:
```bash
python run.py "C:\Path\To\ReferenceFolder"
python run.py "C:\Path\To\AnatomyBook.pdf"
```

---

## Building the Windows Executable (.exe)

To build a standalone single-file executable that runs without requiring Python installed:

```bash
# Build standalone single-file executable with PyInstaller
pyinstaller --noconfirm --onefile --windowed --name "ReferenceBoard" --add-data "refpad;refpad" run.py
```

The output standalone executable will be created at `dist/ReferenceBoard.exe`.

---

## License

MIT License. Designed and built as a clean, open reference desktop companion for digital artists.
