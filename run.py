"""Tiny launcher so you can run `python run.py` from the project root."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

from yomimi.__main__ import main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(main())
