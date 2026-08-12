from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional, Protocol
from urllib.parse import parse_qs, urlparse

import requests
from groq import Groq

from config.settings import GROQ_API_KEY, MODEL_NAME
from memory.vector_memory import store_memory


client = Groq(api_key=GROQ_API_KEY)

REQUEST_TIMEOUT = 10

CAPABILITY_MODE = "hybrid"
TRUST_LEVEL = "safe"
AGENT_NAME = "youtube"

ACTION_SUMMARIZE = "summarize_youtube"
ACTION_SEARCH = "search_youtube_topic"

OEMBED_URL = "https://www.youtube.com/oembed"

ERROR_MISSING_URL = "MISSING_URL"
ERROR_INVALID_URL = "INVALID_URL"
ERROR_TIMEOUT = "TIMEOUT"
ERROR_NETWORK = "NETWORK_ERROR"
ERROR_MISSING_TOPIC = "MISSING_TOPIC"
ERROR_GENERIC = "ERROR"
ERROR_INVALID_RESPONSE = "INVALID_RESPONSE"
ERROR_EMPTY_RESULT = "EMPTY_RESULT"


class MemoryStore(Protocol):
    def __call__(self, label: str, metadata: Dict[str, Any]) -> None: ...


@dataclass(slots=True)
class AgentResult:
    success: bool
    action: str
    message: str
    data: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    error_code: Optional[str] = None
    mode: str = CAPABILITY_MODE
    agent: str = AGENT_NAME
    trust_level: str = TRUST_LEVEL

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class VideoMetadata:
    video_id: str
    title: str
    channel: str
    url: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class YouTubeAgentError(Exception):
    error_code = ERROR_GENERIC

    def __init__(self, message: str, *, user_message: Optional[str] = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


class MissingUrlError(YouTubeAgentError):
    error_code = ERROR_MISSING_URL


class InvalidUrlError(YouTubeAgentError):
    error_code = ERROR_INVALID_URL


class TimeoutError(YouTubeAgentError):
    error_code = ERROR_TIMEOUT


class NetworkError(YouTubeAgentError):
    error_code = ERROR_NETWORK


class MissingTopicError(YouTubeAgentError):
    error_code = ERROR_MISSING_TOPIC


class InvalidResponseError(YouTubeAgentError):
    error_code = ERROR_INVALID_RESPONSE


class EmptyResultError(YouTubeAgentError):
    error_code = ERROR_EMPTY_RESULT


def build_result(
    *,
    success: bool,
    action: str,
    message: str,
    data: Optional[Dict[str, Any]] = None,
    error: Optional[str] = None,
    error_code: Optional[str] = None,
) -> Dict[str, Any]:
    return AgentResult(
        success=success,
        action=action,
        message=message,
        data=data or {},
        error=error,
        error_code=error_code,
    ).to_dict()


def safe_error_text(error: Exception) -> str:
    text = str(error).strip()
    return text if text else error.__class__.__name__


def clean(text: Any) -> str:
    if text is None:
        return ""

    value = str(text)
    value = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", value)
    value = re.sub(r"#{1,6}\s*", "", value)
    value = re.sub(r"`{3}[\w-]*\n?", "", value)
    value = re.sub(r"`(.+?)`", r"\1", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def is_meaningful(text: Any) -> bool:
    if text is None:
        return False
    cleaned = str(text).strip()
    return bool(cleaned.strip(" \n\t.,!?;:-_"))


def normalize_topic(topic: Any) -> str:
    return clean(topic)


def extract_video_id(url: str) -> Optional[str]:
    try:
        parsed = urlparse(str(url).strip())
        host = parsed.netloc.lower()

        if host in {"youtube.com", "www.youtube.com", "m.youtube.com"}:
            if parsed.path == "/watch":
                video_id = parse_qs(parsed.query).get("v", [None])[0]
                return video_id or None

            if parsed.path.startswith("/shorts/") or parsed.path.startswith("/embed/"):
                parts = [part for part in parsed.path.split("/") if part]
                return parts[1] if len(parts) >= 2 else None

        if host == "youtu.be":
            video_id = parsed.path.lstrip("/")
            return video_id or None

        return None
    except Exception:
        return None


def normalize_youtube_url(url: str) -> Optional[str]:
    video_id = extract_video_id(url)
    if not video_id:
        return None
    return f"https://www.youtube.com/watch?v={video_id}"


class MemoryManager:
    def __init__(self, *, writer: Optional[MemoryStore] = None) -> None:
        self.writer = writer or store_memory

    def maybe_store(self, label: str, metadata: Dict[str, Any]) -> Optional[str]:
        try:
            self.writer(label, metadata)
            return None
        except Exception as error:
            return safe_error_text(error)


class InputValidator:
    @staticmethod
    def validate_url(url: Any) -> str:
        cleaned = clean(url)

        if not is_meaningful(cleaned):
            raise MissingUrlError(
                "Missing URL.",
                user_message="Provide a YouTube URL.",
            )

        normalized = normalize_youtube_url(cleaned)
        if not normalized:
            raise InvalidUrlError(
                "Invalid YouTube URL.",
                user_message="Invalid YouTube URL.",
            )

        return normalized

    @staticmethod
    def validate_topic(topic: Any) -> str:
        cleaned = normalize_topic(topic)

        if not is_meaningful(cleaned):
            raise MissingTopicError(
                "Missing topic.",
                user_message="Provide a topic.",
            )

        return cleaned


class MetadataService:
    def __init__(self, *, timeout: int = REQUEST_TIMEOUT) -> None:
        self.timeout = timeout

    def fetch(self, url: str) -> VideoMetadata:
        normalized_url = normalize_youtube_url(url)
        if not normalized_url:
            raise InvalidUrlError(
                "Invalid YouTube URL.",
                user_message="Invalid YouTube URL.",
            )

        video_id = extract_video_id(normalized_url)
        if not video_id:
            raise InvalidUrlError(
                "Invalid YouTube video ID.",
                user_message="Invalid YouTube URL.",
            )

        try:
            response = requests.get(
                OEMBED_URL,
                params={"url": normalized_url, "format": "json"},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.exceptions.Timeout as error:
            raise TimeoutError(
                "Request timed out.",
                user_message="Request timed out.",
            ) from error
        except requests.exceptions.RequestException as error:
            raise NetworkError(
                "Failed to fetch video metadata.",
                user_message="Failed to fetch video metadata.",
            ) from error

        try:
            data = response.json()
        except Exception as error:
            raise InvalidResponseError(
                "Invalid metadata response.",
                user_message="Failed to read video metadata.",
            ) from error

        if not isinstance(data, dict):
            raise InvalidResponseError(
                "Invalid metadata response.",
                user_message="Failed to read video metadata.",
            )

        title = clean(data.get("title", "")) or "Unknown"
        channel = clean(data.get("author_name", "")) or "Unknown"

        return VideoMetadata(
            video_id=video_id,
            title=title,
            channel=channel,
            url=normalized_url,
        )


class LLMService:
    def __init__(self, *, llm_client: Groq, model_name: str) -> None:
        self.llm_client = llm_client
        self.model_name = model_name

    @staticmethod
    def _extract_content(response: Any) -> str:
        try:
            return response.choices[0].message.content or ""
        except Exception as error:
            raise InvalidResponseError(
                "Invalid LLM response.",
                user_message="Model response was invalid.",
            ) from error

    def summarize_from_metadata(self, metadata: VideoMetadata) -> str:
        response = self.llm_client.chat.completions.create(
            model=self.model_name,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Analyze a YouTube video using only the provided metadata. "
                        "Do not invent details about the video's exact contents. "
                        "Return plain text with these labels exactly:\n"
                        "TITLE:\nCHANNEL:\nSUMMARY:\nKEY TOPICS:\nAUDIENCE:\nNOTE:"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"URL: {metadata.url}\n"
                        f"TITLE: {metadata.title}\n"
                        f"CHANNEL: {metadata.channel}\n"
                        f"VIDEO ID: {metadata.video_id}"
                    ),
                },
            ],
            max_tokens=500,
            temperature=0.2,
        )

        content = self._extract_content(response)
        cleaned = clean(content)

        if not is_meaningful(cleaned):
            raise EmptyResultError(
                "Empty summary.",
                user_message="Failed to analyze video.",
            )

        return cleaned

    def build_search_strategy(self, topic: str) -> str:
        response = self.llm_client.chat.completions.create(
            model=self.model_name,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Suggest a YouTube learning strategy for the user's topic. "
                        "Return plain text with these labels exactly:\n"
                        "TOPIC:\nSEARCH TERMS:\nCHANNEL TYPES:\nLEARNING PATH:\nTIPS:"
                    ),
                },
                {
                    "role": "user",
                    "content": topic,
                },
            ],
            max_tokens=400,
            temperature=0.3,
        )

        content = self._extract_content(response)
        cleaned = clean(content)

        if not is_meaningful(cleaned):
            raise EmptyResultError(
                "Empty topic result.",
                user_message="YouTube search failed.",
            )

        return cleaned


class FallbackFormatter:
    @staticmethod
    def summarize(metadata: VideoMetadata) -> str:
        return (
            f"TITLE: {metadata.title}\n"
            f"CHANNEL: {metadata.channel}\n"
            "SUMMARY: No detailed summary available from metadata only.\n"
            "KEY TOPICS: Unknown\n"
            "AUDIENCE: General viewers\n"
            "NOTE: This result is based only on video metadata."
        )

    @staticmethod
    def search(topic: str) -> str:
        return (
            f"TOPIC: {topic}\n"
            f"SEARCH TERMS: {topic}\n"
            "CHANNEL TYPES: Educational channels\n"
            "LEARNING PATH: Start with beginner videos, then move to practical examples.\n"
            "TIPS: Compare multiple creators."
        )


class YouTubeAgent:
    def __init__(self) -> None:
        self.validator = InputValidator()
        self.metadata = MetadataService()
        self.llm = LLMService(llm_client=client, model_name=MODEL_NAME)
        self.memory = MemoryManager()

    def summarize_youtube(self, url: Any) -> Dict[str, Any]:
        try:
            normalized_url = self.validator.validate_url(url)
            metadata = self.metadata.fetch(normalized_url)

            try:
                message = self.llm.summarize_from_metadata(metadata)
            except (InvalidResponseError, EmptyResultError):
                message = FallbackFormatter.summarize(metadata)

            self.memory.maybe_store(
                f"YouTube analyzed: {metadata.title}",
                {
                    "type": "youtube_summary",
                    "video_id": metadata.video_id,
                    "channel": metadata.channel,
                },
            )

            return build_result(
                success=True,
                action=ACTION_SUMMARIZE,
                message=message,
                data=metadata.to_dict(),
            )

        except YouTubeAgentError as error:
            return build_result(
                success=False,
                action=ACTION_SUMMARIZE,
                message=error.user_message,
                error=safe_error_text(error),
                error_code=error.error_code,
            )

        except Exception as error:
            return build_result(
                success=False,
                action=ACTION_SUMMARIZE,
                message="Failed to analyze video.",
                error=safe_error_text(error),
                error_code=ERROR_GENERIC,
            )

    def search_youtube_topic(self, topic: Any) -> Dict[str, Any]:
        try:
            text = self.validator.validate_topic(topic)

            try:
                message = self.llm.build_search_strategy(text)
            except (InvalidResponseError, EmptyResultError):
                message = FallbackFormatter.search(text)

            self.memory.maybe_store(
                f"YouTube topic: {text}",
                {"type": "youtube_search", "topic": text},
            )

            return build_result(
                success=True,
                action=ACTION_SEARCH,
                message=message,
                data={"topic": text},
            )

        except YouTubeAgentError as error:
            return build_result(
                success=False,
                action=ACTION_SEARCH,
                message=error.user_message,
                error=safe_error_text(error),
                error_code=error.error_code,
            )

        except Exception as error:
            return build_result(
                success=False,
                action=ACTION_SEARCH,
                message="YouTube search failed.",
                error=safe_error_text(error),
                error_code=ERROR_GENERIC,
            )


youtube_agent = YouTubeAgent()


def summarize_youtube(url: Any) -> Dict[str, Any]:
    return youtube_agent.summarize_youtube(url)


def search_youtube_topic(topic: Any) -> Dict[str, Any]:
    return youtube_agent.search_youtube_topic(topic)