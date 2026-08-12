from __future__ import annotations

import re
from typing import Dict, List

from voice.voice_config import load_voice_settings


def detect_wake_word(text: str, wake_words: List[str] | None = None) -> Dict[str, object]:
    original = str(text or "").strip()
    lowered = original.lower()
    words = wake_words or load_voice_settings().wake_words
    normalized_text = re.sub(r"^[\s,.;:!?-]+", "", lowered)
    for wake_word in words:
        candidate = str(wake_word or "").strip().lower()
        if not candidate:
            continue
        pattern = rf"^(?:{re.escape(candidate)})(?:[\s,.;:!?-]+|$)"
        if re.match(pattern, normalized_text):
            cleaned = re.sub(pattern, "", normalized_text, count=1).strip(" ,.:;!-")
            return {
                "detected": True,
                "wake_word": candidate,
                "remaining_text": cleaned,
                "confidence": 1.0,
                "matched_at_start": True,
            }
    return {
        "detected": False,
        "wake_word": None,
        "remaining_text": original,
        "confidence": 0.0,
        "matched_at_start": False,
    }
