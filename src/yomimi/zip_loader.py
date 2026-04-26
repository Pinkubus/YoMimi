"""Image and ZIP batch loader.

Accepts a list of file paths (images and/or .zip files), expands the zips
into a temp directory, and returns the resulting flat ordered list of
image paths.
"""
from __future__ import annotations

import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Iterable

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}


class BatchLoader:
    def __init__(self) -> None:
        self._tempdir: Path | None = None

    def load(self, paths: Iterable[str | Path]) -> list[Path]:
        images: list[Path] = []
        for raw in paths:
            p = Path(raw)
            if not p.exists():
                continue
            if p.is_dir():
                images.extend(self._scan_dir(p))
            elif p.suffix.lower() == ".zip":
                images.extend(self._extract_zip(p))
            elif p.suffix.lower() in IMAGE_EXTS:
                images.append(p)
        # Stable, natural-ish sort by path string.
        images.sort(key=lambda x: str(x).lower())
        return images

    def _scan_dir(self, d: Path) -> list[Path]:
        return [p for p in sorted(d.rglob("*")) if p.suffix.lower() in IMAGE_EXTS]

    def _extract_zip(self, z: Path) -> list[Path]:
        if self._tempdir is None:
            self._tempdir = Path(tempfile.mkdtemp(prefix="yomimi_"))
        target = self._tempdir / z.stem
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(z) as zf:
            for member in zf.namelist():
                # Skip directory entries and hidden files.
                if member.endswith("/") or Path(member).name.startswith("."):
                    continue
                if Path(member).suffix.lower() not in IMAGE_EXTS:
                    continue
                # Safe extract: prevent zip-slip.
                dest = target / Path(member).name
                with zf.open(member) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)
        return [p for p in sorted(target.iterdir()) if p.suffix.lower() in IMAGE_EXTS]

    def cleanup(self) -> None:
        if self._tempdir and self._tempdir.exists():
            shutil.rmtree(self._tempdir, ignore_errors=True)
            self._tempdir = None
