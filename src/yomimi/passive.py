"""Stub for passive screen-watching mode.

Planned (not implemented):
  - Periodically grab the active monitor with `mss` (no extra perms on Windows).
  - Feed it through the same OCREngine as a regular page.
  - Show a transparent always-on-top overlay window with the same hover/hotkey
    boxes the reader uses, anchored at the detected screen coordinates.
  - Hotkey to toggle on/off (e.g. Ctrl+Alt+Y) via `keyboard` or `pynput`.
  - Throttle: only re-OCR when the captured frame changes by more than N%.

For v1 this just exposes a togglable flag so the UI can wire a checkbox.
"""
from __future__ import annotations


class PassiveMode:
    def __init__(self) -> None:
        self.enabled = False

    def toggle(self) -> bool:
        self.enabled = not self.enabled
        return self.enabled

    def status(self) -> str:
        return "Passive mode: not implemented in v1 (stub)."
