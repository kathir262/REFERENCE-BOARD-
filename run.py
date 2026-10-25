"""
Run RefPad launcher.
"""
import sys
# Prevent PyMuPDF layout module from attempting to load unbundled ONNX models in frozen mode
sys.modules['pymupdf.layout'] = None

from pathlib import Path

# Ensure refpad package is importable
root_dir = Path(__file__).resolve().parent
if str(root_dir) not in sys.path:
    sys.path.insert(0, str(root_dir))

from refpad.main import main

if __name__ == "__main__":
    main()
