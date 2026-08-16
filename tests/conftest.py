import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE_SERVICE = ROOT / "services" / "archive"
for path in (str(ROOT), str(ARCHIVE_SERVICE)):
    if path not in sys.path:
        sys.path.insert(0, path)
