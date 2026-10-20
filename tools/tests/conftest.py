import os

os.environ.setdefault("OPENCV_IO_ENABLE_OPENEXR", "1")  # antes de qualquer import do cv2

import sys
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))
