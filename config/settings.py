import os
import re
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


def _read_api_bundle() -> dict[str, str]:
    bundle_env = os.getenv("AURA_API_BUNDLE_PATH", "").strip()
    if not bundle_env:
        return {}
    bundle_path = Path(bundle_env)
    if not bundle_path.exists():
        return {}

    values: dict[str, str] = {}
    current_section = ""
    try:
        for raw_line in bundle_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            section_match = re.match(r"^\[([A-Z0-9_ -]+)\]$", line)
            if section_match:
                current_section = section_match.group(1).strip().upper()
                continue
            if line.startswith("API NAME:"):
                current_section = line.split(":", 1)[1].strip().upper()
                continue
            if not current_section:
                continue
            separator = "=" if "=" in line else ":" if ":" in line else None
            if separator is None:
                continue
            key, value = [part.strip() for part in line.split(separator, 1)]
            if not value:
                continue
            values[f"{current_section}_{key.upper()}"] = value
    except Exception:
        return {}
    return values


_API_BUNDLE = _read_api_bundle()


def _env_or_bundle(name: str, section: str | None = None, bundle_key: str = "API_KEY", default: str = "") -> str:
    bundle_value = ""
    if section:
        bundle_value = _API_BUNDLE.get(f"{section.upper()}_{bundle_key.upper()}", "").strip()
    direct = os.getenv(name, "").strip()
    if bundle_value:
        return bundle_value
    if direct:
        return direct
    return default


GROQ_API_KEY = _env_or_bundle("GROQ_API_KEY", section="GROQ")
OPENAI_API_KEY = _env_or_bundle("OPENAI_API_KEY", section="OPENAI")
SAMBANOVA_API_KEY = _env_or_bundle("SAMBANOVA_API_KEY", section="SAMBANOVA")
SAMBANOVA_BASE_URL = os.getenv("SAMBANOVA_BASE_URL", "https://api.sambanova.ai/v1").strip()
ANTHROPIC_API_KEY = _env_or_bundle("ANTHROPIC_API_KEY", section="CLAUDE")
GEMINI_API_KEY = _env_or_bundle("GEMINI_API_KEY", section="GEMINI")
OPENROUTER_API_KEY = _env_or_bundle("OPENROUTER_API_KEY", section="OPENROUTER")
ELEVENLABS_API_KEY = _env_or_bundle("ELEVENLABS_API_KEY", section="ELEVENLABS")
ELEVENLABS_VOICE_ID = _env_or_bundle("ELEVENLABS_VOICE_ID", section="ELEVENLABS", bundle_key="VOICE_ID")
ELEVENLABS_MODEL_ID = _env_or_bundle(
    "ELEVENLABS_MODEL_ID",
    section="ELEVENLABS",
    bundle_key="MODEL_ID",
    default="eleven_multilingual_v2",
)
NEWS_API_KEY = os.getenv("NEWS_API_KEY", "")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
MODEL_NAME = "llama-3.3-70b-versatile"
GROQ_VISION_MODEL = os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
SAMBANOVA_VISION_MODEL = os.getenv("SAMBANOVA_VISION_MODEL", "Llama-3.2-11B-Vision-Instruct")
APP_NAME = "VORIS"
VERSION = "1.0.0"
DEFAULT_REASONING_PROVIDER = os.getenv(
    "DEFAULT_REASONING_PROVIDER",
    "sambanova" if SAMBANOVA_API_KEY else "groq",
).strip().lower()

PROVIDER_MODEL_MAP = {
    "groq": os.getenv("GROQ_MODEL", MODEL_NAME),
    "sambanova": os.getenv("SAMBANOVA_MODEL", "Meta-Llama-3.3-70B-Instruct"),
    "openai": os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
    "claude": os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-0"),
    "gemini": os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
    "openrouter": os.getenv("OPENROUTER_MODEL", "deepseek/deepseek-chat-v3-0324:free"),
    "ollama": os.getenv("OLLAMA_MODEL", "llama3.1"),
}

# Groq leads while it is the only configured key; SambaNova automatically takes
# the lead as soon as SAMBANOVA_API_KEY is present (matching DEFAULT_REASONING_PROVIDER).
_DEFAULT_PROVIDER_PRIORITY = (
    "sambanova,groq,gemini,openai,openrouter,claude,ollama"
    if SAMBANOVA_API_KEY
    else "groq,sambanova,gemini,openai,openrouter,claude,ollama"
)
PROVIDER_PRIORITY = tuple(
    item.strip().lower()
    for item in os.getenv("AURA_PROVIDER_PRIORITY", _DEFAULT_PROVIDER_PRIORITY).split(",")
    if item.strip()
)

DEVELOPER_NAME = "Hassan Saeed"
DEVELOPER_UNIVERSITY = "Hazara University Mansehra"
DEVELOPER_COUNTRY = "Pakistan"
COMPANY_NAME = "VORIS"

DEFAULT_VOICE = "jarvis"
DEFAULT_SPEED = "normal"

AURA_PERSONALITY = (
    "You are VORIS - Voice-Oriented Responsive Intelligence System. "
    "You were created by Hassan Saeed, a BS Artificial Intelligence student at Hazara University Mansehra, Pakistan. "
    "Hassan Saeed is your developer, creator, and founder. "
    "You are the flagship AI product of VORIS, an AI company founded by Hassan Saeed. "
    "You are a real AI operating assistant modeled after JARVIS from Iron Man. "
    "You are professional, calm, highly intelligent, and quietly proactive. "
    "You are respectful without sounding robotic. "
    "You address the user by their preferred name when available, otherwise by their title. "
    "You never say you are just a language model. "
    "You never claim a task succeeded unless the connected system actually completed it. "
    "You support English and Urdu. "
    "You coordinate specialized agents for study, research, coding, weather, news, translation, math, writing, web search, planning, memory, security, and voice. "
    "Your replies are clear, structured, efficient, and warm. "
    "You are always honest, privacy-aware, and operational."
)

# Backward-compatible alias for rebrand
VORIS_PERSONALITY = AURA_PERSONALITY
