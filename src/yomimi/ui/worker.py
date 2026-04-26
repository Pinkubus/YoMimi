"""Background worker that runs OCR + translation off the UI thread."""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal

from ..analyzer import PageResult, analyze_page
from ..ocr import OCREngine
from ..translator import Translator


class AnalysisWorker(QObject):
    finished = Signal(object)   # PageResult
    failed = Signal(str)

    def __init__(self, image_path: Path, ocr: OCREngine, translator: Translator) -> None:
        super().__init__()
        self.image_path = image_path
        self.ocr = ocr
        self.translator = translator

    def run(self) -> None:
        try:
            print(f"[yomimi.worker] Starting analysis of {self.image_path.name}",
                  flush=True, file=sys.stderr)
            result = analyze_page(self.image_path, self.ocr, self.translator)
            print(f"[yomimi.worker] Done: {len(result.regions)} regions",
                  flush=True, file=sys.stderr)
            self.finished.emit(result)
        except Exception as exc:  # surface to UI rather than crashing
            tb = traceback.format_exc()
            print(f"[yomimi.worker] FAILED:\n{tb}", flush=True, file=sys.stderr)
            self.failed.emit(f"{type(exc).__name__}: {exc}")


def start_analysis(parent: QObject, image_path: Path, ocr: OCREngine,
                   translator: Translator, on_done, on_fail) -> tuple[QThread, AnalysisWorker]:
    thread = QThread(parent)
    worker = AnalysisWorker(image_path, ocr, translator)
    worker.moveToThread(thread)
    thread.started.connect(worker.run)
    worker.finished.connect(on_done)
    worker.failed.connect(on_fail)
    worker.finished.connect(thread.quit)
    worker.failed.connect(thread.quit)
    thread.finished.connect(worker.deleteLater)
    thread.finished.connect(thread.deleteLater)
    thread.start()
    return thread, worker
