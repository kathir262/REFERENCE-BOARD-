# Reference Board (RefPad)

Cross-platform companion application fusing **BeeRef** (infinite reference moodboard with image transforms, arrangement, and context menus) and **Line of Action** (timed gesture and figure drawing practice engine with circular countdown HUD).

Available for **Windows Desktop** (standalone `.exe`) and **Android Mobile & Tablets** (floating overlay `.apk` for Clip Studio Paint, HiPaint, Infinite Painter, and ibis Paint X).

---

## One-Click Downloads

### Desktop (Windows 10 / 11 64-bit)
- **Direct Standalone Executable**: **[ReferenceBoard.exe (95.9 MB)](https://github.com/kathir262/REFERENCE-BOARD-/releases/download/v1.0.0/ReferenceBoard.exe)**
  - No Python, DLLs, or installation required. Just download and double-click to launch.
- **Portable ZIP Archive**: **[ReferenceBoard-Windows-x64.zip (96.5 MB)](https://github.com/kathir262/REFERENCE-BOARD-/releases/download/v1.0.0/ReferenceBoard-Windows-x64.zip)**

### Mobile & Tablets (Android 7.0+)
- **Direct Standalone APK**: **[ReferenceBoard.apk (2.38 MB)](https://github.com/kathir262/REFERENCE-BOARD-/releases/download/v1.0.0/ReferenceBoard.apk)**
  - Direct download and install for Android phones and drawing tablets (Samsung Galaxy Tab, Xiaomi Pad, Pixel Tablet).
  - Floats directly over full-screen drawing applications.

---

## Architecture & Concept

Reference Board bridges the gap between passive reference organization and active gesture practice:

1. **Reference Board Mode (BeeRef Architecture)**:
   - Infinite 2D zoomable and pannable canvas.
   - 1-to-1 BeeRef image operations: horizontal/vertical flips, 90-degree rotations, grayscale value study, color inversion, opacity slider, crop, and Z-order layering.
   - Optimal automatic packing and alignment algorithms.
   - Vibrant studio yellow highlight border (`#facc15`) on selected references with anchor handles and floating badge.
   - Dual context menus: focused image menu on right-clicking references, and complete BeeRef system menu on the floating dock.

2. **Practice Mode (Line of Action Architecture)**:
   - Timed gesture drawing sessions with countdown timer HUD.
   - Configurable pose durations: 30s, 45s, 1m, 2m, 3m, 5m, 10m, and warm-up ladders.
   - Clean controls: pause, skip, restart, flip, grayscale, and pose chimes.

3. **Strict Mode Separation**:
   - Reference Board and Practice Mode operate independently.
   - Smart Import Destination selector routes incoming references (PDFs, images, folders) to Reference Board, Practice Mode, or both.

4. **Zero Purple Studio Dark Theme**:
   - Pure Monochrome and Dark Studio palette for zero color distortion while painting.
   - Studio Yellow accents matching studio grade monitor standards.

---

## Mobile & Tablet (Android) Companion

The Android version is built specifically for digital illustrators and comic artists:

- **Floating Overlay over Drawing Apps**:
  - Uses Android Picture-in-Picture / overlay window capabilities to float directly above Clip Studio Paint, HiPaint, Infinite Painter, ibis Paint X, and Sketchbook.
  - Freely draggable from the header and resizable from the bottom-right corner.
  - Minimize button collapses the window into an unobtrusive floating bubble while working on canvas.
- **Multi-Touch & Stylus Engine**:
  - 2-finger pinch-to-zoom and 2-finger pan.
  - 1-finger select and reposition individual reference tiles.
  - Hardware stylus (S-Pen / Wacom) detection with palm rejection. S-Pen primary button toggles play/pause or selection.
- **Native PDF Reference Ingestion**:
  - High-resolution hardware rendering of multi-page anatomy books and sketchbooks directly from device storage.
- **Quick Interval Presets**:
  - One-tap interval selector (30s, 1m, 2m, 5m) with automatic pose progression.

---

## Keyboard and Mouse Shortcuts (Desktop)

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
├── android/                    # Android Native Mobile & Tablet Application
│   ├── app/
│   │   ├── src/main/java/com/refpad/app/
│   │   │   ├── MainActivity.kt           # SAF file pickers and permissions
│   │   │   ├── FloatingOverlayService.kt # Floating overlay window manager
│   │   │   ├── RefCanvasView.kt          # Touch & stylus reference canvas
│   │   │   ├── RefBoardItem.kt           # Yellow highlighted reference model
│   │   │   ├── PdfHelper.kt              # Native PDF hardware page renderer
│   │   │   └── DataManager.kt            # Shared reference & practice state
│   │   └── src/main/res/                 # Zero purple dark studio UI layouts
│   ├── build.gradle
│   └── settings.gradle
├── refpad/                     # Python Desktop Engine
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

## Building from Source

### Windows Desktop Executable
```bash
pyinstaller --noconfirm --onefile --windowed --name "ReferenceBoard" --add-data "refpad;refpad" --exclude-module "pymupdf.layout" run.py
```
Output: `dist/ReferenceBoard.exe`

### Android Mobile APK
```bash
cd android
./gradlew assembleRelease
```
Output: `android/app/build/outputs/apk/release/ReferenceBoard-release.apk` (and `dist/ReferenceBoard.apk`)

---

## License

MIT License. Designed and built as a clean, open reference companion for digital artists.
