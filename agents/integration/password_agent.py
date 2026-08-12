from __future__ import annotations

import math
import re
import secrets
import string
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Tuple

from memory.vector_memory import store_memory


CAPABILITY_MODE = "real"
TRUST_LEVEL = "safe"
AGENT_NAME = "security"

ACTION_GENERATE_PASSWORD = "generate_password"
ACTION_CHECK_PASSWORD_STRENGTH = "check_password_strength"

SYMBOLS = "!@#$%^&*"
MIN_PASSWORD_LENGTH = 8
DEFAULT_PASSWORD_LENGTH = 16
MAX_PASSWORD_LENGTH = 28

COMMON_PASSWORDS = {
    "password",
    "123456",
    "123456789",
    "qwerty",
    "abc123",
    "password123",
    "admin",
    "letmein",
    "welcome",
    "iloveyou",
}


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
class PasswordGenerationPayload:
    password: str
    length: int
    strength: str
    entropy_bits: float
    includes_uppercase: bool
    includes_lowercase: bool
    includes_numbers: bool
    includes_symbols: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class PasswordStrengthPayload:
    masked_password: str
    length: int
    strength: str
    score: int
    max_score: int
    entropy_bits: float
    includes_uppercase: bool
    includes_lowercase: bool
    includes_numbers: bool
    includes_symbols: bool
    feedback: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class PasswordAgentError(Exception):
    error_code = "PASSWORD_AGENT_ERROR"

    def __init__(self, message: str, *, user_message: Optional[str] = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


class InvalidLengthError(PasswordAgentError):
    error_code = "INVALID_LENGTH"


class InvalidConfigurationError(PasswordAgentError):
    error_code = "INVALID_CONFIGURATION"


class InvalidPasswordError(PasswordAgentError):
    error_code = "INVALID_PASSWORD"


def safe_error_text(error: Exception) -> str:
    text = str(error).strip()
    return text if text else error.__class__.__name__


class MemoryManager:
    def __init__(
        self,
        *,
        writer: Optional[MemoryStore] = None,
        enabled: bool = False,
    ) -> None:
        self.writer = writer or store_memory
        self.enabled = enabled

    def maybe_store(self, label: str, metadata: Dict[str, Any]) -> Optional[str]:
        if not self.enabled:
            return None
        try:
            self.writer(label, metadata)
            return None
        except Exception as error:
            return safe_error_text(error)


class PasswordPolicy:
    def __init__(self, *, symbols: str = SYMBOLS) -> None:
        self.symbols = symbols

    @staticmethod
    def _parse_length(length: Any) -> int:
        try:
            parsed = int(length)
        except (TypeError, ValueError) as error:
            raise InvalidLengthError(
                "Invalid length.",
                user_message="Provide a valid password length.",
            ) from error

        if parsed < MIN_PASSWORD_LENGTH or parsed > MAX_PASSWORD_LENGTH:
            raise InvalidLengthError(
                "Length out of bounds.",
                user_message=f"Length must be between {MIN_PASSWORD_LENGTH} and {MAX_PASSWORD_LENGTH}.",
            )

        return parsed

    def validate_generation_config(
        self,
        *,
        length: Any,
        include_symbols: bool,
        include_numbers: bool,
    ) -> int:
        parsed_length = self._parse_length(length)

        required = 2 + int(include_numbers) + int(include_symbols)
        if parsed_length < required:
            raise InvalidConfigurationError(
                "Too short for required character mix.",
                user_message="Increase password length or reduce required complexity.",
            )

        return parsed_length

    @staticmethod
    def validate_password(password: Any) -> str:
        if password is None:
            raise InvalidPasswordError(
                "Invalid password.",
                user_message="Provide a valid password.",
            )

        value = str(password).strip()
        if not value:
            raise InvalidPasswordError(
                "Invalid password.",
                user_message="Provide a valid password.",
            )

        return value


class PasswordAnalyzer:
    def __init__(self, *, symbols: str = SYMBOLS) -> None:
        self.symbols = symbols

    def character_pool_size(
        self,
        *,
        includes_uppercase: bool,
        includes_lowercase: bool,
        includes_numbers: bool,
        includes_symbols: bool,
    ) -> int:
        size = 0
        if includes_uppercase:
            size += 26
        if includes_lowercase:
            size += 26
        if includes_numbers:
            size += 10
        if includes_symbols:
            size += len(self.symbols)
        return size

    @staticmethod
    def entropy_bits(length: int, pool_size: int) -> float:
        if length <= 0 or pool_size <= 1:
            return 0.0
        return round(length * math.log2(pool_size), 2)

    def detect_patterns(self, password: str) -> List[str]:
        feedback: List[str] = []
        lowered = password.lower()

        if lowered in COMMON_PASSWORDS:
            feedback.append("Avoid common passwords.")

        if re.search(r"(.)\1{2,}", password):
            feedback.append("Avoid repeated characters.")

        if re.search(r"(123|abc|qwerty)", lowered):
            feedback.append("Avoid predictable sequences.")

        return feedback

    def analyze_password(self, password: str) -> PasswordStrengthPayload:
        includes_uppercase = any(c.isupper() for c in password)
        includes_lowercase = any(c.islower() for c in password)
        includes_numbers = any(c.isdigit() for c in password)
        includes_symbols = any(c in self.symbols for c in password)

        pool_size = self.character_pool_size(
            includes_uppercase=includes_uppercase,
            includes_lowercase=includes_lowercase,
            includes_numbers=includes_numbers,
            includes_symbols=includes_symbols,
        )

        entropy = self.entropy_bits(len(password), pool_size)
        feedback = self.detect_patterns(password)

        score = 0

        if len(password) >= 16:
            score += 3
        elif len(password) >= 12:
            score += 2
        elif len(password) >= 8:
            score += 1
        else:
            feedback.append("Use at least 12 characters.")

        score += int(includes_uppercase)
        score += int(includes_lowercase)
        score += int(includes_numbers)
        score += int(includes_symbols)

        if entropy >= 80:
            score += 1

        if score >= 8:
            strength = "VERY STRONG"
        elif score >= 6:
            strength = "STRONG"
        elif score >= 4:
            strength = "MEDIUM"
        else:
            strength = "WEAK"

        return PasswordStrengthPayload(
            masked_password="*" * len(password),
            length=len(password),
            strength=strength,
            score=score,
            max_score=10,
            entropy_bits=entropy,
            includes_uppercase=includes_uppercase,
            includes_lowercase=includes_lowercase,
            includes_numbers=includes_numbers,
            includes_symbols=includes_symbols,
            feedback=feedback,
        )


class PasswordGenerator:
    def __init__(self, *, symbols: str = SYMBOLS) -> None:
        self.symbols = symbols
        self.random = secrets.SystemRandom()

    def _build_charset(
        self,
        *,
        include_symbols: bool,
        include_numbers: bool,
    ) -> Tuple[str, List[str]]:
        charset = string.ascii_letters
        required = [
            self.random.choice(string.ascii_uppercase),
            self.random.choice(string.ascii_lowercase),
        ]

        if include_numbers:
            charset += string.digits
            required.append(self.random.choice(string.digits))

        if include_symbols:
            charset += self.symbols
            required.append(self.random.choice(self.symbols))

        return charset, required

    def generate(
        self,
        *,
        length: int,
        include_symbols: bool,
        include_numbers: bool,
    ) -> str:
        charset, required = self._build_charset(
            include_symbols=include_symbols,
            include_numbers=include_numbers,
        )

        remaining = length - len(required)
        password_chars = required + [self.random.choice(charset) for _ in range(remaining)]
        self.random.shuffle(password_chars)
        return "".join(password_chars)


class PasswordFormatter:
    @staticmethod
    def format_generation(payload: PasswordGenerationPayload) -> str:
        return (
            f"Password: {payload.password}\n"
            f"Strength: {payload.strength}\n"
            f"Entropy: {payload.entropy_bits} bits"
        )

    @staticmethod
    def format_strength(payload: PasswordStrengthPayload) -> str:
        result = (
            f"Strength: {payload.strength} ({payload.score}/{payload.max_score})\n"
            f"Entropy: {payload.entropy_bits} bits"
        )

        if payload.feedback:
            result += "\nImprovements:\n" + "\n".join(payload.feedback)

        return result


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


class PasswordAgent:
    def __init__(self) -> None:
        self.policy = PasswordPolicy()
        self.analyzer = PasswordAnalyzer()
        self.generator = PasswordGenerator()
        self.formatter = PasswordFormatter()
        self.memory = MemoryManager(enabled=False)

    def generate_password(
        self,
        length: Any = DEFAULT_PASSWORD_LENGTH,
        include_symbols: bool = True,
        include_numbers: bool = True,
    ) -> Dict[str, Any]:
        try:
            parsed_length = self.policy.validate_generation_config(
                length=length,
                include_symbols=include_symbols,
                include_numbers=include_numbers,
            )

            password = self.generator.generate(
                length=parsed_length,
                include_symbols=include_symbols,
                include_numbers=include_numbers,
            )

            analysis = self.analyzer.analyze_password(password)

            payload = PasswordGenerationPayload(
                password=password,
                length=parsed_length,
                strength=analysis.strength,
                entropy_bits=analysis.entropy_bits,
                includes_uppercase=analysis.includes_uppercase,
                includes_lowercase=analysis.includes_lowercase,
                includes_numbers=analysis.includes_numbers,
                includes_symbols=analysis.includes_symbols,
            )

            self.memory.maybe_store(
                "password_generated",
                {"length": parsed_length, "strength": analysis.strength},
            )

            return ResultFactory.build(
                success=True,
                action=ACTION_GENERATE_PASSWORD,
                message=self.formatter.format_generation(payload),
                data=payload.to_dict(),
            )

        except PasswordAgentError as error:
            return ResultFactory.build(
                success=False,
                action=ACTION_GENERATE_PASSWORD,
                message=error.user_message,
                error=safe_error_text(error),
                error_code=error.error_code,
            )

        except Exception as error:
            return ResultFactory.build(
                success=False,
                action=ACTION_GENERATE_PASSWORD,
                message="Failed to generate password.",
                error=safe_error_text(error),
                error_code="ERROR",
            )

    def check_password_strength(self, password: Any) -> Dict[str, Any]:
        try:
            validated_password = self.policy.validate_password(password)
            payload = self.analyzer.analyze_password(validated_password)

            self.memory.maybe_store(
                "password_checked",
                {"strength": payload.strength, "length": payload.length},
            )

            return ResultFactory.build(
                success=True,
                action=ACTION_CHECK_PASSWORD_STRENGTH,
                message=self.formatter.format_strength(payload),
                data=payload.to_dict(),
            )

        except PasswordAgentError as error:
            return ResultFactory.build(
                success=False,
                action=ACTION_CHECK_PASSWORD_STRENGTH,
                message=error.user_message,
                error=safe_error_text(error),
                error_code=error.error_code,
            )

        except Exception as error:
            return ResultFactory.build(
                success=False,
                action=ACTION_CHECK_PASSWORD_STRENGTH,
                message="Failed to check password strength.",
                error=safe_error_text(error),
                error_code="ERROR",
            )


password_agent = PasswordAgent()


def generate_password(
    length: Any = DEFAULT_PASSWORD_LENGTH,
    include_symbols: bool = True,
    include_numbers: bool = True,
) -> Dict[str, Any]:
    return password_agent.generate_password(
        length=length,
        include_symbols=include_symbols,
        include_numbers=include_numbers,
    )


def check_password_strength(password: Any) -> Dict[str, Any]:
    return password_agent.check_password_strength(password)