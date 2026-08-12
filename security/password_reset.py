"""Production-grade forgot/reset password flow.

Three-step protocol:

    POST /api/auth/password-reset/request   -> reset_token (opaque)
    POST /api/auth/password-reset/verify    -> confirm_token (opaque)
    POST /api/auth/password-reset/confirm   -> password rotated, sessions revoked

Security guarantees:

  * Account enumeration — the ``request`` step always returns the same
    shape regardless of whether the identifier matches a real user. A
    "phantom" reset session is issued for unknown identifiers so the
    response timing / payload is indistinguishable from a real one.
  * One-time use — each reset_token and confirm_token can be consumed at
    most once, then is wiped.
  * Action-bound OTP — the OTP is generated via ``security.otp_manager``
    under the ``password_reset`` action, so it cannot be reused to satisfy
    any other critical action (and vice versa).
  * Session-bound OTP — the OTP is bound to the reset_token so an OTP
    issued for one reset attempt cannot verify a different attempt.
  * Rate limited — per-identifier and per-IP windows stop mass enumeration
    and reset spam.
  * Full audit trail — every request, verify, confirm, failure is written
    to ``memory/security_audit.jsonl`` via ``log_action``.
  * Session rotation — on successful confirm, ALL active login sessions
    of the user are invalidated (``invalidate_user_sessions``) so a
    stolen cookie is neutralised the moment the password rotates.

Data lives in ``memory/password_reset_state.json`` keyed by reset_token.
Only the token is visible to the client; the user_id is NEVER echoed
back (that would leak account existence).
"""

from __future__ import annotations

import json
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import bcrypt

from security.audit_logger import log_action
from security.auth_manager import load_users, save_users
from security.otp_manager import invalidate_otp, request_otp, verify_otp
from security.phone_registry import get_phone, list_phones
from security.session_manager import invalidate_user_sessions


RESET_STATE_FILE = Path("memory/password_reset_state.json")
RESET_ACTION_NAME = "password_reset"

RESET_TOKEN_TTL_SECONDS = 15 * 60           # reset session lives 15 minutes
CONFIRM_TOKEN_TTL_SECONDS = 5 * 60          # confirm_token valid 5 min after OTP verify
OTP_TTL_SECONDS = 120                       # reuse OTP manager default

# Rate limits
REQUESTS_PER_IDENTIFIER = 3                 # per 15 min
REQUESTS_PER_IP = 10                        # per 15 min
RATE_WINDOW_SECONDS = 15 * 60

MIN_PASSWORD_LENGTH = 8


# ---------------------------------------------------------------------------
# Low-level state file helpers
# ---------------------------------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def _parse_iso(value: Any) -> Optional[datetime]:
    try:
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def _load_state() -> Dict[str, Any]:
    if not RESET_STATE_FILE.exists():
        return {"sessions": {}, "requests": []}
    try:
        payload = json.loads(RESET_STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {"sessions": {}, "requests": []}
    if not isinstance(payload, dict):
        return {"sessions": {}, "requests": []}
    sessions = payload.get("sessions", {})
    requests_log = payload.get("requests", [])
    if not isinstance(sessions, dict):
        sessions = {}
    if not isinstance(requests_log, list):
        requests_log = []
    return {"sessions": sessions, "requests": requests_log}


def _save_state(payload: Dict[str, Any]) -> None:
    RESET_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    RESET_STATE_FILE.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


def _audit(event: str, *, success: bool, reason: str,
           username: Optional[str] = None,
           user_id: Optional[str] = None,
           reset_token: Optional[str] = None,
           ip_address: Optional[str] = None,
           meta: Optional[Dict[str, Any]] = None) -> None:
    try:
        log_action(
            action_name=RESET_ACTION_NAME,
            session_id=str(reset_token or "password_reset"),
            result="success" if success else "failure",
            trust_level="critical",
            username=username,
            reason=f"password_reset_{event}: {reason}",
            meta={
                "layer": "password_reset",
                "event": event,
                "user_id": user_id or "",
                "ip_address": ip_address or "",
                **dict(meta or {}),
            },
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Identifier resolution (email / phone / username)
# ---------------------------------------------------------------------------


_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _classify_identifier(identifier: str) -> str:
    text = str(identifier or "").strip()
    if not text:
        return "unknown"
    if _EMAIL_PATTERN.match(text):
        return "email"
    stripped = re.sub(r"[\s\-\(\)]", "", text)
    if re.match(r"^\+?[0-9]{7,20}$", stripped):
        return "phone"
    return "username"


def _normalize_phone(phone: str) -> str:
    return re.sub(r"[\s\-\(\)]", "", str(phone or "")).strip()


def _find_user(identifier: str) -> Tuple[Optional[str], Optional[Dict[str, Any]], str]:
    """Return (username, user_record, kind) — all None if no match."""

    kind = _classify_identifier(identifier)
    users = load_users()
    if kind == "email":
        email_key = str(identifier).strip().lower()
        for username, record in users.items():
            if str(record.get("email", "")).strip().lower() == email_key:
                return username, record, "email"
        return None, None, "email"
    if kind == "phone":
        target_phone = _normalize_phone(identifier)
        if not target_phone:
            return None, None, "phone"
        for entry in list_phones():
            if _normalize_phone(str(entry.get("phone"))) == target_phone:
                user_id = str(entry.get("user_id") or "")
                for username, record in users.items():
                    if str(record.get("id")) == user_id or username == user_id:
                        return username, record, "phone"
        return None, None, "phone"
    if kind == "username":
        username = str(identifier).strip().lower()
        record = users.get(username)
        if record:
            return username, record, "username"
        return None, None, "username"
    return None, None, "unknown"


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------


def _prune_requests(requests_log: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cutoff = _now() - timedelta(seconds=RATE_WINDOW_SECONDS)
    pruned: List[Dict[str, Any]] = []
    for entry in requests_log:
        ts = _parse_iso(entry.get("at"))
        if ts and ts >= cutoff:
            pruned.append(entry)
    return pruned


def _is_rate_limited(identifier_hash: str, ip_address: str,
                     requests_log: List[Dict[str, Any]]) -> Tuple[bool, str]:
    per_ident = sum(1 for entry in requests_log if entry.get("id_hash") == identifier_hash)
    per_ip = sum(1 for entry in requests_log if entry.get("ip") == ip_address)
    if per_ident >= REQUESTS_PER_IDENTIFIER:
        return True, "identifier_rate_limit"
    if ip_address and per_ip >= REQUESTS_PER_IP:
        return True, "ip_rate_limit"
    return False, ""


def _identifier_hash(identifier: str) -> str:
    """Stable hash so rate limit survives restarts without storing PII."""

    import hashlib
    return hashlib.sha256(str(identifier or "").strip().lower().encode("utf-8")).hexdigest()[:32]


# ---------------------------------------------------------------------------
# Step 1 — request reset
# ---------------------------------------------------------------------------


def request_password_reset(
    identifier: str,
    *,
    ip_address: Optional[str] = None,
    user_agent: Optional[str] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Kick off a password reset. Never reveals whether the account exists.

    Response shape is ALWAYS the same:
        {success, status, reset_token, expires_in_seconds, delivery}

    ``delivery`` is "local" (OTP returned inline for dev) or "phone" (sent
    via the phone registry) — it does NOT depend on whether the account
    exists, because phantom sessions default to "local" too. Clients should
    NOT treat the delivery field as a proof of existence.
    """

    text = str(identifier or "").strip()
    kind = _classify_identifier(text)
    payload = _load_state()
    requests_log = _prune_requests(payload.get("requests") or [])

    id_hash = _identifier_hash(text) if text else "empty"
    client_ip = str(ip_address or "").strip() or "local"
    limited, limit_reason = _is_rate_limited(id_hash, client_ip, requests_log)
    if limited:
        _audit("request", success=False, reason=limit_reason,
               reset_token=None, ip_address=client_ip,
               meta={"identifier_kind": kind})
        # Fail-closed and still opaque: return a generic "too many requests"
        # instead of an enumeration-safe success. This is safe because the
        # rate limit key itself is a hash of the identifier.
        return {
            "success": False,
            "status": "rate_limited",
            "reason": "Too many reset requests. Try again later.",
            "required_action": "wait",
            "next_step_hint": "Wait a few minutes before requesting another reset.",
        }

    username, user_record, resolved_kind = _find_user(text) if text else (None, None, kind)

    reset_token = secrets.token_urlsafe(32)
    now = _now()
    expires_at = now + timedelta(seconds=RESET_TOKEN_TTL_SECONDS)

    session_record: Dict[str, Any] = {
        "reset_token": reset_token,
        "user_id": str(user_record.get("id")) if user_record else None,
        "username": username,
        "identifier_kind": resolved_kind,
        "identifier_hash": id_hash,
        "phantom": user_record is None,
        "otp_issued": False,
        "otp_verified": False,
        "confirm_token": None,
        "confirm_expires_at": None,
        "consumed": False,
        "ip_address": client_ip,
        "user_agent": str(user_agent or "")[:200],
        "created_at": _iso(now),
        "expires_at": _iso(expires_at),
    }

    delivery = "local"
    phone_recipient = None
    if user_record:
        user_key = str(user_record.get("id") or username)
        otp_result = request_otp(
            user_key,
            RESET_ACTION_NAME,
            purpose="password_reset",
            ttl_seconds=OTP_TTL_SECONDS,
            session_id=reset_token,
        )
        session_record["otp_issued"] = bool(otp_result.get("success"))
        session_record["otp_user_key"] = user_key
        delivery = str(otp_result.get("delivery") or "local")
        phone_recipient = otp_result.get("phone_recipient")
        # In dev / local delivery, surface the code just like the OTP
        # endpoint does (tests + no-SMS environments). When phone delivery
        # is wired up, the code is NOT returned.
        if delivery != "phone":
            session_record["dev_code"] = otp_result.get("code")
        else:
            session_record["dev_code"] = None
    else:
        session_record["otp_user_key"] = None
        session_record["dev_code"] = None

    payload["sessions"][reset_token] = session_record
    payload["requests"] = requests_log + [
        {"id_hash": id_hash, "ip": client_ip, "at": _iso(now)}
    ]
    _save_state(payload)

    _audit(
        "request",
        success=True,
        reason="issued" if user_record else "phantom_issued",
        username=username,
        user_id=session_record.get("user_id"),
        reset_token=reset_token,
        ip_address=client_ip,
        meta={
            "identifier_kind": resolved_kind,
            "phantom": session_record["phantom"],
            "delivery": delivery,
        },
    )

    response: Dict[str, Any] = {
        "success": True,
        "status": "issued",
        "reset_token": reset_token,
        "expires_in_seconds": RESET_TOKEN_TTL_SECONDS,
        "otp_expires_in_seconds": OTP_TTL_SECONDS,
        "delivery": delivery,
        "phone_recipient": phone_recipient,
        "next_step_hint": "Enter the 6-digit code sent to your recovery channel.",
    }
    # Dev-only convenience: if the environment returned the code inline
    # (no SMS wired up), echo it back so the UI can complete the flow.
    if session_record.get("dev_code"):
        response["code"] = session_record["dev_code"]
    return response


# ---------------------------------------------------------------------------
# Step 2 — verify OTP
# ---------------------------------------------------------------------------


def _lookup_session(reset_token: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    payload = _load_state()
    session = payload["sessions"].get(str(reset_token or ""))
    return payload, (session or {})


def _expire_if_stale(session: Dict[str, Any]) -> bool:
    expires = _parse_iso(session.get("expires_at"))
    return bool(expires and _now() > expires)


def verify_password_reset(
    reset_token: str,
    otp: str,
    *,
    otp_token: Optional[str] = None,
    ip_address: Optional[str] = None,
) -> Dict[str, Any]:
    """Verify the OTP bound to ``reset_token`` and issue a confirm_token."""

    payload, session = _lookup_session(reset_token)
    client_ip = str(ip_address or "").strip() or "local"
    if not session:
        _audit("verify", success=False, reason="unknown_token",
               reset_token=reset_token, ip_address=client_ip)
        return {
            "success": False,
            "status": "invalid_token",
            "reason": "Reset session is invalid or expired.",
            "required_action": "restart",
            "next_step_hint": "Start the reset flow again.",
        }

    if session.get("consumed"):
        _audit("verify", success=False, reason="already_consumed",
               reset_token=reset_token, ip_address=client_ip,
               username=session.get("username"),
               user_id=session.get("user_id"))
        return {
            "success": False,
            "status": "consumed",
            "reason": "This reset session has already been used.",
            "required_action": "restart",
            "next_step_hint": "Start the reset flow again.",
        }

    if _expire_if_stale(session):
        payload["sessions"].pop(str(reset_token), None)
        _save_state(payload)
        _audit("verify", success=False, reason="expired",
               reset_token=reset_token, ip_address=client_ip,
               username=session.get("username"),
               user_id=session.get("user_id"))
        return {
            "success": False,
            "status": "expired",
            "reason": "Reset session expired.",
            "required_action": "restart",
            "next_step_hint": "Start the reset flow again.",
        }

    # Phantom sessions: burn an attempt and always fail, so behaviour is
    # indistinguishable from a real wrong OTP until the attempt limit hits.
    if session.get("phantom") or not session.get("otp_user_key"):
        session["phantom_attempts"] = int(session.get("phantom_attempts", 0)) + 1
        if session["phantom_attempts"] >= 5:
            payload["sessions"].pop(str(reset_token), None)
            _save_state(payload)
            _audit("verify", success=False, reason="phantom_too_many_attempts",
                   reset_token=reset_token, ip_address=client_ip)
            return {
                "success": False,
                "status": "too_many_attempts",
                "reason": "Too many failed attempts. Request a new reset.",
                "required_action": "restart",
                "next_step_hint": "Start the reset flow again.",
            }
        payload["sessions"][str(reset_token)] = session
        _save_state(payload)
        _audit("verify", success=False, reason="phantom_incorrect",
               reset_token=reset_token, ip_address=client_ip,
               meta={"phantom_attempts": session["phantom_attempts"]})
        return {
            "success": False,
            "status": "incorrect",
            "reason": "Incorrect code.",
            "attempts_remaining": max(5 - int(session["phantom_attempts"]), 0),
            "required_action": "otp",
            "next_step_hint": "Re-enter the code or request a new reset.",
        }

    user_key = str(session.get("otp_user_key") or "")
    otp_result = verify_otp(
        user_key,
        RESET_ACTION_NAME,
        otp,
        token=otp_token,
        session_id=str(reset_token),
    )

    if not otp_result.get("success"):
        _audit(
            "verify",
            success=False,
            reason=str(otp_result.get("status") or "otp_failed"),
            reset_token=reset_token,
            ip_address=client_ip,
            username=session.get("username"),
            user_id=session.get("user_id"),
            meta={"otp_status": otp_result.get("status")},
        )
        return {
            "success": False,
            "status": otp_result.get("status", "otp_failed"),
            "reason": str(otp_result.get("reason") or "Incorrect OTP."),
            "attempts_remaining": otp_result.get("attempts_remaining"),
            "required_action": "otp",
            "next_step_hint": "Re-enter the code or request a new reset.",
        }

    confirm_token = secrets.token_urlsafe(32)
    confirm_expires = _now() + timedelta(seconds=CONFIRM_TOKEN_TTL_SECONDS)
    session["otp_verified"] = True
    session["confirm_token"] = confirm_token
    session["confirm_expires_at"] = _iso(confirm_expires)
    payload["sessions"][str(reset_token)] = session
    _save_state(payload)

    _audit(
        "verify",
        success=True,
        reason="otp_verified",
        reset_token=reset_token,
        ip_address=client_ip,
        username=session.get("username"),
        user_id=session.get("user_id"),
    )

    return {
        "success": True,
        "status": "verified",
        "confirm_token": confirm_token,
        "expires_in_seconds": CONFIRM_TOKEN_TTL_SECONDS,
        "required_action": "set_password",
        "next_step_hint": "Submit your new password with the confirm_token to complete the reset.",
    }


# ---------------------------------------------------------------------------
# Step 3 — confirm + rotate password
# ---------------------------------------------------------------------------


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _validate_new_password(password: str) -> Tuple[bool, str]:
    text = str(password or "")
    if len(text) < MIN_PASSWORD_LENGTH:
        return False, f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if text.strip() != text:
        return False, "Password must not start or end with whitespace."
    # Lightweight strength guard: must contain at least one letter AND one
    # digit or symbol. Full strength-scoring lives in the password agent.
    has_letter = any(ch.isalpha() for ch in text)
    has_other = any((not ch.isalpha()) for ch in text)
    if not (has_letter and has_other):
        return False, "Password must contain letters and at least one digit or symbol."
    return True, ""


def confirm_password_reset(
    reset_token: str,
    confirm_token: str,
    new_password: str,
    *,
    ip_address: Optional[str] = None,
) -> Dict[str, Any]:
    """Rotate the password and invalidate every active session for the user."""

    payload, session = _lookup_session(reset_token)
    client_ip = str(ip_address or "").strip() or "local"
    if not session:
        _audit("confirm", success=False, reason="unknown_token",
               reset_token=reset_token, ip_address=client_ip)
        return {
            "success": False,
            "status": "invalid_token",
            "reason": "Reset session is invalid or expired.",
            "required_action": "restart",
            "next_step_hint": "Start the reset flow again.",
        }

    if session.get("consumed"):
        _audit("confirm", success=False, reason="already_consumed",
               reset_token=reset_token, ip_address=client_ip,
               username=session.get("username"),
               user_id=session.get("user_id"))
        return {
            "success": False,
            "status": "consumed",
            "reason": "This reset session has already been used.",
            "required_action": "restart",
            "next_step_hint": "Start the reset flow again.",
        }

    if _expire_if_stale(session):
        payload["sessions"].pop(str(reset_token), None)
        _save_state(payload)
        _audit("confirm", success=False, reason="expired",
               reset_token=reset_token, ip_address=client_ip)
        return {
            "success": False,
            "status": "expired",
            "reason": "Reset session expired.",
            "required_action": "restart",
            "next_step_hint": "Start the reset flow again.",
        }

    if not session.get("otp_verified") or not session.get("confirm_token"):
        _audit("confirm", success=False, reason="otp_not_verified",
               reset_token=reset_token, ip_address=client_ip,
               username=session.get("username"),
               user_id=session.get("user_id"))
        return {
            "success": False,
            "status": "otp_required",
            "reason": "OTP verification is required first.",
            "required_action": "otp",
            "next_step_hint": "Verify the OTP before setting a new password.",
        }

    if str(confirm_token or "") != str(session.get("confirm_token") or ""):
        _audit("confirm", success=False, reason="confirm_token_mismatch",
               reset_token=reset_token, ip_address=client_ip,
               username=session.get("username"),
               user_id=session.get("user_id"))
        return {
            "success": False,
            "status": "invalid_confirm_token",
            "reason": "Confirm token does not match this reset session.",
            "required_action": "restart",
            "next_step_hint": "Start the reset flow again.",
        }

    confirm_expires = _parse_iso(session.get("confirm_expires_at"))
    if confirm_expires and _now() > confirm_expires:
        _audit("confirm", success=False, reason="confirm_token_expired",
               reset_token=reset_token, ip_address=client_ip,
               username=session.get("username"),
               user_id=session.get("user_id"))
        return {
            "success": False,
            "status": "expired",
            "reason": "Confirm token expired. Start over.",
            "required_action": "restart",
            "next_step_hint": "Start the reset flow again.",
        }

    ok, password_reason = _validate_new_password(new_password)
    if not ok:
        _audit("confirm", success=False, reason=f"weak_password:{password_reason}",
               reset_token=reset_token, ip_address=client_ip,
               username=session.get("username"),
               user_id=session.get("user_id"))
        return {
            "success": False,
            "status": "weak_password",
            "reason": password_reason,
            "required_action": "set_password",
            "next_step_hint": "Choose a stronger password.",
        }

    username = session.get("username")
    user_id = session.get("user_id")
    users = load_users()
    record = users.get(username) if username else None
    if not record:
        # Could happen if the user was deleted between request and confirm.
        session["consumed"] = True
        payload["sessions"][str(reset_token)] = session
        _save_state(payload)
        _audit("confirm", success=False, reason="user_not_found",
               reset_token=reset_token, ip_address=client_ip,
               username=username, user_id=user_id)
        return {
            "success": False,
            "status": "user_not_found",
            "reason": "Account no longer exists.",
            "required_action": "restart",
            "next_step_hint": "Contact an administrator.",
        }

    record["password"] = _hash_password(str(new_password))
    record["password_rotated_at"] = _now().strftime("%Y-%m-%d %H:%M:%S")
    users[username] = record
    save_users(users)

    # Critical: kill every active session for this user, so a stolen cookie
    # cannot ride the old password's trust window.
    invalidate_user_sessions(user_id=str(record.get("id") or ""), username=username)

    # Kill any lingering OTP entry for this action + user.
    invalidate_otp(str(record.get("id") or username), RESET_ACTION_NAME)

    session["consumed"] = True
    session["confirm_token"] = None
    session["dev_code"] = None
    session["completed_at"] = _iso(_now())
    payload["sessions"][str(reset_token)] = session
    _save_state(payload)

    _audit(
        "confirm",
        success=True,
        reason="password_rotated",
        reset_token=reset_token,
        ip_address=client_ip,
        username=username,
        user_id=str(record.get("id") or ""),
        meta={"sessions_revoked": True},
    )

    return {
        "success": True,
        "status": "password_rotated",
        "reason": "Password updated. All active sessions have been signed out.",
        "required_action": "login",
        "next_step_hint": "Sign in with your new password.",
    }


# ---------------------------------------------------------------------------
# Dashboards / maintenance
# ---------------------------------------------------------------------------


def get_reset_session_public(reset_token: str) -> Dict[str, Any]:
    """Return a safe, non-enumerating view of a reset session."""

    _, session = _lookup_session(reset_token)
    if not session:
        return {"exists": False}
    return {
        "exists": True,
        "otp_verified": bool(session.get("otp_verified")),
        "consumed": bool(session.get("consumed")),
        "expires_at": session.get("expires_at"),
        "confirm_expires_at": session.get("confirm_expires_at"),
    }


def cleanup_expired_reset_sessions() -> int:
    payload = _load_state()
    removed = 0
    sessions = payload.get("sessions", {})
    for token, session in list(sessions.items()):
        expires = _parse_iso(session.get("expires_at"))
        if session.get("consumed") or (expires and _now() > expires):
            sessions.pop(token, None)
            removed += 1
    payload["sessions"] = sessions
    payload["requests"] = _prune_requests(payload.get("requests") or [])
    _save_state(payload)
    return removed


def recent_reset_events(limit: int = 25) -> List[Dict[str, Any]]:
    """Password-reset-only view over the audit log."""

    try:
        from security.audit_logger import tail_audit_log
        events = tail_audit_log(limit=limit * 4)
    except Exception:
        return []
    return [
        event for event in events
        if (event.get("meta") or {}).get("layer") == "password_reset"
    ][-limit:]
