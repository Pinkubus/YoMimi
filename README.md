# YoMimi

A desktop Japanese reading-practice assistant. Drop in image files or `.zip`
archives of pages; YoMimi runs OCR on every text region but **does not** show
the translations up front. Hover a region for its translation, or hit a
keyboard hotkey shown in the corner of each box.

## Features (v1)

- Batch open mixed images and `.zip` archives of images
- Vertical and horizontal Japanese OCR
  - Detection: EasyOCR
  - Recognition: [manga-ocr](https://github.com/kha-white/manga-ocr) (purpose-built for manga / stylized text)
- Translation by Anthropic Claude (per-sentence + per-word gloss with readings)
- Reveal-on-demand UI:
  - **Hover** a box → tooltip with sentence + word breakdown
  - **Numpad / number row 1-9, 0** → reveal one of the page's sentences
  - **Letter keys a-z** → reveal one of the page's individual words
  - **Esc** → unpin
  - **Left / Right arrows** → previous / next page
- On-disk cache keyed by image SHA-1, so re-opening a page is instant
- Passive screen-watching mode is **stubbed** for v1 (UI button + plan only)

## Setup

```powershell
cd C:\Users\tylwilli\Desktop\YoMimi
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

> First launch downloads ~500 MB-1 GB of ML models (manga-ocr + EasyOCR's
> Japanese detector). They're cached under your user profile after that.

Make sure `.env` contains your Claude key. Any of these names work:

```
ANTHROPIC_API_KEY=sk-ant-...
# or
Claude_API_KEY=sk-ant-...
```

## Run

```powershell
python run.py
```

Then `Ctrl+O` to pick images and/or `.zip` files.

## Project layout

```
src/yomimi/
  __main__.py        # `python -m yomimi`
  config.py          # .env loading + cache dir
  zip_loader.py      # batch image + zip ingestion
  ocr.py             # EasyOCR detection + manga-ocr recognition
  translator.py      # Claude API client (batched per page)
  analyzer.py        # OCR + translate + cache glue
  cache.py           # JSON cache keyed by image hash
  passive.py         # stub for screen-watching mode
  ui/
    main_window.py
    reader_view.py
    worker.py        # QThread wrapper for analysis
```

## Cost note

Each page = one Claude `messages.create` call containing every detected
sentence on that page. Cached pages cost zero.

## Passive mode plan

See [src/yomimi/passive.py](src/yomimi/passive.py) for the design notes. Short
version: `mss` for capture → diff-throttled OCR → transparent always-on-top
overlay window with the same hotkey system as the reader.
