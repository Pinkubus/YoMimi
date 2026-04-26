"""Background worker that pre-loads OCR models on app startup.

Without this, the first image-open call blocks for tens of seconds (or
several minutes on the very first run while models download), which makes
the UI look frozen on the "Analyzing..." status.
"""
from __future__ import annotations

import sys
import traceback

from PySide6.QtCore import QObject, QThread, Signal

from ..ocr import OCREngine


class WarmupWorker(QObject):
    progress = Signal(str)
    finished = Signal()
    failed = Signal(str)

    def __init__(self, ocr: OCREngine) -> None:
        super().__init__()
        self.ocr = ocr

    def run(self) -> None:
        try:
            self.progress.emit("Loading OCR detector (EasyOCR)...")
            self.ocr._detector()  # noqa: SLF001
            self.progress.emit("Loading OCR recognizer (manga-ocr, ~450MB on first run)...")
            self.ocr._recognizer()  # noqa: SLF001
            self.progress.emit("OCR models ready.")
            self.finished.emit()
        except Exception as exc:
            tb = traceback.format_exc()
            print(f"[yomimi.warmup] FAILED:\n{tb}", flush=True, file=sys.stderr)
            self.failed.emit(f"{type(exc).__name__}: {exc}")


def start_warmup(parent: QObject, ocr: OCREngine,
                 on_progress, on_done, on_fail) -> tuple[QThread, WarmupWorker]:
    thread = QThread(parent)
    worker = WarmupWorker(ocr)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.progress.connect(on_progress)
    worker.finished.connect(on_done)
    worker.failed.connect(on_fail)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread, worker
