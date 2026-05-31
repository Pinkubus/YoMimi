"""Reader widget: displays one page with hover/hotkey-revealed translations.

Interaction model:
  * Press a digit (1-0) or click a region -> SELECT that sentence; first word
    becomes the highlighted word. Hold the digit (or hold the mouse button)
    to see the full sentence translation.
  * Once a sentence is selected, the arrow keys move the highlighted word
    through the sentence in reading order. The selected word's gloss is shown
    persistently until you select something else or press Esc.
  * Press a letter (a-z) to peek at a specific word's gloss while held.
  * Esc clears any selection.
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

SELECT_COLOR = QColor(255, 230, 80, 240)
REGION_COLOR = QColor(80, 200, 255, 220)
WORD_BADGE_COLOR = QColor(255, 200, 80, 225)
SENTENCE_BADGE_COLOR = QColor(80, 200, 255, 235)


class ReaderWidget(QWidget):
    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)
        self._pixmap: QPixmap | None = None
        self._page: PageResult | None = None
        # Mapping: hotkey character -> ("sentence"|"word", region_index, word_index|None)
        self._hotkeys: dict[str, tuple[str, int, int | None]] = {}
        # Currently held hotkey character (None when nothing is held).
        self._held_key: str | None = None
        # Sticky selection driven by digit press / click + arrow keys.
        self._sel_region: int | None = None
        self._sel_word: int | None = None
        self.setStyleSheet("background: #111;")

    # -- public API ------------------------------------------------------
    def set_page(self, image_path: Path, page: PageResult | None) -> None:
        self._pixmap = QPixmap(str(image_path))
        self._page = page
        self._held_key = None
        self._sel_region = None
        self._sel_word = None
        self._rebuild_hotkeys()
        self.update()

    def clear(self) -> None:
        self._pixmap = None
        self._page = None
        self._hotkeys.clear()
        self._held_key = None
        self._sel_region = None
        self._sel_word = None
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

        # Draw region markers + hotkey labels.
        painter.setRenderHint(QPainter.Antialiasing, True)
        font = QFont("Segoe UI", 9, QFont.Bold)
        painter.setFont(font)

        # Map region index -> sentence hotkey
        sentence_keys_for_region: dict[int, str] = {
            v[1]: k for k, v in self._hotkeys.items() if v[0] == "sentence"
        }
        # Map region index -> ordered list of (word_idx, hotkey)
        word_keys_for_region: dict[int, list[tuple[int, str]]] = {}
        for k, (kind, ri, wi) in self._hotkeys.items():
            if kind == "word" and wi is not None:
                word_keys_for_region.setdefault(ri, []).append((wi, k))

        # Choose a badge column side per region: place to the right of the
        # region if there's room, otherwise to the left. Keeps badges off the
        # text itself.
        widget_right = float(self.width())
        BADGE_W = 18
        BADGE_H = 18
        BADGE_GAP = 2

        for i, ar in enumerate(self._page.regions):
            rect = self._region_rect(ar)

            is_selected = (i == self._sel_region)
            bracket_color = SELECT_COLOR if is_selected else REGION_COLOR
            _draw_corner_brackets(painter, rect, bracket_color)

            # Decide which side to stack badges on.
            place_right = (widget_right - rect.right()) >= (BADGE_W + 6)
            x = rect.right() + 4 if place_right else rect.left() - BADGE_W - 4

            y = rect.top()
            # Sentence badge first.
            skey = sentence_keys_for_region.get(i)
            if skey:
                color = SELECT_COLOR if is_selected else SENTENCE_BADGE_COLOR
                _draw_badge_at(painter, x, y, BADGE_W, BADGE_H, skey, color)
                y += BADGE_H + BADGE_GAP

            # Word badges below.
            for wi, key in sorted(word_keys_for_region.get(i, [])):
                color = (
                    SELECT_COLOR
                    if (is_selected and wi == self._sel_word)
                    else WORD_BADGE_COLOR
                )
                _draw_badge_at(painter, x, y, BADGE_W - 4, BADGE_H - 4, key,
                               color, small=True)
                y += (BADGE_H - 4) + BADGE_GAP

    # -- input -----------------------------------------------------------
    def mouseMoveEvent(self, event) -> None:  # noqa: N802
        # Hover alone no longer reveals translations -- you must hold the
        # mouse button or a hotkey. Keep the handler so we can reposition a
        # held-mouse tooltip if the cursor moves between regions.
        if not self._page or not (event.buttons() & Qt.LeftButton):
            return
        pos = event.position()
        for i, ar in enumerate(self._page.regions):
            if self._region_rect(ar).contains(pos):
                self._show_sentence_tooltip(i, event.globalPosition().toPoint())
                return
        QToolTip.hideText()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton and self._page:
            pos = event.position()
            for i, ar in enumerate(self._page.regions):
                if self._region_rect(ar).contains(pos):
                    self._select_region(i)
                    self._show_sentence_tooltip(
                        i, event.globalPosition().toPoint())
                    event.accept()
                    return
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        if event.button() == Qt.LeftButton:
            # Drop the sentence tooltip and revert to the selected-word view.
            self._show_selected_word_tooltip()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        # Auto-repeat is suppressed for both hold and arrow nav -- keeps the
        # tooltip stable and prevents the selection sprinting away.
        if event.isAutoRepeat():
            event.accept()
            return

        # Arrow-key word navigation operates on the current selection.
        if event.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down):
            if self._sel_region is not None and self._move_selection(event.key()):
                self._show_selected_word_tooltip()
                event.accept()
                return
            # Fall through if no selection -- lets parent shortcuts (none
            # currently) handle the arrow.
            super().keyPressEvent(event)
            return

        if event.key() == Qt.Key_Escape:
            self._held_key = None
            self._sel_region = None
            self._sel_word = None
            QToolTip.hideText()
            self.update()
            event.accept()
            return

        key = event.text().lower()
        if key in self._hotkeys:
            kind, ri, wi = self._hotkeys[key]
            self._held_key = key
            anchor = self._tooltip_anchor(ri)
            if kind == "sentence":
                self._select_region(ri)
                self._show_sentence_tooltip(ri, anchor)
            else:
                self._show_word_tooltip(ri, wi or 0, anchor)
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:  # noqa: N802
        if event.isAutoRepeat():
            event.accept()
            return
        key = event.text().lower()
        if self._held_key is not None and key == self._held_key:
            self._held_key = None
            # Revert to the persistent selected-word tooltip if any.
            self._show_selected_word_tooltip()
            event.accept()
            return
        super().keyReleaseEvent(event)

    def leaveEvent(self, event: QEvent) -> None:  # noqa: N802
        if self._held_key is None and self._sel_region is None:
            QToolTip.hideText()
        super().leaveEvent(event)

    # -- selection helpers ----------------------------------------------
    def _select_region(self, ri: int) -> None:
        self._sel_region = ri
        ar = self._page.regions[ri] if self._page else None
        self._sel_word = 0 if ar and ar.translation.words else None
        self.update()

    def _move_selection(self, qt_key: int) -> bool:
        """Advance/rewind the selected word. Returns True if it moved.

        Words have no per-token bounding boxes (they come from Claude's
        tokenization of the merged sentence), so arrow keys map to reading
        order: forward for the natural "next-line" direction of the script,
        backward for the opposite.
        """
        if self._sel_region is None or self._page is None:
            return False
        ar = self._page.regions[self._sel_region]
        n = len(ar.translation.words)
        if n == 0:
            return False
        if ar.region.vertical:
            forward = {Qt.Key_Down, Qt.Key_Left}
            backward = {Qt.Key_Up, Qt.Key_Right}
        else:
            forward = {Qt.Key_Right, Qt.Key_Down}
            backward = {Qt.Key_Left, Qt.Key_Up}
        if qt_key in forward:
            delta = 1
        elif qt_key in backward:
            delta = -1
        else:
            return False
        cur = self._sel_word if self._sel_word is not None else 0
        new = max(0, min(n - 1, cur + delta))
        if new == cur:
            return False
        self._sel_word = new
        self.update()
        return True

    def _tooltip_anchor(self, ri: int):
        ar = self._page.regions[ri]
        rect = self._region_rect(ar)
        return self.mapToGlobal(rect.topRight().toPoint())

    # -- tooltip rendering ----------------------------------------------
    def _show_selected_word_tooltip(self) -> None:
        if self._sel_region is None or self._sel_word is None:
            QToolTip.hideText()
            return
        self._show_word_tooltip(
            self._sel_region, self._sel_word, self._tooltip_anchor(self._sel_region)
        )

    def _show_word_tooltip(self, ri: int, wi: int, global_pt) -> None:
        if not self._page or ri >= len(self._page.regions):
            return
        ar = self._page.regions[ri]
        if wi >= len(ar.translation.words):
            return
        w = ar.translation.words[wi]
        html = (
            f"<div style='font-family:Segoe UI;'>"
            f"<b style='font-size:14pt;'>{_esc(w.jp)}</b> "
            f"<span style='color:#888;'>[{_esc(w.reading)}]</span><br>"
            f"<span style='font-size:11pt;'>{_esc(w.meaning)}</span>"
            f"</div>"
        )
        QToolTip.showText(global_pt, html, self)

    def _show_sentence_tooltip(self, ri: int, global_pt) -> None:
        if not self._page or ri >= len(self._page.regions):
            return
        t = self._page.regions[ri].translation
        # Vertical key-value list, one word per row.
        rows = []
        for w in t.words:
            rows.append(
                "<tr>"
                f"<td style='padding:1px 8px 1px 0; color:#fa8;'>"
                f"<b>{_esc(w.jp)}</b></td>"
                f"<td style='padding:1px 8px 1px 0; color:#888;'>"
                f"[{_esc(w.reading)}]</td>"
                f"<td style='padding:1px 0;'>{_esc(w.meaning)}</td>"
                "</tr>"
            )
        words_table = (
            f"<table style='border-collapse:collapse;'>{''.join(rows)}</table>"
            if rows else ""
        )
        html = (
            f"<div style='font-family:Segoe UI; max-width:520px;'>"
            f"<div style='font-size:13pt;'>{_esc(t.original)}</div>"
            f"<div style='margin:4px 0;'>{words_table}</div>"
            f"<div style='font-size:11pt; margin-top:4px;'>"
            f"<b>{_esc(t.translation)}</b></div>"
            f"</div>"
        )
        QToolTip.showText(global_pt, html, self)


def _draw_badge_at(painter: QPainter, x: float, y: float, w: float, h: float,
                   text: str, color: QColor, small: bool = False) -> None:
    rect = QRectF(x, y, w, h)
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


def _draw_corner_brackets(painter: QPainter, rect: QRectF, color: QColor) -> None:
    """Draw four small L-shaped corner marks instead of a full rectangle.

    Keeps the visual indication of the region but avoids the box-on-box clutter
    you get when OCR regions overlap or sit very close together.
    """
    painter.setBrush(Qt.NoBrush)
    painter.setPen(QPen(color, 1.5))
    L = min(8.0, rect.width() / 3, rect.height() / 3)
    x1, y1 = rect.left(), rect.top()
    x2, y2 = rect.right(), rect.bottom()
    painter.drawLine(QPointF(x1, y1), QPointF(x1 + L, y1))
    painter.drawLine(QPointF(x1, y1), QPointF(x1, y1 + L))
    painter.drawLine(QPointF(x2, y1), QPointF(x2 - L, y1))
    painter.drawLine(QPointF(x2, y1), QPointF(x2, y1 + L))
    painter.drawLine(QPointF(x1, y2), QPointF(x1 + L, y2))
    painter.drawLine(QPointF(x1, y2), QPointF(x1, y2 - L))
    painter.drawLine(QPointF(x2, y2), QPointF(x2 - L, y2))
    painter.drawLine(QPointF(x2, y2), QPointF(x2, y2 - L))


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
