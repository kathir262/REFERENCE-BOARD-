"""Starts RefPad for Windows from source:  py -3.12 run.py [picture or PDF ...]"""
import sys
from pathlib import Path

root_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from refpad.main import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
