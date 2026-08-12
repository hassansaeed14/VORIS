from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional, Protocol

from groq import Groq

from config.settings import GROQ_API_KEY, MODEL_NAME
from memory.vector_memory import store_memory


client = Groq(api_key=GROQ_API_KEY)

CAPABILITY_MODE = "hybrid"
TRUST_LEVEL = "safe"
AGENT_NAME = "translation"

ACTION_TRANSLATE = "translate"
ACTION_DETECT_AND_TRANSLATE = "detect_and_translate"

MAX_TEXT_LENGTH = 5000

LANGUAGES = {
    "urdu": "Urdu",
    "english": "English",
    "arabic": "Arabic",
    "french": "French",
    "spanish": "Spanish",
    "german": "German",
    "chinese": "Chinese",
    "hindi": "Hindi",
    "punjabi": "Punjabi",
    "turkish": "Turkish",
    "russian": "Russian",
    "japanese": "Japanese",
    "korean": "Korean",
    "italian": "Italian",
    "portuguese": "Portuguese",
}

AUTO_LANGUAGE = "Auto"


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
class TranslationPayload:
    original_text: str
    translated_text: str
    source_language: str
    target_language: str
    notes: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class AutoTranslationPayload:
    original_text: str
    translated_text: str
    detected_language: str
    target_language: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class TranslationAgentError(Exception):
    error_code = "TRANSLATION_AGENT_ERROR"

    def __init__(self, message: str, *, user_message: Optional[str] = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


class MissingTextError(TranslationAgentError):
    error_code = "MISSING_TEXT"


class InvalidLanguageError(TranslationAgentError):
    error_code = "INVALID_LANGUAGE"


class TextTooLongError(TranslationAgentError):
    error_code = "TEXT_TOO_LONG"


class EmptyTranslationError(TranslationAgentError):
    error_code = "EMPTY_TRANSLATION"


class InvalidResponseError(TranslationAgentError):
    error_code = "INVALID_RESPONSE"


def safe_error_text(error: Exception) -> str:
    text = str(error).strip()
    return text if text else error.__class__.__name__


class MemoryManager:
    def __init__(self, *, writer: Optional[MemoryStore] = None) -> None:
        self.writer = writer or store_memory

    def maybe_store(self, label: str, metadata: Dict[str, Any]) -> Optional[str]:
        try:
            self.writer(label, metadata)
            return None
        except Exception as error:
            return safe_error_text(error)


class TextCleaner:
    @staticmethod
    def is_meaningful(value: Any) -> bool:
        if value is None:
            return False
        text = str(value).strip()
        return bool(text.strip(" \n\t.,!?;:-_"))

    @staticmethod
    def clean_output(text: Any) -> str:
        if not TextCleaner.is_meaningful(text):
            return ""
        value = str(text)
        value = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", value)
        value = re.sub(r"#{1,6}\s*", "", value)
        value = re.sub(r"`{3}[\w-]*\n?", "", value)
        value = re.sub(r"`(.+?)`", r"\1", value)
        value = re.sub(r"\s+", " ", value)
        return value.strip()

    @staticmethod
    def clean_input_text(text: Any) -> str:
        if text is None:
            return ""
        value = str(text).strip()
        value = re.sub(r"\r\n?", "\n", value)
        value = re.sub(r"\n{3,}", "\n\n", value)
        return value.strip()


class LanguageNormalizer:
    @staticmethod
    def normalize(lang: Any, *, allow_auto: bool = True) -> str:
        text = str(lang or "").strip()
        if not text:
            return AUTO_LANGUAGE if allow_auto else "English"

        lowered = text.lower()

        if allow_auto and lowered == "auto":
            return AUTO_LANGUAGE

        if lowered in LANGUAGES:
            return LANGUAGES[lowered]

        if re.fullmatch(r"[A-Za-z][A-Za-z\s\-]{1,40}", text):
            return text.strip().title()

        raise InvalidLanguageError(
            f"Invalid language: {text}",
            user_message="Provide a valid language name.",
        )


class TranslationPolicy:
    @staticmethod
    def validate_text(text: Any) -> str:
        cleaned = TextCleaner.clean_input_text(text)

        if not TextCleaner.is_meaningful(cleaned):
            raise MissingTextError(
                "Missing text.",
                user_message="Provide text to translate.",
            )

        if len(cleaned) > MAX_TEXT_LENGTH:
            raise TextTooLongError(
                "Text too long.",
                user_message=f"Keep text under {MAX_TEXT_LENGTH} characters.",
            )

        return cleaned


class LLMTranslationClient:
    def __init__(self, *, llm_client: Groq, model_name: str) -> None:
        self.llm_client = llm_client
        self.model_name = model_name

    def _safe_extract(self, response: Any) -> str:
        try:
            return response.choices[0].message.content or ""
        except Exception as error:
            raise InvalidResponseError(
                "Invalid LLM response.",
                user_message="Translation failed due to model error.",
            ) from error

    def _call(self, messages: list, max_tokens: int) -> str:
        response = self.llm_client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            max_tokens=max_tokens,
            temperature=0.2,
        )
        content = self._safe_extract(response)
        cleaned = TextCleaner.clean_output(content)

        if not TextCleaner.is_meaningful(cleaned):
            raise EmptyTranslationError(
                "Empty translation.",
                user_message="Translation failed.",
            )

        return cleaned

    def translate(self, *, text: str, target_language: str, source_language: str) -> str:
        return self._call(
            [
                {
                    "role": "system",
                    "content": (
                        "Translate accurately.\n"
                        "STRICT FORMAT:\n"
                        "ORIGINAL TEXT:\nSOURCE LANGUAGE:\nTARGET LANGUAGE:\nTRANSLATION:\nNOTES:"
                    ),
                },
                {
                    "role": "user",
                    "content": f"{source_language} -> {target_language}\n{text}",
                },
            ],
            max_tokens=1000,
        )

    def detect_and_translate(self, *, text: str) -> str:
        return self._call(
            [
                {
                    "role": "system",
                    "content": (
                        "Detect language and translate.\n"
                        "English ↔ Urdu.\n"
                        "STRICT FORMAT:\n"
                        "DETECTED LANGUAGE:\nTARGET LANGUAGE:\nORIGINAL TEXT:\nTRANSLATION:"
                    ),
                },
                {"role": "user", "content": text},
            ],
            max_tokens=800,
        )


class TranslationParser:
    @staticmethod
    def _extract(content: str, label: str) -> str:
        match = re.search(
            rf"{label}\s*:\s*(.*?)(?=\n[A-Z ]+:|$)",
            content,
            re.DOTALL,
        )
        return match.group(1).strip() if match else ""

    def parse_translation(self, content: str) -> TranslationPayload:
        translated = self._extract(content, "TRANSLATION")

        if not translated:
            raise EmptyTranslationError(
                "No translation.",
                user_message="Translation failed.",
            )

        return TranslationPayload(
            original_text=self._extract(content, "ORIGINAL TEXT"),
            translated_text=translated,
            source_language=self._extract(content, "SOURCE LANGUAGE") or AUTO_LANGUAGE,
            target_language=self._extract(content, "TARGET LANGUAGE"),
            notes=self._extract(content, "NOTES"),
        )

    def parse_auto(self, content: str) -> AutoTranslationPayload:
        translated = self._extract(content, "TRANSLATION")

        if not translated:
            raise EmptyTranslationError(
                "No translation.",
                user_message="Translation failed.",
            )

        return AutoTranslationPayload(
            original_text=self._extract(content, "ORIGINAL TEXT"),
            translated_text=translated,
            detected_language=self._extract(content, "DETECTED LANGUAGE") or AUTO_LANGUAGE,
            target_language=self._extract(content, "TARGET LANGUAGE"),
        )


class TranslationFormatter:
    @staticmethod
    def format_translation(p: TranslationPayload) -> str:
        return p.translated_text

    @staticmethod
    def format_auto(p: AutoTranslationPayload) -> str:
        return p.translated_text


class ResultFactory:
    @staticmethod
    def build(
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


class TranslationAgent:
    def __init__(self) -> None:
        self.llm = LLMTranslationClient(llm_client=client, model_name=MODEL_NAME)
        self.parser = TranslationParser()
        self.formatter = TranslationFormatter()
        self.policy = TranslationPolicy()
        self.memory = MemoryManager()

    def translate(
        self,
        text: Any,
        target_language: Any = "urdu",
        source_language: Any = "auto",
    ) -> Dict[str, Any]:
        try:
            text = self.policy.validate_text(text)
            target = LanguageNormalizer.normalize(target_language, allow_auto=False)
            source = LanguageNormalizer.normalize(source_language)

            raw = self.llm.translate(
                text=text,
                target_language=target,
                source_language=source,
            )

            payload = self.parser.parse_translation(raw)

            self.memory.maybe_store(
                "translation",
                {"target": target, "source": source},
            )

            return ResultFactory.build(
                success=True,
                action=ACTION_TRANSLATE,
                message=self.formatter.format_translation(payload),
                data=payload.to_dict(),
            )

        except TranslationAgentError as error:
            return ResultFactory.build(
                success=False,
                action=ACTION_TRANSLATE,
                message=error.user_message,
                error=safe_error_text(error),
                error_code=error.error_code,
            )

        except Exception as error:
            return ResultFactory.build(
                success=False,
                action=ACTION_TRANSLATE,
                message="Translation failed.",
                error=safe_error_text(error),
                error_code="ERROR",
            )

    def detect_and_translate(self, text: Any) -> Dict[str, Any]:
        try:
            text = self.policy.validate_text(text)

            raw = self.llm.detect_and_translate(text=text)
            payload = self.parser.parse_auto(raw)

            self.memory.maybe_store(
                "auto_translation",
                {"detected": payload.detected_language},
            )

            return ResultFactory.build(
                success=True,
                action=ACTION_DETECT_AND_TRANSLATE,
                message=self.formatter.format_auto(payload),
                data=payload.to_dict(),
            )

        except TranslationAgentError as error:
            return ResultFactory.build(
                success=False,
                action=ACTION_DETECT_AND_TRANSLATE,
                message=error.user_message,
                error=safe_error_text(error),
                error_code=error.error_code,
            )

        except Exception as error:
            return ResultFactory.build(
                success=False,
                action=ACTION_DETECT_AND_TRANSLATE,
                message="Translation failed.",
                error=safe_error_text(error),
                error_code="ERROR",
            )


translation_agent = TranslationAgent()


def translate(
    text: Any,
    target_language: Any = "urdu",
    source_language: Any = "auto",
) -> Dict[str, Any]:
    return translation_agent.translate(text, target_language, source_language)


def detect_and_translate(text: Any) -> Dict[str, Any]:
    return translation_agent.detect_and_translate(text)