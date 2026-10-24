"""
BeeRef Board File I/O Manager:
Saves, opens, and exports entire moodboards (.refpad / .bee compatible JSON).
Handles relative paths and base64 embedded pasted images.
"""
import json
import base64
import os
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
                "rotation": c_item.rotation(),
                "is_flipped_h": ref.is_flipped_h,
                "is_grayscale": ref.is_grayscale,
                "is_silhouette": ref.is_silhouette
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
        """Load board data from .refpad / .bee JSON."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            return data
        except Exception as e:
            print(f"Error loading board from {file_path}: {e}")
            return None
