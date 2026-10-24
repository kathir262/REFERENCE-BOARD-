"""
BeeRef Board File I/O Manager:
Saves, opens, and exports entire moodboards (.refpad JSON and .bee SQLite compatible).
Handles relative paths, SQLite BLOB extraction, and base64 embedded pasted images.
"""
import json
import base64
import os
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional
from PySide6.QtGui import QPixmap, QImage
from PySide6.QtCore import QBuffer, QIODevice, QPointF

from refpad.models.item import RefItem

def pixmap_to_base64(pixmap: QPixmap) -> str:
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    pixmap.save(buf, "PNG")
    data = bytes(buf.data())
    return base64.b64encode(data).decode('utf-8')

def base64_to_pixmap(b64_str: str) -> Optional[QPixmap]:
    try:
        data = base64.b64decode(b64_str)
        pix = QPixmap()
        pix.loadFromData(data)
        return pix
    except Exception:
        return None

class BoardManager:
    @staticmethod
    def save_board(file_path: str, canvas_items: list, notes: list = None) -> bool:
        """Serialize canvas items, transforms, and sticky notes into .refpad file."""
        data = {
            "version": "1.0",
            "items": [],
            "notes": notes or []
        }

        for c_item in canvas_items:
            ref = c_item.ref_item
            pos = c_item.pos()
            item_dict: Dict[str, Any] = {
                "source_type": ref.source_type,
                "file_path": ref.file_path,
                "page_num": ref.page_num,
                "name": ref.name,
                "x": pos.x(),
                "y": pos.y(),
                "scale": c_item.scale(),
                "rotation": ref.rotation,
                "is_flipped_h": ref.is_flipped_h,
                "is_flipped_v": ref.is_flipped_v,
                "is_grayscale": ref.is_grayscale,
                "is_inverted": ref.is_inverted,
                "opacity": c_item.item_opacity
            }

            # If it was pasted from clipboard with no file path, embed base64
            if not ref.file_path or not os.path.exists(ref.file_path):
                base_pix = ref.get_base_pixmap()
                if base_pix and not base_pix.isNull():
                    item_dict["embedded_data"] = pixmap_to_base64(base_pix)

            data["items"].append(item_dict)

        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            print(f"Error saving board to {file_path}: {e}")
            return False

    @staticmethod
    def load_board(file_path: str) -> Optional[Dict[str, Any]]:
        """Load board data from .refpad JSON or native BeeRef .bee SQLite."""
        if not os.path.exists(file_path):
            return None

        # Check if this is a BeeRef SQLite database
        try:
            with open(file_path, 'rb') as f:
                header = f.read(16)
            if header.startswith(b'SQLite format 3'):
                return BoardManager._load_beeref_sqlite(file_path)
        except Exception:
            pass

        # Otherwise read as JSON
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data
        except Exception as e:
            print(f"Error loading board from {file_path}: {e}")
            return None

    @staticmethod
    def _load_beeref_sqlite(file_path: str) -> Optional[Dict[str, Any]]:
        """Read native BeeRef .bee SQLite file and convert to RefPad board dict."""
        try:
            conn = sqlite3.connect(file_path)
            c = conn.cursor()
            rows = c.execute("""
                SELECT items.id, type, x, y, z, scale, rotation, flip, items.data, sqlar.data
                FROM sqlar JOIN items ON sqlar.item_id = items.id
            """).fetchall()

            # Also check for text notes in BeeRef
            text_rows = c.execute("""
                SELECT items.id, type, x, y, z, scale, rotation, flip, items.data
                FROM items WHERE items.type = 'text'
            """).fetchall()

            result: Dict[str, Any] = {"version": "1.0", "items": [], "notes": []}

            for row in rows:
                item_id, it_type, x, y, z, scale, rotation, flip, meta_json, img_blob = row
                meta = json.loads(meta_json) if meta_json else {}
                filename = meta.get("filename", f"Item_{item_id}")

                b64_img = base64.b64encode(img_blob).decode('utf-8') if img_blob else ""

                result["items"].append({
                    "source_type": "clipboard",
                    "file_path": filename,
                    "name": Path(filename).name,
                    "x": x or 0.0,
                    "y": y or 0.0,
                    "scale": scale or 1.0,
                    "rotation": rotation or 0.0,
                    "is_flipped_h": (flip == -1),
                    "is_flipped_v": False,
                    "is_grayscale": meta.get("grayscale", False),
                    "embedded_data": b64_img
                })

            for trow in text_rows:
                meta = json.loads(trow[8]) if trow[8] else {}
                txt = meta.get("text", "")
                if txt:
                    result["notes"].append(txt)

            conn.close()
            return result
        except Exception as e:
            print(f"Error parsing BeeRef SQLite .bee file: {e}")
            return None
