"""Configuration loader. Reads .env from project root."""
from __future__ import annotations

import os
from pathlib import Path
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = PROJECT_ROOT / ".yomimi_cache"
CACHE_DIR.mkdir(exist_ok=True)

load_dotenv(PROJECT_ROOT / ".env")


def claude_api_key() -> str:
    # Accept a few common variants since the user's .env uses "Claude_API_KEY".
    for k in ("ANTHROPIC_API_KEY", "CLAUDE_API_KEY", "Claude_API_KEY"):
        v = os.environ.get(k)
        if v:
            return v.strip()
    raise RuntimeError(
        "No Claude API key found. Set ANTHROPIC_API_KEY (or Claude_API_KEY) in .env"
    )


CLAUDE_MODEL = os.environ.get("CLAUDE_MODEL", "claude-3-5-sonnet-latest")
