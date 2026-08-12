from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional


PHONE_REGISTRY_FILE = Path("memory/phone_registry.json")
_PHONE_PATTERN = re.compile(r"^\+?[0-9]{7,20}$")


def _normalize_phone(phone: str) -> str:
    cleaned = re.sub(r"[\s\-\(\)]", "", str(phone or ""))
    return cleaned.strip()


def _now() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")


def _load() -> Dict[str, Dict[str, str]]:
    if not PHONE_REGISTRY_FILE.exists():
        return {}
    try:
        payload = json.loads(PHONE_REGISTRY_FILE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _save(payload: Dict[str, Dict[str, str]]) -> None:
    PHONE_REGISTRY_FILE.parent.mkdir(parents=True, exist_ok=True)
    PHONE_REGISTRY_FILE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def is_valid_phone(phone: str) -> bool:
    return bool(_PHONE_PATTERN.match(_normalize_phone(phone)))


def register_phone(user_id: str, phone: str) -> Dict[str, object]:
    user_key = str(user_id or "").strip()
    if not user_key:
        return {"success": False, "reason": "user_id is required."}
    normalized = _normalize_phone(phone)
    if not is_valid_phone(normalized):
        return {"success": False, "reason": "Phone number format is invalid."}

    payload = _load()
    payload[user_key] = {
        "phone": normalized,
        "verified": False,
        "updated_at": _now(),
    }
    _save(payload)
    return {"success": True, "user_id": user_key, "phone": normalized}


def mark_phone_verified(user_id: str) -> bool:
    user_key = str(user_id or "").strip()
    payload = _load()
    entry = payload.get(user_key)
    if not entry:
        return False
    entry["verified"] = True
    entry["verified_at"] = _now()
    payload[user_key] = entry
    _save(payload)
    return True


def get_phone(user_id: str) -> Optional[Dict[str, object]]:
    user_key = str(user_id or "").strip()
    entry = _load().get(user_key)
    if not entry:
        return None
    return dict(entry)


def remove_phone(user_id: str) -> bool:
    user_key = str(user_id or "").strip()
    payload = _load()
    if user_key in payload:
        payload.pop(user_key, None)
        _save(payload)
        return True
    return False


def list_phones() -> List[Dict[str, object]]:
    payload = _load()
    return [
        {"user_id": user_id, **entry}
        for user_id, entry in payload.items()
    ]
