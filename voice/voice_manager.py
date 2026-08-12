from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional


CONFIG_DIR = Path(__file__).resolve().parents[1] / "config"
VOICE_PROFILES_FILE = CONFIG_DIR / "voice_profiles.json"
USER_PROFILE_FILE = CONFIG_DIR / "user_profile.json"


def load_voice_profiles() -> Dict[str, Dict[str, Any]]:
    if not VOICE_PROFILES_FILE.exists():
        return {}
    try:
        payload = json.loads(VOICE_PROFILES_FILE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def load_user_profile() -> Dict[str, Any]:
    if not USER_PROFILE_FILE.exists():
        return {}
    try:
        payload = json.loads(USER_PROFILE_FILE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def save_user_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    USER_PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
    USER_PROFILE_FILE.write_text(json.dumps(profile, indent=2, ensure_ascii=False), encoding="utf-8")
    return profile


def resolve_voice_profile(profile_id: str | None = None) -> Dict[str, Any]:
    profiles = load_voice_profiles()
    user_profile = load_user_profile()
    selected_id = str(profile_id or user_profile.get("voice_profile") or "jarvis").strip().lower()
    selected = dict(profiles.get(selected_id) or profiles.get("jarvis") or {})
    selected["id"] = selected_id if selected else "jarvis"
    return selected


def format_speech_text(text: str) -> str:
    content = str(text or "").strip()
    if not content:
        return ""

    content = re.sub(r"```[\s\S]*?```", " I've prepared the code for you. ", content)
    content = re.sub(r"`([^`]+)`", r"\1", content)
    content = re.sub(r"#{1,6}\s*", "", content)
    content = re.sub(r"\*\*(.*?)\*\*", r"\1", content)
    content = re.sub(r"\*(.*?)\*", r"\1", content)
    content = re.sub(r"^\s*[-*]\s+", "Additionally, ", content, flags=re.MULTILINE)
    content = re.sub(r"\n{2,}", ". ", content)
    content = re.sub(r"\n", ", ", content)
    content = re.sub(r"\s{2,}", " ", content)
    content = content.replace("•", " Additionally, ")
    return content.strip()


def build_spoken_preview(text: str, *, max_sentences: int = 8, max_length: int = 1200) -> str:
    formatted = format_speech_text(text)
    if not formatted:
        return ""
    if len(formatted) <= max_length:
        return formatted
    sentences = re.split(r"(?<=[.!?])\s+", formatted)
    preview: list[str] = []
    current_length = 0
    for sentence in sentences[:max_sentences]:
        stripped = sentence.strip()
        if not stripped:
            continue
        if current_length + len(stripped) > max_length and len(preview) >= 2:
            break
        preview.append(stripped)
        current_length += len(stripped) + 1
        if current_length >= max_length:
            break
    spoken = " ".join(preview).strip()
    if spoken and len(formatted) > max_length:
        return f"{spoken} The full response is on screen — say stop or I'll read it myself to silence me."
    return spoken or formatted[:max_length]


STOP_SPEECH_PHRASES: tuple[str, ...] = (
    "stop",
    "okay stop",
    "ok stop",
    "stop it",
    "stop speaking",
    "stop talking",
    "be quiet",
    "quiet",
    "shut up",
    "enough",
    "that's enough",
    "thats enough",
    "i'll read it myself",
    "ill read it myself",
    "i will read it myself",
    "i can read",
    "let me read",
    "silence",
    "pause",
)


def is_stop_speech_phrase(transcript: str) -> bool:
    normalized = re.sub(r"[^a-z'\s]", " ", str(transcript or "").lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return False
    if normalized in STOP_SPEECH_PHRASES:
        return True
    first_words = " ".join(normalized.split(" ")[:5])
    for phrase in STOP_SPEECH_PHRASES:
        if not phrase:
            continue
        if first_words == phrase or first_words.startswith(f"{phrase} "):
            return True
    return False


def choose_voice_metadata(voices: List[Dict[str, Any]], *, gender: str, language: str) -> Optional[Dict[str, Any]]:
    if not voices:
        return None

    requested_gender = str(gender or "").strip().lower()
    requested_language = str(language or "").strip().lower()

    def _name(entry: Dict[str, Any]) -> str:
        return f"{entry.get('name', '')} {entry.get('id', '')}".lower()

    def _language_match(entry: Dict[str, Any]) -> bool:
        languages = [str(item).lower() for item in entry.get("languages", [])]
        if requested_language and any(lang.startswith(requested_language) for lang in languages):
            return True
        return requested_language in _name(entry)

    if requested_gender == "male":
        for entry in voices:
            name = _name(entry)
            if any(label in name for label in ("male", "david", "mark", "james")) or (_language_match(entry) and "female" not in name):
                return entry
    else:
        for entry in voices:
            name = _name(entry)
            if any(label in name for label in ("female", "zira", "susan", "hazel")) or _language_match(entry):
                return entry

    for entry in voices:
        if _language_match(entry):
            return entry
    return voices[0]
