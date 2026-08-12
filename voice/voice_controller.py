from __future__ import annotations

from typing import Any, Dict

from voice.audio_manager import get_audio_status
from voice.mic_handler import get_microphone_status
from voice.noise_filter import analyze_transcript_noise, clean_transcript_text
from voice.speech_to_text import get_stt_status, transcribe_audio_file, transcribe_microphone
from voice.text_to_speech import get_tts_status, list_voices, stop_speaking
from voice.voice_config import load_voice_settings, update_voice_settings
from voice.voice_manager import build_spoken_preview, load_user_profile
from voice.wake_word import detect_wake_word


def get_voice_status() -> Dict[str, Any]:
    settings = load_voice_settings()
    user_profile = load_user_profile()
    stt_status = get_stt_status()
    microphone_status = get_microphone_status()
    audio_status = get_audio_status()
    backend_microphone_ready = bool(stt_status.get("supports_microphone") and microphone_status.get("available"))
    locked_voice = list_voices()
    tts_status = get_tts_status()
    return {
        "mode": "browser_voice",
        "settings": {
            "backend": "browser_speech_synthesis",
            "enabled": settings.enabled,
            "language": settings.language,
            "auto_speak_responses": settings.auto_speak_responses,
            "wake_words": list(settings.wake_words),
            "phrase_time_limit": settings.phrase_time_limit,
        },
        "user_profile": user_profile,
        "tts": {
            **tts_status,
            "voice": locked_voice[0] if locked_voice else None,
            "voice_locked": True,
        },
        "stt": stt_status,
        "microphone": microphone_status,
        "audio": audio_status,
        "web_input": {
            "backend_route_available": True,
            "recommended_mode": "backend_host_microphone" if backend_microphone_ready else "browser_only_fallback",
            "capture_scope": "host_machine",
            "note": (
                "Backend STT listens through the host machine microphone."
                if backend_microphone_ready
                else "Backend host microphone capture is unavailable. Reliable browser voice input falls back to push-to-talk."
            ),
        },
        "wake_word_preview": detect_wake_word("hey voris status check", settings.wake_words),
        "wake_word": {
            "phrases": list(settings.wake_words),
            "default_phrase": settings.wake_words[0] if settings.wake_words else "hey voris",
            "mode": "beta_single_phrase",
            "continuous_listening_note": (
                "Always-on ambient wake is not guaranteed. Reliable browser voice input is push-to-talk, "
                "and wake mode is a beta single-phrase listener while this page is open."
            ),
            "truth_note": "Do not treat browser wake as always-on background listening.",
        },
    }


def update_voice_preferences(**updates: object) -> Dict[str, Any]:
    allowed_updates = {
        key: value
        for key, value in updates.items()
        if key in {"enabled", "language", "auto_speak_responses"} and value is not None
    }
    settings = update_voice_settings(**allowed_updates)
    return {"success": True, "settings": settings.to_dict()}


def speak_response(text: str) -> Dict[str, Any]:
    preview = build_spoken_preview(text)
    if not preview:
        return {
            "success": False,
            "status": "empty_text",
            "message": "Speech text is empty.",
            "provider": "browser_speech_synthesis",
            "client_managed": True,
        }
    return {
        "success": False,
        "status": "disabled",
        "message": "Backend speech playback is disabled. The browser client speaks responses directly.",
        "provider": "browser_speech_synthesis",
        "client_managed": True,
        "backend_enabled": False,
        "spoken_text": preview,
    }


def stop_voice_output() -> Dict[str, Any]:
    return stop_speaking()


def transcribe_file_request(path_value: str) -> Dict[str, Any]:
    result = transcribe_audio_file(path_value)
    if result.get("success") and result.get("text"):
        result["cleaned_text"] = clean_transcript_text(str(result["text"]))
        result["wake_word"] = detect_wake_word(result["cleaned_text"])
        result["quality"] = analyze_transcript_noise(str(result["text"]))
    return result


def transcribe_microphone_request(*, timeout: int = 5, phrase_time_limit: int | None = None) -> Dict[str, Any]:
    result = transcribe_microphone(timeout=timeout, phrase_time_limit=phrase_time_limit)
    if result.get("success") and result.get("text"):
        result["cleaned_text"] = clean_transcript_text(str(result["text"]))
        result["wake_word"] = detect_wake_word(result["cleaned_text"])
        result["quality"] = analyze_transcript_noise(str(result["text"]))
    return result
