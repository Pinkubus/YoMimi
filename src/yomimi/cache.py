"""Disk cache for OCR + translation results, keyed by image content hash."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .config import CACHE_DIR


def hash_file(path: Path) -> str:
    h = hashlib.sha1()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def cache_path(image_hash: str) -> Path:
    return CACHE_DIR / f"{image_hash}.json"


def load(image_hash: str) -> dict[str, Any] | None:
    p = cache_path(image_hash)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def save(image_hash: str, data: dict[str, Any]) -> None:
    cache_path(image_hash).write_text(
        json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
    )
