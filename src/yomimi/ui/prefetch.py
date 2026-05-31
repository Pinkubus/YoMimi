"""Prefetch manager: runs OCR + translation for pages serially in a background
thread, with the currently-viewed page always promoted to the head of the queue.

We use a single worker thread because manga-ocr's torch model isn't safe to
call concurrently across threads.

Cross-thread calls go through Qt signals (auto-queued), which marshal arbitrary
Python objects cleanly.
"""
from __future__ import annotations

import sys
import traceback
from collections import deque
from pathlib import Path

from PySide6.QtCore import QObject, QThread, Signal, Slot

from ..analyzer import analyze_page
from ..ocr import OCREngine
from ..translator import Translator


def _log(msg: str) -> None:
    print(f"[yomimi.prefetch] {msg}", flush=True, file=sys.stderr)


class _PrefetchWorker(QObject):
    page_ready = Signal(object)
    page_failed = Signal(object, str)
    idle = Signal()

    def __init__(self, ocr: OCREngine, translator_factory) -> None:
        super().__init__()
        self.ocr = ocr
        self._translator_factory = translator_factory
        self._translator: Translator | None = None
        self._queue: deque[Path] = deque()
        self._done: set[Path] = set()
        self._stopping = False

    @Slot(object)
    def on_enqueue(self, path: Path) -> None:
        if path in self._done or path in self._queue:
            return
        self._queue.append(path)
        _log(f"queued {path.name} (depth={len(self._queue)})")
        self._pump()

    @Slot(object)
    def on_prioritize(self, path: Path) -> None:
        if path in self._done:
            return
        try:
            self._queue.remove(path)
        except ValueError:
            pass
        self._queue.appendleft(path)
        _log(f"prioritized {path.name} (depth={len(self._queue)})")
        self._pump()

    @Slot(object)
    def on_replace_queue(self, paths: list) -> None:
        self._queue.clear()
        for p in paths:
            if p not in self._done:
                self._queue.append(p)
        _log(f"replaced queue (depth={len(self._queue)})")
        self._pump()

    @Slot()
    def on_stop(self) -> None:
        self._stopping = True
        self._queue.clear()

    def _pump(self) -> None:
        while self._queue and not self._stopping:
            path = self._queue.popleft()
            if path in self._done:
                continue
            try:
                if self._translator is None:
                    self._translator = self._translator_factory()
                _log(f"analyzing {path.name}")
                result = analyze_page(path, self.ocr, self._translator)
                self._done.add(path)
                self.page_ready.emit(result)
            except Exception as exc:
                tb = traceback.format_exc()
                _log(f"FAILED on {path.name}:\n{tb}")
                self.page_failed.emit(path, f"{type(exc).__name__}: {exc}")
        if not self._queue:
            self.idle.emit()


class PrefetchManager(QObject):
    page_ready = Signal(object)
    page_failed = Signal(object, str)
    idle = Signal()

    # Cross-thread request signals (auto-queued to worker thread).
    _enqueue = Signal(object)
    _prioritize = Signal(object)
    _replace_queue = Signal(object)
    _stop = Signal()

    def __init__(self, parent: QObject, ocr: OCREngine, translator_factory) -> None:
        super().__init__(parent)
        self._thread = QThread(parent)
        self._worker = _PrefetchWorker(ocr, translator_factory)
        self._worker.moveToThread(self._thread)

        self._enqueue.connect(self._worker.on_enqueue)
        self._prioritize.connect(self._worker.on_prioritize)
        self._replace_queue.connect(self._worker.on_replace_queue)
        self._stop.connect(self._worker.on_stop)

        self._worker.page_ready.connect(self.page_ready)
        self._worker.page_failed.connect(self.page_failed)
        self._worker.idle.connect(self.idle)

        self._thread.start()

    def request(self, path: Path, priority: bool = False) -> None:
        if priority:
            self._prioritize.emit(path)
        else:
            self._enqueue.emit(path)

    def set_pages(self, paths: list[Path]) -> None:
        self._replace_queue.emit(list(paths))

    def shutdown(self) -> None:
        self._stop.emit()
        self._thread.quit()
        self._thread.wait(2000)
