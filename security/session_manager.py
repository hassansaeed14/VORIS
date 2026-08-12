from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from security.security_config import ACTION_APPROVAL_FILE, AUTH_SESSION_IDLE_DELTA, SESSION_APPROVAL_DELTA, SESSIONS_FILE


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _read_json(path: Path, fallback: Any) -> Any:
    if not path.exists():
        return fallback
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload
    except Exception:
        return fallback


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def _hash_token(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def _load_login_sessions() -> Dict[str, Dict[str, Dict[str, str]]]:
    payload = _read_json(SESSIONS_FILE, {"sessions": {}})
    if not isinstance(payload, dict):
        return {"sessions": {}}
    sessions = payload.get("sessions", {})
    if not isinstance(sessions, dict):
        sessions = {}
    return {"sessions": sessions}


def _save_login_sessions(payload: Dict[str, Dict[str, Dict[str, str]]]) -> None:
    _write_json(SESSIONS_FILE, payload)


def create_login_session(*, user_id: str, username: str, ip_address: str, user_agent: str) -> str:
    raw_token = secrets.token_hex(32)
    token_hash = _hash_token(raw_token)
    payload = _load_login_sessions()
    sessions = payload["sessions"]

    stale_hashes = [
        key
        for key, entry in sessions.items()
        if entry.get("user_id") == user_id or entry.get("username") == username
    ]
    for stale_hash in stale_hashes:
        sessions.pop(stale_hash, None)

    sessions[token_hash] = {
        "user_id": user_id,
        "username": username,
        "ip_address": ip_address,
        "user_agent": user_agent,
        "created_at": _now().isoformat(),
        "last_seen_at": _now().isoformat(),
    }
    _save_login_sessions(payload)
    return raw_token


def get_login_session(token: str, *, touch: bool = True) -> Optional[Dict[str, str]]:
    if not token:
        return None
    payload = _load_login_sessions()
    sessions = payload["sessions"]
    token_hash = _hash_token(token)
    entry = sessions.get(token_hash)
    if not entry:
        return None

    try:
        last_seen_at = datetime.fromisoformat(entry["last_seen_at"])
    except Exception:
        sessions.pop(token_hash, None)
        _save_login_sessions(payload)
        return None

    if _now() - last_seen_at > AUTH_SESSION_IDLE_DELTA:
        sessions.pop(token_hash, None)
        _save_login_sessions(payload)
        return None

    if touch:
        entry["last_seen_at"] = _now().isoformat()
        sessions[token_hash] = entry
        _save_login_sessions(payload)
    return dict(entry)


def touch_login_session(token: str) -> Optional[Dict[str, str]]:
    """Force-update ``last_seen_at`` for a session without other side effects.

    Returns the refreshed session dict, or ``None`` if the session is gone.
    Used by request paths that want to re-arm the idle timer even when they
    aren't reading the full session payload.
    """

    return get_login_session(token, touch=True)


def session_age_seconds(token: str) -> Optional[int]:
    """How long ago was this session last active (in seconds)?

    Returns ``None`` if the session is missing or expired.
    """

    if not token:
        return None
    payload = _load_login_sessions()
    entry = payload["sessions"].get(_hash_token(token))
    if not entry:
        return None
    try:
        last_seen_at = datetime.fromisoformat(entry["last_seen_at"])
    except Exception:
        return None
    return max(int((_now() - last_seen_at).total_seconds()), 0)


def require_recent_auth(
    token: str,
    *,
    max_age_seconds: int = 300,
) -> Dict[str, Any]:
    """Verify ``token`` is valid AND was recently active.

    Critical actions (payment, password change, purchase, account delete, …)
    route through this gate so a dormant session cannot execute a destructive
    operation just because the 24-hour idle window hasn't elapsed yet.
    """

    age = session_age_seconds(token)
    if age is None:
        return {"valid": False, "reason": "expired_or_missing", "remaining_seconds": 0}
    if age > max_age_seconds:
        return {
            "valid": False,
            "reason": "reauth_required",
            "age_seconds": age,
            "max_age_seconds": int(max_age_seconds),
        }
    return {
        "valid": True,
        "reason": "recent",
        "age_seconds": age,
        "max_age_seconds": int(max_age_seconds),
    }


def describe_login_session(token: str) -> Dict[str, Any]:
    if not token:
        return {"valid": False, "reason": "no_session_token", "session": None}

    payload = _load_login_sessions()
    sessions = payload["sessions"]
    token_hash = _hash_token(token)
    entry = sessions.get(token_hash)
    if not entry:
        return {"valid": False, "reason": "expired_or_missing", "session": None}

    try:
        last_seen_at = datetime.fromisoformat(str(entry["last_seen_at"]))
    except Exception:
        sessions.pop(token_hash, None)
        _save_login_sessions(payload)
        return {"valid": False, "reason": "invalid_session_state", "session": None}

    expires_at = last_seen_at + AUTH_SESSION_IDLE_DELTA
    remaining_seconds = max(int((expires_at - _now()).total_seconds()), 0)
    if remaining_seconds <= 0:
        sessions.pop(token_hash, None)
        _save_login_sessions(payload)
        return {
            "valid": False,
            "reason": "expired_or_missing",
            "session": None,
            "expires_at": expires_at.isoformat(),
            "remaining_seconds": 0,
        }

    return {
        "valid": True,
        "reason": "active",
        "session": dict(entry),
        "expires_at": expires_at.isoformat(),
        "remaining_seconds": remaining_seconds,
    }


def invalidate_login_session(token: str) -> None:
    if not token:
        return
    payload = _load_login_sessions()
    payload["sessions"].pop(_hash_token(token), None)
    _save_login_sessions(payload)


def invalidate_user_sessions(*, user_id: str | None = None, username: str | None = None) -> None:
    payload = _load_login_sessions()
    sessions = payload["sessions"]
    for token_hash, entry in list(sessions.items()):
        if (user_id and entry.get("user_id") == user_id) or (username and entry.get("username") == username):
            sessions.pop(token_hash, None)
    _save_login_sessions(payload)


def list_login_sessions() -> list[dict[str, str]]:
    payload = _load_login_sessions()
    return [dict(item) for item in payload["sessions"].values()]


def _load_action_approvals() -> Dict[str, Dict[str, float]]:
    payload = _read_json(ACTION_APPROVAL_FILE, {})
    return payload if isinstance(payload, dict) else {}


def _save_action_approvals(payload: Dict[str, Dict[str, float]]) -> None:
    _write_json(ACTION_APPROVAL_FILE, payload)


def approve_action(session_id: str, action_name: str, *, minutes: int | None = None) -> Dict[str, object]:
    ttl_seconds = int((minutes * 60) if minutes is not None else SESSION_APPROVAL_DELTA.total_seconds())
    payload = _load_action_approvals()
    session_key = str(session_id or "default").strip()
    payload.setdefault(session_key, {})
    payload[session_key][str(action_name or "").strip().lower()] = (_now().timestamp() + ttl_seconds)
    _save_action_approvals(payload)
    return {"success": True, "session_id": session_key, "action_name": action_name}


def is_action_approved(session_id: str, action_name: str) -> bool:
    payload = _load_action_approvals()
    session_key = str(session_id or "default").strip()
    expiry = payload.get(session_key, {}).get(str(action_name or "").strip().lower())
    if not expiry:
        return False
    try:
        if _now().timestamp() <= float(expiry):
            return True
    except Exception:
        pass
    revoke_action(session_id, action_name)
    return False


def revoke_action(session_id: str, action_name: str) -> None:
    payload = _load_action_approvals()
    session_key = str(session_id or "default").strip()
    if session_key in payload:
        payload[session_key].pop(str(action_name or "").strip().lower(), None)
        _save_action_approvals(payload)


# ---------------------------------------------------------------------------
# OTP verification state (informational only — OTP is still single-use per
# critical action; this table lets the permission engine surface *when* an
# action was last verified without changing enforcement semantics).
# ---------------------------------------------------------------------------

from security.security_config import OTP_VERIFIED_FILE  # noqa: E402


def _load_otp_verifications() -> Dict[str, Dict[str, float]]:
    payload = _read_json(OTP_VERIFIED_FILE, {})
    return payload if isinstance(payload, dict) else {}


def _save_otp_verifications(payload: Dict[str, Dict[str, float]]) -> None:
    _write_json(OTP_VERIFIED_FILE, payload)


def mark_otp_verified(session_id: str, action_name: str, *, ttl_seconds: int = 120) -> None:
    payload = _load_otp_verifications()
    session_key = str(session_id or "default").strip()
    payload.setdefault(session_key, {})
    payload[session_key][str(action_name or "").strip().lower()] = _now().timestamp() + int(ttl_seconds)
    _save_otp_verifications(payload)


def was_otp_verified(session_id: str, action_name: str) -> bool:
    payload = _load_otp_verifications()
    session_key = str(session_id or "default").strip()
    expiry = payload.get(session_key, {}).get(str(action_name or "").strip().lower())
    if not expiry:
        return False
    try:
        return _now().timestamp() <= float(expiry)
    except Exception:
        return False
