"""Main application window: file open, page navigation, status bar."""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QLabel,
    QMainWindow,
    QMessageBox,
    QStatusBar,
    QToolBar,
)

from ..analyzer import PageResult
from ..ocr import OCREngine
from ..passive import PassiveMode
from ..translator import Translator
from ..zip_loader import BatchLoader
from .reader_view import ReaderWidget
from .worker import start_analysis


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("YoMimi - Japanese Reading Assistant")
        self.resize(1200, 900)

        self.loader = BatchLoader()
        self.ocr = OCREngine()
        self.translator: Translator | None = None  # built lazily on first analyze
        self.passive = PassiveMode()

        self.pages: list[Path] = []
        self.index: int = -1
        self.results: dict[Path, PageResult] = {}
        self._active_thread = None

        self.reader = ReaderWidget(self)
        self.setCentralWidget(self.reader)

        self._build_actions()
        self._build_toolbar()
        self.setStatusBar(QStatusBar(self))
        self.status_label = QLabel("Ready. Open files (Ctrl+O) to begin.")
        self.statusBar().addWidget(self.status_label)

    # -- actions / toolbar ---------------------------------------------
    def _build_actions(self) -> None:
        self.act_open = QAction("&Open files...", self)
        self.act_open.setShortcut(QKeySequence.Open)
        self.act_open.triggered.connect(self.open_files)

        self.act_prev = QAction("Previous page", self)
        self.act_prev.setShortcut(Qt.Key_Left)
        self.act_prev.triggered.connect(lambda: self.show_page(self.index - 1))

        self.act_next = QAction("Next page", self)
        self.act_next.setShortcut(Qt.Key_Right)
        self.act_next.triggered.connect(lambda: self.show_page(self.index + 1))

        self.act_passive = QAction("Toggle passive mode", self)
        self.act_passive.setCheckable(True)
        self.act_passive.triggered.connect(self.toggle_passive)

        self.addAction(self.act_open)
        self.addAction(self.act_prev)
        self.addAction(self.act_next)

    def _build_toolbar(self) -> None:
        tb = QToolBar("Main", self)
        tb.addAction(self.act_open)
        tb.addSeparator()
        tb.addAction(self.act_prev)
        tb.addAction(self.act_next)
        tb.addSeparator()
        tb.addAction(self.act_passive)
        self.addToolBar(tb)

    # -- file load ------------------------------------------------------
    def open_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Open images and/or .zip files",
            "",
            "Images and Archives (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.tif *.tiff *.zip)",
        )
        if not paths:
            return
        self.pages = self.loader.load(paths)
        self.results.clear()
        if not self.pages:
            QMessageBox.information(self, "YoMimi", "No images found in the selection.")
            return
        self.show_page(0)

    # -- navigation -----------------------------------------------------
    def show_page(self, idx: int) -> None:
        if not self.pages:
            return
        idx = max(0, min(idx, len(self.pages) - 1))
        self.index = idx
        path = self.pages[idx]
        self._set_status(f"Page {idx+1}/{len(self.pages)}  -  {path.name}")
        # Show image immediately, even before analysis completes.
        self.reader.set_page(path, self.results.get(path))
        if path not in self.results:
            self._kick_analysis(path)

    def _kick_analysis(self, path: Path) -> None:
        if self.translator is None:
            try:
                self.translator = Translator()
            except Exception as exc:
                QMessageBox.critical(self, "YoMimi", f"Translator init failed: {exc}")
                return
        self._set_status(f"Analyzing {path.name}... (first run downloads ML models)")
        self._active_thread, _ = start_analysis(
            self, path, self.ocr, self.translator,
            on_done=self._on_analyzed,
            on_fail=self._on_failed,
        )

    def _on_analyzed(self, result: PageResult) -> None:
        self.results[result.image_path] = result
        # If this result is for the page currently displayed, refresh.
        if 0 <= self.index < len(self.pages) and self.pages[self.index] == result.image_path:
            self.reader.set_page(result.image_path, result)
            self._set_status(
                f"Page {self.index+1}/{len(self.pages)}  -  {result.image_path.name}  "
                f"-  {len(result.regions)} regions"
            )

    def _on_failed(self, msg: str) -> None:
        self._set_status(f"Analysis failed: {msg}")
        QMessageBox.warning(self, "YoMimi", f"Analysis failed:\n{msg}")

    # -- passive --------------------------------------------------------
    def toggle_passive(self) -> None:
        on = self.passive.toggle()
        self.act_passive.setChecked(on)
        QMessageBox.information(self, "YoMimi", self.passive.status())

    # -- helpers --------------------------------------------------------
    def _set_status(self, text: str) -> None:
        self.status_label.setText(text)

    def closeEvent(self, event) -> None:  # noqa: N802
        self.loader.cleanup()
        super().closeEvent(event)
