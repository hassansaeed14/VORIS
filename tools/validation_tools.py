from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path


WORKSPACE_ROOT = Path(
    os.getenv("VORIS_WORKSPACE_ROOT") or Path(__file__).resolve().parents[1]
).resolve()


def validate_url(value: str) -> bool:
    return bool(re.match(r"^(https?://|www\.)\S+$", str(value or "").strip(), flags=re.IGNORECASE))


def validate_email(value: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", str(value or "").strip()))


def validate_number(value: object) -> bool:
    try:
        float(value)
        return True
    except Exception:
        return False


def validate_date_string(value: str, fmt: str = "%Y-%m-%d") -> bool:
    try:
        datetime.strptime(str(value or "").strip(), fmt)
        return True
    except Exception:
        return False


def normalize_language(value: str | None) -> str:
    normalized = str(value or "english").strip().lower()
    return normalized if normalized in {"english", "urdu", "arabic", "hindi", "punjabi", "french", "spanish"} else "english"


def validate_workspace_path(path_value: str | Path) -> bool:
    try:
        candidate = Path(path_value).expanduser().resolve()
    except Exception:
        return False
    return str(candidate).startswith(str(WORKSPACE_ROOT))
