"""OCR pipeline: detect text regions with EasyOCR, recognize with manga-ocr.

Why two engines?
- EasyOCR's `detect()` reliably finds Japanese text bounding boxes, including
  vertical columns, but its recognition for stylized manga text is mediocre.
- manga-ocr is purpose-built for single-region manga text recognition, giving
  much higher quality strings, but is a recognizer only -- it does not detect
  regions. So we feed each EasyOCR-detected crop into manga-ocr.

Models are downloaded on first use (~500 MB-1 GB total).
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


@dataclass
class TextRegion:
    # Axis-aligned bounding box in image pixel coords.
    x: int
    y: int
    w: int
    h: int
    text: str
    # Heuristic flag: vertical reading direction (taller than wide and narrow).
    vertical: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TextRegion":
        return cls(**d)


class OCREngine:
    """Lazy-loads heavy ML models on first call."""

    def __init__(self) -> None:
        self._reader = None       # easyocr.Reader
        self._mocr = None         # manga_ocr.MangaOcr

    # --- lazy loaders ---------------------------------------------------
    def _detector(self):
        if self._reader is None:
            import easyocr  # heavy import
            # Japanese only; English usually rides along OK in most builds,
            # but mixing causes warnings. For pure Japanese pages this is fine.
            self._reader = easyocr.Reader(["ja", "en"], gpu=False, verbose=False)
        return self._reader

    def _recognizer(self):
        if self._mocr is None:
            from manga_ocr import MangaOcr
            self._mocr = MangaOcr()
        return self._mocr

    # --- public API -----------------------------------------------------
    def analyze(self, image_path: Path) -> list[TextRegion]:
        img = Image.open(image_path).convert("RGB")
        arr = np.array(img)

        reader = self._detector()
        # detect() returns (horizontal_boxes, free_form_boxes).
        h_boxes, f_boxes = reader.detect(arr)
        regions: list[TextRegion] = []

        # horizontal_boxes are [x_min, x_max, y_min, y_max].
        flat_h = h_boxes[0] if h_boxes else []
        for box in flat_h:
            x_min, x_max, y_min, y_max = (int(v) for v in box)
            regions.append(self._recognize_crop(img, x_min, y_min, x_max, y_max))

        # free_form_boxes are 4 corner points; convert to axis-aligned.
        flat_f = f_boxes[0] if f_boxes else []
        for poly in flat_f:
            xs = [int(p[0]) for p in poly]
            ys = [int(p[1]) for p in poly]
            regions.append(self._recognize_crop(img, min(xs), min(ys), max(xs), max(ys)))

        # Drop empty / dedupe near-identical boxes.
        regions = [r for r in regions if r.text.strip()]
        regions = _dedupe(regions)
        return regions

    def _recognize_crop(self, img: Image.Image, x1: int, y1: int, x2: int, y2: int) -> TextRegion:
        # Clamp + tiny pad to give the recognizer breathing room.
        W, H = img.size
        pad = 4
        x1 = max(0, x1 - pad); y1 = max(0, y1 - pad)
        x2 = min(W, x2 + pad); y2 = min(H, y2 + pad)
        crop = img.crop((x1, y1, x2, y2))
        try:
            text = self._recognizer()(crop).strip()
        except Exception:
            text = ""
        w, h = x2 - x1, y2 - y1
        vertical = h > w * 1.5
        return TextRegion(x=x1, y=y1, w=w, h=h, text=text, vertical=vertical)


def _dedupe(regions: list[TextRegion]) -> list[TextRegion]:
    """Remove regions whose bbox heavily overlaps an already-kept one."""
    kept: list[TextRegion] = []
    for r in regions:
        if any(_iou(r, k) > 0.6 for k in kept):
            continue
        kept.append(r)
    return kept


def _iou(a: TextRegion, b: TextRegion) -> float:
    ax2, ay2 = a.x + a.w, a.y + a.h
    bx2, by2 = b.x + b.w, b.y + b.h
    ix1, iy1 = max(a.x, b.x), max(a.y, b.y)
    ix2, iy2 = min(ax2, bx2), min(ay2, by2)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    union = a.w * a.h + b.w * b.h - inter
    return inter / union
