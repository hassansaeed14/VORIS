from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Optional

from security.audit_logger import log_action
from security.encryption_utils import hash_secret, verify_secret
from security.phone_registry import get_phone


OTP_STATE_FILE = Path("memory/otp_state.json")
OTP_EXPIRY_SECONDS = 120
OTP_MAX_ATTEMPTS = 5
OTP_CODE_LENGTH = 6


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _load_state() -> Dict[str, Dict[str, object]]:
    if not OTP_STATE_FILE.exists():
        return {}
    try:
        payload = json.loads(OTP_STATE_FILE.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _save_state(payload: Dict[str, Dict[str, object]]) -> None:
    OTP_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    OTP_STATE_FILE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


def _generate_code() -> str:
    return f"{secrets.randbelow(10 ** OTP_CODE_LENGTH):0{OTP_CODE_LENGTH}d}"


def _key(user_id: str, action_name: str) -> str:
    return f"{str(user_id or '').strip()}::{str(action_name or '').strip().lower()}"


def _audit(event: str, user_id: str, action_name: str, *, success: bool,
           reason: str, session_id: Optional[str] = None,
           meta: Optional[Dict[str, object]] = None) -> None:
    try:
        log_action(
            action_name=str(action_name or "").strip().lower() or "unknown",
            session_id=str(session_id or "otp"),
            result="success" if success else "failure",
            trust_level="critical",
            username=None,
            reason=f"otp_{event}: {reason}",
            meta={
                "layer": "otp_manager",
                "event": event,
                "user_id": str(user_id or ""),
                **dict(meta or {}),
            },
        )
    except Exception:
        pass


def request_otp(
    user_id: str,
    action_name: str,
    *,
    purpose: Optional[str] = None,
    ttl_seconds: int = OTP_EXPIRY_SECONDS,
    session_id: Optional[str] = None,
) -> Dict[str, object]:
    user_key = str(user_id or "").strip()
    if not user_key:
        _audit("request", user_id or "", action_name or "",
               success=False, reason="missing_user", session_id=session_id)
        return {"success": False, "reason": "user_id is required.", "status": "missing_user"}
    if not action_name:
        _audit("request", user_key, action_name or "",
               success=False, reason="missing_action", session_id=session_id)
        return {"success": False, "reason": "action_name is required.", "status": "missing_action"}

    phone_entry = get_phone(user_key)
    phone_number = None
    if phone_entry:
        phone_number = str(phone_entry.get("phone") or "")

    code = _generate_code()
    token = secrets.token_urlsafe(18)
    expires_at = (_now() + timedelta(seconds=int(ttl_seconds))).isoformat()

    payload = _load_state()
    payload[_key(user_key, action_name)] = {
        "token": token,
        "code_hash": hash_secret(code),
        "action_name": str(action_name).strip().lower(),
        "user_id": user_key,
        "session_id": str(session_id or "").strip() or None,
        "purpose": purpose or "",
        "issued_at": _now().isoformat(),
        "expires_at": expires_at,
        "attempts": 0,
        "consumed": False,
        "phone_recipient": phone_number or None,
    }
    _save_state(payload)

    _audit(
        "request", user_key, action_name,
        success=True, reason="issued", session_id=session_id,
        meta={"ttl_seconds": int(ttl_seconds), "delivery": "phone" if phone_number else "local"},
    )

    return {
        "success": True,
        "status": "issued",
        "token": token,
        "code": code,
        "action_name": str(action_name).strip().lower(),
        "expires_at": expires_at,
        "expires_in_seconds": int(ttl_seconds),
        "phone_recipient": phone_number,
        "delivery": "phone" if phone_number else "local",
        "session_id": str(session_id or "").strip() or None,
    }


def verify_otp(
    user_id: str,
    action_name: str,
    code: str,
    *,
    token: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, object]:
    user_key = str(user_id or "").strip()
    action_key = str(action_name or "").strip().lower()
    entry_key = _key(user_key, action_key)

    payload = _load_state()
    entry = payload.get(entry_key)
    if not entry:
        _audit("verify", user_key, action_key, success=False,
               reason="not_found", session_id=session_id)
        return {"success": False, "status": "not_found", "reason": "No OTP has been issued for this action."}

    try:
        expires_at = datetime.fromisoformat(str(entry.get("expires_at")))
    except Exception:
        payload.pop(entry_key, None)
        _save_state(payload)
        _audit("verify", user_key, action_key, success=False,
               reason="expired_invalid_state", session_id=session_id)
        return {"success": False, "status": "expired", "reason": "OTP expired."}

    if entry.get("consumed"):
        _audit("verify", user_key, action_key, success=False,
               reason="already_consumed", session_id=session_id)
        return {"success": False, "status": "consumed", "reason": "OTP already used."}

    if _now() > expires_at:
        payload.pop(entry_key, None)
        _save_state(payload)
        _audit("verify", user_key, action_key, success=False,
               reason="expired", session_id=session_id)
        return {"success": False, "status": "expired", "reason": "OTP expired."}

    if token and str(token) != str(entry.get("token")):
        entry["attempts"] = int(entry.get("attempts", 0)) + 1
        payload[entry_key] = entry
        _save_state(payload)
        _audit("verify", user_key, action_key, success=False,
               reason="invalid_token", session_id=session_id)
        return {"success": False, "status": "invalid_token", "reason": "OTP token mismatch."}

    bound_session = str(entry.get("session_id") or "").strip() or None
    if bound_session and session_id and bound_session != str(session_id).strip():
        entry["attempts"] = int(entry.get("attempts", 0)) + 1
        payload[entry_key] = entry
        _save_state(payload)
        _audit("verify", user_key, action_key, success=False,
               reason="session_mismatch", session_id=session_id,
               meta={"bound_session": bound_session})
        return {
            "success": False,
            "status": "session_mismatch",
            "reason": "OTP was issued for a different session.",
        }

    attempts = int(entry.get("attempts", 0))
    if attempts >= OTP_MAX_ATTEMPTS:
        payload.pop(entry_key, None)
        _save_state(payload)
        _audit("verify", user_key, action_key, success=False,
               reason="too_many_attempts", session_id=session_id,
               meta={"attempts": attempts})
        return {"success": False, "status": "too_many_attempts", "reason": "Too many failed attempts. Request a new OTP."}

    if not verify_secret(str(code or "").strip(), str(entry.get("code_hash") or "")):
        entry["attempts"] = attempts + 1
        payload[entry_key] = entry
        _save_state(payload)
        _audit("verify", user_key, action_key, success=False,
               reason="incorrect", session_id=session_id,
               meta={"attempts": entry["attempts"]})
        return {
            "success": False,
            "status": "incorrect",
            "reason": "Incorrect OTP.",
            "attempts_remaining": max(OTP_MAX_ATTEMPTS - entry["attempts"], 0),
        }

    entry["consumed"] = True
    entry["verified_at"] = _now().isoformat()
    entry["verified_session_id"] = str(session_id or bound_session or "").strip() or None
    payload[entry_key] = entry
    _save_state(payload)
    _audit("verify", user_key, action_key, success=True,
           reason="verified", session_id=session_id)
    return {
        "success": True,
        "status": "verified",
        "reason": "OTP verified.",
        "action_name": action_key,
        "session_id": entry["verified_session_id"],
    }


def invalidate_otp(user_id: str, action_name: str) -> bool:
    payload = _load_state()
    key = _key(user_id, action_name)
    if key in payload:
        payload.pop(key, None)
        _save_state(payload)
        _audit("invalidate", user_id, action_name, success=True, reason="invalidated")
        return True
    return False


def get_otp_status(user_id: str, action_name: str) -> Dict[str, object]:
    payload = _load_state()
    entry = payload.get(_key(user_id, action_name))
    if not entry:
        return {"exists": False}
    try:
        expires_at = datetime.fromisoformat(str(entry.get("expires_at")))
        expired = _now() > expires_at
    except Exception:
        expired = True
    return {
        "exists": True,
        "issued_at": entry.get("issued_at"),
        "expires_at": entry.get("expires_at"),
        "consumed": bool(entry.get("consumed")),
        "expired": expired,
        "attempts": int(entry.get("attempts", 0)),
        "session_id": entry.get("session_id"),
    }


def recent_otp_attempts(limit: int = 25) -> list:
    """Return the most-recent OTP events for status dashboards."""

    # We don't keep a separate rolling log for OTP here because each event is
    # already recorded in the main audit log via ``log_action``. This helper
    # just reads from the audit log to produce an OTP-only view.
    try:
        from security.audit_logger import tail_audit_log
        events = tail_audit_log(limit=limit * 4)
    except Exception:
        return []
    otp_events = [
        event for event in events
        if (event.get("meta") or {}).get("layer") == "otp_manager"
    ]
    return otp_events[-limit:]


def cleanup_expired() -> int:
    payload = _load_state()
    removed = 0
    for key, entry in list(payload.items()):
        try:
            expires_at = datetime.fromisoformat(str(entry.get("expires_at")))
        except Exception:
            payload.pop(key, None)
            removed += 1
            continue
        if _now() > expires_at or entry.get("consumed"):
            payload.pop(key, None)
            removed += 1
    if removed:
        _save_state(payload)
    return removed
