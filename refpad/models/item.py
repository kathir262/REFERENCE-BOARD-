"""
Reference Item representation for files and PDF pages.
Full BeeRef transforms: Flip H/V, 90° Rotations, Crop, Invert, Grayscale, Opacity.
"""
from dataclasses import dataclass
from typing import Optional, Tuple
from pathlib import Path
from PySide6.QtGui import QPixmap, QImage, QColor, QTransform
from PySide6.QtCore import Qt, QRect

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
    is_flipped_v: bool = False
    rotation: float = 0.0
    is_grayscale: bool = False
    is_inverted: bool = False
    is_silhouette: bool = False
    opacity: float = 1.0
    crop_rect: Optional[Tuple[int, int, int, int]] = None  # x, y, w, h in base pixmap coords
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
        """Returns the pixmap with active BeeRef filters and transforms."""
        crop_key = f"{self.crop_rect}" if self.crop_rect else "none"
        transform_key = (
            f"{self.is_flipped_h}_{self.is_flipped_v}_{self.rotation}_"
            f"{self.is_grayscale}_{self.is_inverted}_{self.is_silhouette}_{crop_key}"
        )
        if self._cached_pixmap is not None and self._cached_transform_key == transform_key:
            return self._cached_pixmap

        base = self.get_base_pixmap()
        if not base or base.isNull():
            return None

        # Apply crop if defined
        if self.crop_rect:
            x, y, w, h = self.crop_rect
            base = base.copy(QRect(x, y, w, h))

        # Convert to QImage for pixel-level color filters
        img = base.toImage()

        if self.is_grayscale or self.is_silhouette:
            img = img.convertToFormat(QImage.Format.Format_Grayscale8)

        if self.is_inverted:
            img.invertPixels()

        if self.is_silhouette:
            img = img.convertToFormat(QImage.Format.Format_RGB32)
            for y in range(img.height()):
                for x in range(img.width()):
                    c = img.pixelColor(x, y)
                    val = c.red()
                    new_val = 0 if val < 160 else 255
                    img.setPixelColor(x, y, QColor(new_val, new_val, new_val))

        result_pix = QPixmap.fromImage(img)

        # Apply geometric transforms (rotation and flips)
        t = QTransform()
        if self.rotation != 0:
            t.rotate(self.rotation)
        if self.is_flipped_h or self.is_flipped_v:
            t.scale(-1 if self.is_flipped_h else 1, -1 if self.is_flipped_v else 1)

        if not t.isIdentity():
            result_pix = result_pix.transformed(t, Qt.TransformationMode.SmoothTransformation)

        self._cached_pixmap = result_pix
        self._cached_transform_key = transform_key
        return result_pix

    def toggle_flip(self):
        """Legacy alias for horizontal flip."""
        self.toggle_flip_h()

    def toggle_flip_h(self):
        self.is_flipped_h = not self.is_flipped_h
        self._cached_pixmap = None

    def toggle_flip_v(self):
        self.is_flipped_v = not self.is_flipped_v
        self._cached_pixmap = None

    def rotate_cw(self):
        self.rotation = (self.rotation + 90) % 360
        self._cached_pixmap = None

    def rotate_ccw(self):
        self.rotation = (self.rotation - 90) % 360
        self._cached_pixmap = None

    def toggle_grayscale(self):
        self.is_grayscale = not self.is_grayscale
        self._cached_pixmap = None

    def toggle_invert(self):
        self.is_inverted = not self.is_inverted
        self._cached_pixmap = None

    def toggle_silhouette(self):
        self.is_silhouette = not self.is_silhouette
        self._cached_pixmap = None

    def reset_crop(self):
        self.crop_rect = None
        self._cached_pixmap = None

    def reset_transforms(self):
        self.is_flipped_h = False
        self.is_flipped_v = False
        self.rotation = 0.0
        self.crop_rect = None
        self._cached_pixmap = None
