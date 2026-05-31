"""Per-page analysis result, combining OCR regions with translations.

Persisted to the on-disk cache so reopening images is instant.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import cache
from .ocr import OCREngine, TextRegion
from .translator import Translator, SentenceTranslation


@dataclass
class AnalyzedRegion:
    region: TextRegion
    translation: SentenceTranslation

    def to_dict(self) -> dict[str, Any]:
        return {
            "region": self.region.to_dict(),
            "translation": self.translation.to_dict(),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "AnalyzedRegion":
        return cls(
            region=TextRegion.from_dict(d["region"]),
            translation=SentenceTranslation.from_dict(d["translation"]),
        )


@dataclass
class PageResult:
    image_path: Path
    image_hash: str
    regions: list[AnalyzedRegion] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "image_hash": self.image_hash,
            "regions": [r.to_dict() for r in self.regions],
        }


def analyze_page(
    image_path: Path,
    ocr: OCREngine,
    translator: Translator,
    use_cache: bool = True,
) -> PageResult:
    image_hash = cache.hash_file(image_path)

    if use_cache:
        cached = cache.load(image_hash)
        if cached:
            return PageResult(
                image_path=image_path,
                image_hash=image_hash,
                regions=[AnalyzedRegion.from_dict(r) for r in cached.get("regions", [])],
            )

    regions = ocr.analyze(image_path)

    # Group nearby regions so a single hotkey covers a whole speech bubble /
    # paragraph instead of one per detected line.
    clusters = _cluster_regions(regions)
    merged = [_merge_cluster(regions, idxs) for idxs in clusters]
    # Put clusters in natural reading order so sentence numbers 1,2,3... flow.
    merged.sort(key=_reading_order_key(merged))

    sentences = [m.text for m in merged]
    translations = translator.translate(sentences) if sentences else []

    analyzed = [
        AnalyzedRegion(region=m, translation=t) for m, t in zip(merged, translations)
    ]
    result = PageResult(image_path=image_path, image_hash=image_hash, regions=analyzed)
    cache.save(image_hash, result.to_dict())
    return result


# -- clustering ---------------------------------------------------------

def _cluster_regions(regions: list[TextRegion], gap_factor: float = 1.0) -> list[list[int]]:
    """Union-find grouping by proximity.

    Two regions belong to the same cluster if the empty-space distance between
    their bounding boxes is within `gap_factor * min(min_dim_a, min_dim_b)`,
    where `min_dim` is min(width, height). For vertical text columns this is
    column width; for horizontal lines, line height. Both yield sensible
    "same speech bubble / paragraph" merges.
    """
    n = len(regions)
    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        a, b = find(i), find(j)
        if a != b:
            parent[a] = b

    for i in range(n):
        ai = regions[i]
        for j in range(i + 1, n):
            aj = regions[j]
            gx = max(0, max(ai.x, aj.x) - min(ai.x + ai.w, aj.x + aj.w))
            gy = max(0, max(ai.y, aj.y) - min(ai.y + ai.h, aj.y + aj.h))
            dist = (gx * gx + gy * gy) ** 0.5
            min_dim = min(min(ai.w, ai.h), min(aj.w, aj.h))
            if dist <= gap_factor * min_dim:
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())


def _merge_cluster(regions: list[TextRegion], idxs: list[int]) -> TextRegion:
    members = [regions[i] for i in idxs]
    x0 = min(m.x for m in members)
    y0 = min(m.y for m in members)
    x1 = max(m.x + m.w for m in members)
    y1 = max(m.y + m.h for m in members)
    vertical = sum(1 for m in members if m.vertical) >= len(members) / 2
    if vertical:
        # Japanese vertical: right column first, top to bottom within a column.
        members.sort(key=lambda m: (-m.x, m.y))
    else:
        members.sort(key=lambda m: (m.y, m.x))
    text = "\n".join(m.text for m in members if m.text)
    return TextRegion(x=x0, y=y0, w=x1 - x0, h=y1 - y0, text=text, vertical=vertical)


def _reading_order_key(merged: list[TextRegion]):
    vertical_majority = (
        merged and sum(1 for m in merged if m.vertical) >= len(merged) / 2
    )
    if vertical_majority:
        return lambda m: (-m.x, m.y)
    return lambda m: (m.y, m.x)
