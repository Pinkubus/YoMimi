"""YoMimi entry point: `python -m yomimi`."""
from __future__ import annotations

import os
import sys

# Quiet down HuggingFace Hub on Windows (symlinks require Developer Mode).
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
# Suppress transformers' chatty logging.
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

from PySide6.QtWidgets import QApplication

from .ui.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("YoMimi")
    win = MainWindow()
    win.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
