"""
Source Ingestion Manager: handles Folder crawling and PDF page extraction.
"""
import sys
import os
import random
from pathlib import Path
from typing import List, Optional
from refpad.models.item import RefItem

# Prevent PyMuPDF layout module from attempting to load unbundled ONNX models in frozen mode
sys.modules['pymupdf.layout'] = None

try:
    import pymupdf
except ImportError:
    import fitz as pymupdf

SUPPORTED_IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.jfif', '.tif', '.tiff'}

class SourceManager:
    def __init__(self):
        self.items: List[RefItem] = []
        self.current_source_description: str = "No sources loaded"

    def load_folder(self, folder_path: str, recursive: bool = True, shuffle: bool = False) -> List[RefItem]:
        """Scan a folder for image files and load RefItems."""
        p = Path(folder_path)
        if not p.exists() or not p.is_dir():
            return []

        loaded: List[RefItem] = []
        pattern = "**/*" if recursive else "*"
        for file in p.glob(pattern):
            if not file.is_file():
                continue
            if file.name.startswith(('~', '.')):
                continue
            ext = file.suffix.lower()
            if ext in SUPPORTED_IMAGE_EXTENSIONS:
                loaded.append(RefItem(
                    source_type='file',
                    file_path=str(file.resolve()),
                    name=file.name
                ))
            elif ext == '.pdf':
                try:
                    doc = pymupdf.open(str(file.resolve()))
                    page_count = len(doc)
                    doc.close()
                    for idx in range(page_count):
                        loaded.append(RefItem(
                            source_type='pdf',
                            file_path=str(file.resolve()),
                            page_num=idx,
                            name=f"{file.stem} (p. {idx + 1})"
                        ))
                except Exception as e:
                    print(f"Error reading PDF {file}: {e}")

        if shuffle:
            random.shuffle(loaded)
        else:
            loaded.sort(key=lambda x: (x.file_path.lower(), x.page_num, x.name.lower()))

        self.items = loaded
        self.current_source_description = f"Folder: {p.name} ({len(loaded)} images)"
        return self.items

    def load_pdf(self, pdf_path: str) -> List[RefItem]:
        """Load all pages of a PDF document as RefItems."""
        p = Path(pdf_path)
        if not p.exists() or not p.is_file():
            return []

        loaded: List[RefItem] = []
        try:
            doc = pymupdf.open(str(p.resolve()))
            page_count = len(doc)
            doc.close()
            for idx in range(page_count):
                loaded.append(RefItem(
                    source_type='pdf',
                    file_path=str(p.resolve()),
                    page_num=idx,
                    name=f"{p.stem} - Page {idx + 1}"
                ))
            self.items = loaded
            self.current_source_description = f"PDF: {p.name} ({page_count} pages)"
        except Exception as e:
            print(f"Failed to read PDF {pdf_path}: {e}")
            return []

        return self.items

    def add_files(self, file_paths: List[str]) -> List[RefItem]:
        """Add individual files or PDFs to the current collection."""
        new_items = []
        for fp in file_paths:
            p = Path(fp)
            if not p.exists():
                continue
            if p.suffix.lower() == '.pdf':
                try:
                    doc = pymupdf.open(str(p.resolve()))
                    for idx in range(len(doc)):
                        new_items.append(RefItem(
                            source_type='pdf',
                            file_path=str(p.resolve()),
                            page_num=idx,
                            name=f"{p.stem} - Page {idx + 1}"
                        ))
                    doc.close()
                except Exception as e:
                    print(f"Error loading {fp}: {e}")
            elif p.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
                new_items.append(RefItem(
                    source_type='file',
                    file_path=str(p.resolve()),
                    name=p.name
                ))
        self.items.extend(new_items)
        return new_items

    def shuffle_items(self):
        random.shuffle(self.items)
