"""Test set-up: a throw-away data folder and an off-screen Qt, so tests never touch your real board."""
import os
import sys
import tempfile
from pathlib import Path

os.environ["REFPAD_DATA_DIR"] = tempfile.mkdtemp(prefix="refpad-test-")
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="session")
def app():
    a = QApplication.instance() or QApplication([])
    from refpad.core import images
    images.init()
    images.init_cache()
    return a
