import sys
from pathlib import Path

base_dir = Path(__file__).resolve().parent.parent
src_dir = base_dir / "src"
if str(src_dir) not in sys.path:
    sys.path.insert(0, str(src_dir))
if str(base_dir) not in sys.path:
    sys.path.insert(0, str(base_dir))
