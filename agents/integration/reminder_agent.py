from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol

from memory.vector_memory import store_memory


CAPABILITY_MODE = "real"
TRUST_LEVEL = "safe"
AGENT_NAME = "reminder"

ACTION_ADD = "add_reminder"
ACTION_LIST = "get_reminders"
ACTION_DELETE = "delete_reminder"
ACTION_COMPLETE = "complete_reminder"
ACTION_FIND_DUE = "find_due_reminders"

REMINDERS_FILE = Path("memory/reminders.json")
DATETIME_FORMAT = "%Y-%m-%d %H:%M"
VALID_STATUSES = {"active", "completed", "deleted"}


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
class ReminderItem:
    id: int
    text: str
    time: Optional[str] = None
    date: Optional[str] = None
    created: str = ""
    status: str = "active"
    completed_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class ReminderAgentError(Exception):
    error_code = "REMINDER_AGENT_ERROR"

    def __init__(self, message: str, *, user_message: Optional[str] = None) -> None:
        super().__init__(message)
        self.user_message = user_message or message


class InvalidReminderTextError(ReminderAgentError):
    error_code = "INVALID_REMINDER_TEXT"


class InvalidReminderIdError(ReminderAgentError):
    error_code = "INVALID_REMINDER_ID"


class ReminderNotFoundError(ReminderAgentError):
    error_code = "REMINDER_NOT_FOUND"


class InvalidStatusError(ReminderAgentError):
    error_code = "INVALID_STATUS"


class ReminderStorageError(ReminderAgentError):
    error_code = "STORAGE_ERROR"


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


class ReminderValidator:
    @staticmethod
    def clean_optional(value: Any) -> Optional[str]:
        if value is None:
            return None
        text = str(value).strip()
        return text if text else None

    @staticmethod
    def validate_text(text: Any) -> str:
        cleaned = ReminderValidator.clean_optional(text)
        if not cleaned:
            raise InvalidReminderTextError(
                "Missing reminder text.",
                user_message="Provide reminder text.",
            )
        return cleaned

    @staticmethod
    def validate_status(status: Any) -> Optional[str]:
        cleaned = ReminderValidator.clean_optional(status)
        if cleaned is None:
            return None

        normalized = cleaned.lower()
        if normalized not in VALID_STATUSES:
            raise InvalidStatusError(
                "Invalid status.",
                user_message="Use active, completed, or deleted.",
            )
        return normalized

    @staticmethod
    def validate_id(reminder_id: Any) -> int:
        try:
            parsed = int(reminder_id)
        except Exception as error:
            raise InvalidReminderIdError(
                "Invalid ID.",
                user_message="Provide numeric ID.",
            ) from error

        if parsed <= 0:
            raise InvalidReminderIdError(
                "Invalid ID.",
                user_message="Provide valid positive ID.",
            )

        return parsed


class ReminderRepository:
    def __init__(self, *, file_path: Path = REMINDERS_FILE) -> None:
        self.file_path = file_path

    def load(self) -> List[ReminderItem]:
        if not self.file_path.exists():
            return []

        try:
            with self.file_path.open("r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return []

        reminders: List[ReminderItem] = []
        for item in data if isinstance(data, list) else []:
            try:
                reminders.append(ReminderItem(**item))
            except Exception:
                continue

        return reminders

    def save(self, reminders: List[ReminderItem]) -> None:
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.file_path.with_suffix(".tmp")

            with tmp.open("w", encoding="utf-8") as f:
                json.dump(
                    [r.to_dict() for r in reminders],
                    f,
                    indent=2,
                    ensure_ascii=False,
                )

            tmp.replace(self.file_path)
        except Exception as error:
            raise ReminderStorageError(
                "Save failed.",
                user_message="Couldn't save reminders.",
            ) from error

    @staticmethod
    def next_id(reminders: List[ReminderItem]) -> int:
        return max((r.id for r in reminders), default=0) + 1


class ReminderFormatter:
    @staticmethod
    def format_reminder(r: ReminderItem) -> str:
        return f"[{AGENT_NAME.upper()}] {r.id}. {r.text} ({r.date or '-'} {r.time or '-'}) [{r.status}]"

    @staticmethod
    def format_list(reminders: List[ReminderItem]) -> str:
        if not reminders:
            return f"[{AGENT_NAME.upper()}] No reminders."
        return "\n".join(ReminderFormatter.format_reminder(r) for r in reminders)


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


class ReminderAgent:
    def __init__(self) -> None:
        self.repo = ReminderRepository()
        self.validator = ReminderValidator()
        self.formatter = ReminderFormatter()
        self.memory = MemoryManager()

    @staticmethod
    def _now() -> str:
        return datetime.now().strftime(DATETIME_FORMAT)

    def add_reminder(
        self,
        text: Any,
        time: Any = None,
        date: Any = None,
    ) -> Dict[str, Any]:
        try:
            reminders = self.repo.load()

            reminder = ReminderItem(
                id=self.repo.next_id(reminders),
                text=self.validator.validate_text(text),
                time=self.validator.clean_optional(time),
                date=self.validator.clean_optional(date),
                created=self._now(),
            )

            reminders.append(reminder)
            self.repo.save(reminders)

            self.memory.maybe_store(
                "reminder_add",
                {"id": reminder.id, "text": reminder.text},
            )

            return ResultFactory.build(
                success=True,
                action=ACTION_ADD,
                message=self.formatter.format_reminder(reminder),
                data=reminder.to_dict(),
            )

        except ReminderAgentError as error:
            return ResultFactory.build(
                success=False,
                action=ACTION_ADD,
                message=error.user_message,
                error=safe_error_text(error),
                error_code=error.error_code,
            )

        except Exception as error:
            return ResultFactory.build(
                success=False,
                action=ACTION_ADD,
                message="Failed.",
                error=safe_error_text(error),
                error_code="ERROR",
            )

    def get_reminders(self, status: Any = "active") -> Dict[str, Any]:
        try:
            reminders = self.repo.load()
            validated_status = self.validator.validate_status(status)

            if validated_status:
                reminders = [r for r in reminders if r.status == validated_status]

            return ResultFactory.build(
                success=True,
                action=ACTION_LIST,
                message=self.formatter.format_list(reminders),
                data={
                    "count": len(reminders),
                    "items": [r.to_dict() for r in reminders],
                },
            )

        except ReminderAgentError as error:
            return ResultFactory.build(
                success=False,
                action=ACTION_LIST,
                message=error.user_message,
                error=safe_error_text(error),
                error_code=error.error_code,
            )

        except Exception as error:
            return ResultFactory.build(
                success=False,
                action=ACTION_LIST,
                message="Failed.",
                error=safe_error_text(error),
                error_code="ERROR",
            )

    def delete_reminder(self, reminder_id: Any) -> Dict[str, Any]:
        try:
            rid = self.validator.validate_id(reminder_id)
            reminders = self.repo.load()

            if not any(r.id == rid for r in reminders):
                raise ReminderNotFoundError(
                    "Not found.",
                    user_message="Reminder not found.",
                )

            updated = [r for r in reminders if r.id != rid]
            self.repo.save(updated)

            self.memory.maybe_store("reminder_delete", {"id": rid})

            return ResultFactory.build(
                success=True,
                action=ACTION_DELETE,
                message=f"[{AGENT_NAME.upper()}] Deleted {rid}",
            )

        except ReminderAgentError as error:
            return ResultFactory.build(
                success=False,
                action=ACTION_DELETE,
                message=error.user_message,
                error=safe_error_text(error),
                error_code=error.error_code,
            )

        except Exception as error:
            return ResultFactory.build(
                success=False,
                action=ACTION_DELETE,
                message="Failed.",
                error=safe_error_text(error),
                error_code="ERROR",
            )

    def complete_reminder(self, reminder_id: Any) -> Dict[str, Any]:
        try:
            rid = self.validator.validate_id(reminder_id)
            reminders = self.repo.load()

            reminder = next((r for r in reminders if r.id == rid), None)
            if not reminder:
                raise ReminderNotFoundError(
                    "Not found.",
                    user_message="Reminder not found.",
                )

            reminder.status = "completed"
            reminder.completed_at = self._now()

            self.repo.save(reminders)

            self.memory.maybe_store("reminder_complete", {"id": rid})

            return ResultFactory.build(
                success=True,
                action=ACTION_COMPLETE,
                message=f"[{AGENT_NAME.upper()}] Completed {rid}",
            )

        except ReminderAgentError as error:
            return ResultFactory.build(
                success=False,
                action=ACTION_COMPLETE,
                message=error.user_message,
                error=safe_error_text(error),
                error_code=error.error_code,
            )

        except Exception as error:
            return ResultFactory.build(
                success=False,
                action=ACTION_COMPLETE,
                message="Failed.",
                error=safe_error_text(error),
                error_code="ERROR",
            )

    def find_due_reminders(
        self,
        current_date: Any = None,
        current_time: Any = None,
    ) -> Dict[str, Any]:
        try:
            reminders = self.repo.load()
            date = self.validator.clean_optional(current_date)
            time = self.validator.clean_optional(current_time)

            due = [
                r for r in reminders
                if r.status == "active"
                and (not date or r.date == date)
                and (not time or r.time == time)
            ]

            return ResultFactory.build(
                success=True,
                action=ACTION_FIND_DUE,
                message=self.formatter.format_list(due),
                data={
                    "count": len(due),
                    "items": [r.to_dict() for r in due],
                },
            )

        except Exception as error:
            return ResultFactory.build(
                success=False,
                action=ACTION_FIND_DUE,
                message="Failed.",
                error=safe_error_text(error),
                error_code="ERROR",
            )


reminder_agent = ReminderAgent()


def add_reminder(text: Any, time: Any = None, date: Any = None) -> Dict[str, Any]:
    return reminder_agent.add_reminder(text, time, date)


def get_reminders(status: Any = "active") -> Dict[str, Any]:
    return reminder_agent.get_reminders(status)


def delete_reminder(reminder_id: Any) -> Dict[str, Any]:
    return reminder_agent.delete_reminder(reminder_id)


def complete_reminder(reminder_id: Any) -> Dict[str, Any]:
    return reminder_agent.complete_reminder(reminder_id)


def find_due_reminders(
    current_date: Any = None,
    current_time: Any = None,
) -> Dict[str, Any]:
    return reminder_agent.find_due_reminders(current_date, current_time)