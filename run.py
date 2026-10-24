"""
Run RefPad launcher.
"""
import sys
from pathlib import Path

# Ensure refpad package is importable
root_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from refpad.main import main

if __name__ == "__main__":
    main()
