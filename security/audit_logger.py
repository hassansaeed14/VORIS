from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional


AUDIT_LOG_FILE = Path("memory/security_audit.jsonl")


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(tzinfo=None).strftime("%Y-%m-%d %H:%M:%S")


def _append_event(event: Dict[str, Any]) -> Dict[str, Any]:
    AUDIT_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with AUDIT_LOG_FILE.open("a", encoding="utf-8") as file:
        file.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def record_audit_event(
    *,
    action_name: str,
    allowed: bool,
    trust_level: str,
    reason: str,
    username: str | None = None,
    session_id: str | None = None,
) -> Dict[str, object]:
    event = {
        "timestamp": _timestamp(),
        "kind": "permission_evaluation",
        "action_name": action_name,
        "allowed": allowed,
        "trust_level": trust_level,
        "reason": reason,
        "username": username,
        "session_id": session_id,
    }
    return _append_event(event)


def log_action(
    *,
    action_name: str,
    session_id: str | None,
    result: str,
    trust_level: str | None = None,
    username: str | None = None,
    reason: str | None = None,
    meta: Dict[str, Any] | None = None,
) -> Dict[str, Any]:
    event = {
        "timestamp": _timestamp(),
        "kind": "action_execution",
        "action_name": str(action_name or "unknown"),
        "session_id": str(session_id or "default"),
        "result": str(result or "unknown"),
        "trust_level": trust_level,
        "username": username,
        "reason": reason,
        "meta": meta or {},
    }
    return _append_event(event)


def tail_audit_log(limit: int = 100, *, kinds: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
    if not AUDIT_LOG_FILE.exists():
        return []
    try:
        lines = AUDIT_LOG_FILE.read_text(encoding="utf-8").splitlines()
    except Exception:
        return []
    events: List[Dict[str, Any]] = []
    allowed_kinds = set(kinds) if kinds else None
    for line in lines[-max(limit * 4, limit):]:
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
        except Exception:
            continue
        if allowed_kinds and item.get("kind") not in allowed_kinds:
            continue
        events.append(item)
    return events[-limit:]
