"""Claude-powered translator.

Given a list of OCR'd Japanese sentences, returns for each:
  - sentence_translation: natural English
  - words: list of {jp, reading, meaning} tokens, in reading order

Batches all sentences from a page into one Claude call to minimize cost.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Any

from anthropic import Anthropic

from .config import claude_api_key, CLAUDE_MODEL


@dataclass
class WordGloss:
    jp: str
    reading: str
    meaning: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SentenceTranslation:
    original: str
    translation: str
    words: list[WordGloss]

    def to_dict(self) -> dict[str, Any]:
        return {
            "original": self.original,
            "translation": self.translation,
            "words": [w.to_dict() for w in self.words],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SentenceTranslation":
        return cls(
            original=d["original"],
            translation=d["translation"],
            words=[WordGloss(**w) for w in d.get("words", [])],
        )


SYSTEM_PROMPT = """You are a Japanese reading tutor. For each numbered Japanese
sentence the user provides, return a JSON object with:
  - "translation": a natural English translation of the whole sentence.
  - "words": an ordered list of every meaningful word/token in the sentence
    (skip pure punctuation). Each entry has:
       - "jp":      the surface form in Japanese
       - "reading": hiragana reading
       - "meaning": short English gloss (1-5 words)

Respond ONLY with a JSON array, one object per input sentence, in the SAME order.
No prose, no markdown fences."""


class Translator:
    def __init__(self) -> None:
        self._client = Anthropic(api_key=claude_api_key())

    def translate(self, sentences: list[str]) -> list[SentenceTranslation]:
        if not sentences:
            return []

        numbered = "\n".join(f"{i+1}. {s}" for i, s in enumerate(sentences))
        msg = self._client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": numbered}],
        )
        raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        data = _parse_json_array(raw)

        out: list[SentenceTranslation] = []
        for original, entry in zip(sentences, data):
            words = [
                WordGloss(
                    jp=w.get("jp", ""),
                    reading=w.get("reading", ""),
                    meaning=w.get("meaning", ""),
                )
                for w in entry.get("words", [])
            ]
            out.append(
                SentenceTranslation(
                    original=original,
                    translation=entry.get("translation", ""),
                    words=words,
                )
            )
        # Pad if Claude returned fewer entries than expected.
        while len(out) < len(sentences):
            out.append(SentenceTranslation(sentences[len(out)], "", []))
        return out


def _parse_json_array(raw: str) -> list[dict[str, Any]]:
    raw = raw.strip()
    # Strip accidental code fences.
    if raw.startswith("```"):
        raw = raw.strip("`")
        # remove leading "json\n" if present
        if raw.lower().startswith("json"):
            raw = raw[4:].lstrip()
    # Find the outermost JSON array.
    start = raw.find("[")
    end = raw.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        parsed = json.loads(raw[start : end + 1])
    except json.JSONDecodeError:
        return []
    return parsed if isinstance(parsed, list) else []
