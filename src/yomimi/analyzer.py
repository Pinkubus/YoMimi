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
    sentences = [r.text for r in regions]
    translations = translator.translate(sentences) if sentences else []

    analyzed = [
        AnalyzedRegion(region=r, translation=t) for r, t in zip(regions, translations)
    ]
    result = PageResult(image_path=image_path, image_hash=image_hash, regions=analyzed)
    cache.save(image_hash, result.to_dict())
    return result
