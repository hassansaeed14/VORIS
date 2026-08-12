from __future__ import annotations

from typing import Any, Dict, Optional

from brain.core_ai import process_command_detailed
from voice.noise_filter import analyze_transcript_noise, clean_transcript_text
from voice.voice_controller import get_voice_status
from voice.wake_word import detect_wake_word

WAKE_ACKNOWLEDGEMENTS = (
    "Yes?",
    "I'm here.",
    "Go ahead.",
)


def _wake_acknowledgement(cleaned_text: str) -> str:
    normalized = str(cleaned_text or "").strip()
    if not normalized:
        return WAKE_ACKNOWLEDGEMENTS[0]
    return WAKE_ACKNOWLEDGEMENTS[len(normalized) % len(WAKE_ACKNOWLEDGEMENTS)]


def process_voice_text(
    text: str,
    *,
    session_id: str = "default",
    user_profile: Optional[dict[str, Any]] = None,
    current_mode: str = "hybrid",
) -> Dict[str, Any]:
    """Normalize spoken input and send it through the same high-quality assistant path."""
    cleaned = clean_transcript_text(text)
    wake = detect_wake_word(cleaned)
    command_text = str(wake["remaining_text"] if wake.get("detected") else cleaned).strip()

    if not command_text:
        if wake.get("detected"):
            acknowledgement = _wake_acknowledgement(cleaned)
            return {
                "success": True,
                "status": "wake_only",
                "message": "Wake word detected. Waiting for the command.",
                "assistant_reply": acknowledgement,
                "transcript": text,
                "cleaned_transcript": cleaned,
                "wake_word": wake,
                "command_text": "",
                "noise": analyze_transcript_noise(text),
                "voice": get_voice_status(),
                "requires_followup_command": True,
            }
        return {
            "success": False,
            "status": "empty_command",
            "message": "VORIS heard the wake word but no command followed.",
            "voice": get_voice_status(),
            "noise": analyze_transcript_noise(text),
        }

    result = process_command_detailed(
        command_text,
        session_id=session_id,
        user_profile=user_profile,
        current_mode=current_mode,
    )
    return {
        "success": True,
        "status": "processed",
        "transcript": text,
        "cleaned_transcript": cleaned,
        "wake_word": wake,
        "command_text": command_text,
        "noise": analyze_transcript_noise(text),
        "voice": get_voice_status(),
        "result": result,
    }
