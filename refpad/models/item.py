"""
Reference Item representation for files and PDF pages.
"""
from dataclasses import dataclass
from typing import Optional
from pathlib import Path
from PySide6.QtGui import QPixmap, QImage, QColor, QPainter
from PySide6.QtCore import Qt

try:
    import pymupdf  # new PyMuPDF recommended import
except ImportError:
    import fitz as pymupdf

@dataclass
class RefItem:
    source_type: str  # 'file', 'pdf', or 'clipboard'
    file_path: str = ""
    page_num: int = 0
    name: str = ""
    is_flipped_h: bool = False
    is_grayscale: bool = False
    is_silhouette: bool = False
    in_memory_pixmap: Optional[QPixmap] = None
    _cached_pixmap: Optional[QPixmap] = None
    _cached_transform_key: str = ""

    def __post_init__(self):
        if not self.name:
            if self.source_type == 'clipboard':
                self.name = "Pasted Reference"
            elif self.file_path:
                p = Path(self.file_path)
                if self.source_type == 'pdf':
                    self.name = f"{p.name} (p. {self.page_num + 1})"
                else:
                    self.name = p.name
            else:
                self.name = "Reference Item"

    def get_base_pixmap(self, max_dim: int = 2560) -> Optional[QPixmap]:
        """Loads and returns the base unmodified QPixmap."""
        if self.in_memory_pixmap is not None:
            return self.in_memory_pixmap
        if self.source_type == 'pdf':
            try:
                doc = pymupdf.open(self.file_path)
                if self.page_num < 0 or self.page_num >= len(doc):
                    return None
                page = doc[self.page_num]
                # High-res rendering: 2x scale for crisp lines
                matrix = pymupdf.Matrix(2.0, 2.0)
                pix = page.get_pixmap(matrix=matrix, alpha=False)
                img = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGB888)
                pixmap = QPixmap.fromImage(img.copy())
                doc.close()
                return pixmap
            except Exception as e:
                print(f"Error loading PDF page {self.page_num} from {self.file_path}: {e}")
                return None
        else:
            pixmap = QPixmap(self.file_path)
            if pixmap.isNull():
                return None
            return pixmap

    def get_transformed_pixmap(self) -> Optional[QPixmap]:
        """Returns the pixmap with active filters (Flip, Grayscale, Silhouette)."""
        transform_key = f"{self.is_flipped_h}_{self.is_grayscale}_{self.is_silhouette}"
        if self._cached_pixmap is not None and self._cached_transform_key == transform_key:
            return self._cached_pixmap

        base = self.get_base_pixmap()
        if not base or base.isNull():
            return None

        # Apply transformations
        img = base.toImage()

        if self.is_grayscale or self.is_silhouette:
            img = img.convertToFormat(QImage.Format.Format_Grayscale8)

        if self.is_silhouette:
            # Simple threshold for silhouette gesture view
            img = img.convertToFormat(QImage.Format.Format_RGB32)
            for y in range(img.height()):
                for x in range(img.width()):
                    c = img.pixelColor(x, y)
                    val = c.red()
                    new_val = 0 if val < 160 else 255
                    img.setPixelColor(x, y, QColor(new_val, new_val, new_val))

        result_pix = QPixmap.fromImage(img)

        if self.is_flipped_h:
            from PySide6.QtGui import QTransform
            result_pix = result_pix.transformed(QTransform().scale(-1, 1))

        self._cached_pixmap = result_pix
        self._cached_transform_key = transform_key
        return result_pix

    def toggle_flip(self):
        self.is_flipped_h = not self.is_flipped_h
        self._cached_pixmap = None

    def toggle_grayscale(self):
        self.is_grayscale = not self.is_grayscale
        self._cached_pixmap = None

    def toggle_silhouette(self):
        self.is_silhouette = not self.is_silhouette
        self._cached_pixmap = None
