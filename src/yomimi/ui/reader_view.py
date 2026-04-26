"""Reader widget: displays one page with hover/hotkey-revealed translations.

Hotkey assignment for the current page:
  - Sentences (full translation): digits 1-9, then 0  (so up to 10 per page)
  - Words (per-token gloss):       letters a-z         (up to 26 per page)
Each region is labeled in the top-right corner with its key.
"""
from __future__ import annotations

import string
from pathlib import Path
from typing import Optional

from PySide6.QtCore import Qt, QRectF, QPointF, QEvent
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QPainter,
    QPen,
    QPixmap,
)
from PySide6.QtWidgets import QToolTip, QWidget

from ..analyzer import AnalyzedRegion, PageResult


SENTENCE_KEYS = "1234567890"            # 10 sentences max
WORD_KEYS = string.ascii_lowercase       # 26 words max


class ReaderWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self._pixmap: QPixmap | None = None
        self._page: PageResult | None = None
        # Mapping: hotkey character -> ("sentence"|"word", region_index, word_index|None)
        self._hotkeys: dict[str, tuple[str, int, int | None]] = {}
        # When user presses a hotkey, we pin its tooltip until they press another or move.
        self._pinned: tuple[str, int, int | None] | None = None
        self.setStyleSheet("background: #111;")

    # -- public API ------------------------------------------------------
    def set_page(self, image_path: Path, page: PageResult | None) -> None:
        self._pixmap = QPixmap(str(image_path))
        self._page = page
        self._pinned = None
        self._rebuild_hotkeys()
        self.update()

    def clear(self) -> None:
        self._pixmap = None
        self._page = None
        self._hotkeys.clear()
        self._pinned = None
        self.update()

    # -- internals -------------------------------------------------------
    def _rebuild_hotkeys(self) -> None:
        self._hotkeys.clear()
        if not self._page:
            return
        # Sentence keys: one per region.
        for i, _ in enumerate(self._page.regions):
            if i >= len(SENTENCE_KEYS):
                break
            self._hotkeys[SENTENCE_KEYS[i]] = ("sentence", i, None)
        # Word keys: walk all words across all regions in order.
        wk = 0
        for ri, ar in enumerate(self._page.regions):
            for wi, _w in enumerate(ar.translation.words):
                if wk >= len(WORD_KEYS):
                    return
                self._hotkeys[WORD_KEYS[wk]] = ("word", ri, wi)
                wk += 1

    def _scale(self) -> tuple[float, float, float]:
        """Return (scale, offset_x, offset_y) for fitting pixmap into widget."""
        if not self._pixmap or self._pixmap.isNull():
            return 1.0, 0.0, 0.0
        pw, ph = self._pixmap.width(), self._pixmap.height()
        ww, wh = self.width(), self.height()
        s = min(ww / pw, wh / ph) if pw and ph else 1.0
        ox = (ww - pw * s) / 2
        oy = (wh - ph * s) / 2
        return s, ox, oy

    def _region_rect(self, ar: AnalyzedRegion) -> QRectF:
        s, ox, oy = self._scale()
        r = ar.region
        return QRectF(ox + r.x * s, oy + r.y * s, r.w * s, r.h * s)

    # -- painting --------------------------------------------------------
    def paintEvent(self, _event) -> None:  # noqa: N802 (Qt naming)
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#111"))
        if not self._pixmap or self._pixmap.isNull():
            painter.setPen(QColor("#888"))
            painter.drawText(self.rect(), Qt.AlignCenter,
                             "Open images or .zip files to begin (Ctrl+O)")
            return

        s, ox, oy = self._scale()
        painter.drawPixmap(
            QPointF(ox, oy),
            self._pixmap.scaled(
                int(self._pixmap.width() * s),
                int(self._pixmap.height() * s),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            ),
        )

        if not self._page:
            return

        # Draw region frames + hotkey labels.
        painter.setRenderHint(QPainter.Antialiasing, True)
        font = QFont("Segoe UI", 9, QFont.Bold)
        painter.setFont(font)

        sentence_pen = QPen(QColor(80, 200, 255, 200), 1.5)
        # Map region index -> sentence hotkey
        sentence_keys_for_region: dict[int, str] = {
            v[1]: k for k, v in self._hotkeys.items() if v[0] == "sentence"
        }
        # Map (region_idx, word_idx) -> word hotkey
        word_keys_for_region: dict[int, list[tuple[int, str]]] = {}
        for k, (kind, ri, wi) in self._hotkeys.items():
            if kind == "word" and wi is not None:
                word_keys_for_region.setdefault(ri, []).append((wi, k))

        for i, ar in enumerate(self._page.regions):
            rect = self._region_rect(ar)
            painter.setPen(sentence_pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(rect)

            # Sentence hotkey badge top-right.
            skey = sentence_keys_for_region.get(i)
            if skey:
                _draw_badge(painter, rect.topRight(), skey, QColor(80, 200, 255, 230))

            # Word hotkey badges along the right edge of the region, stacked.
            wks = sorted(word_keys_for_region.get(i, []))
            for j, (_wi, key) in enumerate(wks):
                anchor = QPointF(rect.right(), rect.top() + 18 + j * 16)
                _draw_badge(painter, anchor, key, QColor(255, 200, 80, 220), small=True)

    # -- input -----------------------------------------------------------
    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        if not self._page:
            return
        pos = event.position()
        for i, ar in enumerate(self._page.regions):
            if self._region_rect(ar).contains(pos):
                self._show_tooltip("sentence", i, None, event.globalPosition().toPoint())
                return
        QToolTip.hideText()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        key = event.text().lower()
        if key in self._hotkeys:
            kind, ri, wi = self._hotkeys[key]
            self._pinned = (kind, ri, wi)
            # Anchor pinned tooltip at the region's top-right in screen coords.
            ar = self._page.regions[ri]
            rect = self._region_rect(ar)
            global_pt = self.mapToGlobal(rect.topRight().toPoint())
            self._show_tooltip(kind, ri, wi, global_pt)
            event.accept()
            return
        if event.key() == Qt.Key_Escape:
            self._pinned = None
            QToolTip.hideText()
            event.accept()
            return
        super().keyPressEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        if not self._pinned:
            QToolTip.hideText()
        super().leaveEvent(event)

    # -- tooltip rendering ----------------------------------------------
    def _show_tooltip(self, kind: str, ri: int, wi: int | None, global_pt) -> None:
        if not self._page or ri >= len(self._page.regions):
            return
        ar = self._page.regions[ri]
        if kind == "word" and wi is not None and wi < len(ar.translation.words):
            w = ar.translation.words[wi]
            html = (
                f"<div style='font-family:Segoe UI;'>"
                f"<b style='font-size:14pt;'>{_esc(w.jp)}</b> "
                f"<span style='color:#888;'>[{_esc(w.reading)}]</span><br>"
                f"<span style='font-size:11pt;'>{_esc(w.meaning)}</span>"
                f"</div>"
            )
        else:
            t = ar.translation
            words_html = " ".join(
                f"<span style='color:#fa8;'>{_esc(w.jp)}</span>"
                f"<span style='color:#888;font-size:8pt;'>[{_esc(w.reading)}]</span>"
                for w in t.words
            )
            html = (
                f"<div style='font-family:Segoe UI; max-width:420px;'>"
                f"<div style='font-size:13pt;'>{_esc(t.original)}</div>"
                f"<div style='color:#888; margin:4px 0;'>{words_html}</div>"
                f"<div style='font-size:11pt;'><b>{_esc(t.translation)}</b></div>"
                f"</div>"
            )
        QToolTip.showText(global_pt, html, self)


def _draw_badge(painter: QPainter, anchor: QPointF, text: str,
                color: QColor, small: bool = False) -> None:
    size = 14 if small else 18
    rect = QRectF(anchor.x() - size, anchor.y() - size / 2, size, size)
    painter.setBrush(QBrush(color))
    painter.setPen(QPen(QColor(0, 0, 0, 180), 1))
    painter.drawRoundedRect(rect, 3, 3)
    painter.setPen(QColor(20, 20, 20))
    f = painter.font()
    old_size = f.pointSize()
    f.setPointSize(7 if small else 9)
    painter.setFont(f)
    painter.drawText(rect, Qt.AlignCenter, text)
    f.setPointSize(old_size)
    painter.setFont(f)


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
