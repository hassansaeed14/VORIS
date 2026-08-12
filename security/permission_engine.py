"""Core permission checker — the gatekeeper every privileged action passes through.

Delegates trust-level resolution to ``config.permissions`` (the single source
of truth) and full evaluation to ``security.enforcement.enforce_action`` so
that OTP, PIN, lock checks, and audit logging all stay centralized.

Public surface::

    check_permission(action, session, context) -> {
        "allowed": bool,
        "action": str,
        "trust_level": str,
        "reason": str,
        "required_action": "allow" | "confirm" | "session_approval" | "otp" | "pin"
                           | "auth_required" | "session_expired" | "locked"
                           | "reauth_required",
        "next_step_hint": str,
        "status": str,
        ... plus enforcement metadata under "enforcement"
    }

Legacy helpers (``evaluate_permission``, ``classify_action`` etc.) are kept
as audit-logged shims so older brain backups continue to import without
error — but they no longer let an action pass silently. Every legacy call
emits an ``action_execution`` audit event so bypass attempts show up in
``memory/security_audit.jsonl``.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Mapping, Optional

from config.permissions import (
    DEFAULT_TRUST_LEVEL,
    NEXT_STEP_HINTS,
    TRUST_LEVELS,
    get_action_policy,
    get_next_step_hint,
    get_required_action,
    get_trust_level,
    normalize_action,
)
from security.audit_logger import log_action
from security.enforcement import enforce_action
from security.session_manager import get_login_session, is_action_approved


PERMISSIONS_FILE = "memory/permissions.json"


# Status → required_action mapping for resolved approvals. Statuses that
# reflect an auth/lock failure carry their own explicit required_action
# (auth_required, session_expired, locked, reauth_required) so callers
# get accurate guidance rather than a misleading "otp" suggestion.
_STATUS_TO_REQUIRED = {
    "approved": "allow",
    "needs_confirmation": "confirm",
    "confirm": "confirm",
    "needs_session_approval": "session_approval",
    "session_approval": "session_approval",
    "needs_pin": "pin",
    "pin": "pin",
    "pin_required": "pin",
    "otp_required": "otp",
    "auth_required": "auth_required",
    "session_expired": "session_expired",
    "reauth_required": "auth_required",
    "locked": "locked",
}


def _coerce_context(context: Any) -> Dict[str, Any]:
    if not context:
        return {}
    if isinstance(context, Mapping):
        return dict(context)
    return {}


def _session_snapshot(session: Any) -> Dict[str, Any]:
    """Normalize whatever the caller passed as ``session`` into a dict.

    Accepts a session token (str), a session dict, or None. Resolves the
    token to the canonical session record when possible so the caller never
    has to pre-resolve it.
    """

    if session is None:
        return {}
    if isinstance(session, str):
        resolved = get_login_session(session, touch=True) or {}
        return {"token": session, **resolved}
    if isinstance(session, Mapping):
        snapshot = dict(session)
        token = snapshot.get("token") or snapshot.get("session_token")
        if token and not snapshot.get("username"):
            resolved = get_login_session(str(token), touch=True) or {}
            snapshot = {**resolved, **snapshot}
        return snapshot
    return {}


def _required_action_from_enforcement(trust_level: str, access: Dict[str, Any]) -> str:
    # Prefer the explicit required_action set by enforce_action — it already
    # knows exactly which gate the caller hit (otp, pin, auth_required, …).
    explicit = str(access.get("required_action") or "").strip().lower()
    if explicit:
        return explicit
    if access.get("allowed"):
        return "allow"
    status = str(access.get("status") or "").strip().lower()
    if status in _STATUS_TO_REQUIRED:
        return _STATUS_TO_REQUIRED[status]
    return get_required_action(trust_level)


def check_permission(
    action: str,
    session: Any = None,
    context: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """Decide whether ``action`` may run for ``session``.

    ``session`` may be a session token string, a session dict (as returned
    by ``get_login_session``), or ``None`` for unauthenticated callers.
    ``context`` carries per-call signals (``confirmed``, ``pin``, ``otp``,
    ``otp_token``, ``resource_id``, ``session_id``, ``require_auth``, ``meta``).

    The decision is ALWAYS recorded to the audit log via ``enforce_action``
    — there is no silent path. Every return value carries ``next_step_hint``
    so UI and API layers can respond uniformly.
    """

    ctx = _coerce_context(context)
    action_key = normalize_action(action)
    policy = get_action_policy(action_key)
    trust_level = policy.trust_level
    if trust_level not in TRUST_LEVELS:
        trust_level = DEFAULT_TRUST_LEVEL

    snapshot = _session_snapshot(session)
    session_token = (
        ctx.get("session_token")
        or snapshot.get("token")
        or snapshot.get("session_token")
    )
    username = ctx.get("username") or snapshot.get("username")
    user_id = ctx.get("user_id") or snapshot.get("user_id")
    session_id = str(
        ctx.get("session_id")
        or snapshot.get("session_id")
        or "runtime"
    )

    require_auth = bool(ctx.get("require_auth", trust_level != "safe"))

    access = enforce_action(
        action_key,
        username=username,
        user_id=user_id,
        session_id=session_id,
        session_token=session_token,
        confirmed=bool(ctx.get("confirmed", False)),
        pin=ctx.get("pin"),
        otp=ctx.get("otp"),
        otp_token=ctx.get("otp_token"),
        resource_id=ctx.get("resource_id"),
        require_auth=require_auth,
        trust_level_override=trust_level,
        meta={
            "layer": "permission_engine",
            **dict(ctx.get("meta") or {}),
        },
    )

    required_action = _required_action_from_enforcement(trust_level, access)
    next_step_hint = str(access.get("next_step_hint") or get_next_step_hint(required_action))
    result = {
        "allowed": bool(access.get("allowed")),
        "action": action_key,
        "trust_level": str(access.get("trust_level") or trust_level),
        "reason": str(access.get("reason") or ""),
        "required_action": required_action,
        "next_step_hint": next_step_hint,
        "status": access.get("status"),
        "session_id": session_id,
        "policy": policy.to_dict(),
        "enforcement": access,
    }
    return result


def has_session_approval(session_id: str, action: str) -> bool:
    """Thin wrapper so other modules don't have to import session_manager."""

    return bool(is_action_approved(session_id, normalize_action(action)))


# ---------------------------------------------------------------------------
# Legacy helpers — kept so older callers (brain/core_ai_backup*.py and any
# persisted memory/permissions.json overrides) continue to work. Each of
# these now emits an audit event so unauthorized bypass attempts show up in
# the security log. New code MUST use ``check_permission`` directly.
# ---------------------------------------------------------------------------


def _default_permissions() -> Dict[str, Any]:
    return {
        "policy_mode": "balanced",
        "action_rules": {
            "safe": "allow",
            "private": "ask",
            "sensitive": "session",
            "critical": "pin",
        },
        "trusted_sessions": {},
        "custom_rules": {},
    }


def load_permissions() -> Dict[str, Any]:
    if not os.path.exists(PERMISSIONS_FILE):
        return _default_permissions()
    try:
        with open(PERMISSIONS_FILE, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except Exception:
        return _default_permissions()
    for key, value in _default_permissions().items():
        data.setdefault(key, value)
    return data


def save_permissions(data: Dict[str, Any]) -> None:
    os.makedirs(os.path.dirname(PERMISSIONS_FILE), exist_ok=True)
    with open(PERMISSIONS_FILE, "w", encoding="utf-8") as handle:
        json.dump(data, handle, indent=4, ensure_ascii=False)


def classify_action(command: str) -> str:
    """Best-effort trust-level classification for a freeform command string."""

    text = str(command or "").strip().lower()
    if not text:
        return "safe"
    direct = get_trust_level(text)
    if direct != DEFAULT_TRUST_LEVEL or text in {"general", "greeting"}:
        return direct

    critical_keywords = (
        "buy", "purchase", "pay", "payment", "send money",
        "credit card", "debit card", "unlock locked chat",
        "delete all", "delete file", "delete files", "wipe", "factory reset",
        "change password", "password", "otp", "pin", "bank", "banking",
        "credentials",
    )
    sensitive_keywords = (
        "login", "log in", "sign in", "send email", "send message",
        "upload file", "modify file", "write file", "type ", "enter ",
        "ask it to", "tell it to",
    )
    private_keywords = (
        "open whatsapp", "open gallery", "open files",
        "show my history", "show my chats", "view memory",
    )

    if any(keyword in text for keyword in critical_keywords):
        return "critical"
    if any(keyword in text for keyword in sensitive_keywords):
        return "sensitive"
    if any(keyword in text for keyword in private_keywords):
        return "private"
    return "safe"


def evaluate_permission(command: str) -> Dict[str, Any]:
    """Legacy shim — prefer ``check_permission``.

    Classifies ``command`` and returns a dict compatible with the old API.
    Always writes an audit event so a bypass via this legacy API is
    visible in the security log.
    """

    trust_level = classify_action(command)
    required = get_required_action(trust_level)
    allowed = required == "allow"
    log_action(
        action_name=normalize_action(command),
        session_id="legacy",
        result="allowed" if allowed else "needs_approval",
        trust_level=trust_level,
        reason=f"legacy evaluate_permission -> {required}",
        meta={"layer": "permission_engine.legacy"},
    )
    return {
        "allowed": allowed,
        "action_level": trust_level,
        "rule": required,
        "reason": (
            "This action is allowed by current policy."
            if allowed
            else f"This action needs: {required}."
        ),
        "next_step_hint": NEXT_STEP_HINTS.get(required, NEXT_STEP_HINTS["confirm"]),
    }


def get_action_rule(action_level: str, command: str | None = None) -> str:
    return get_required_action(action_level)


def allow_for_session(command: str, minutes: int = 30) -> None:
    """Legacy helper — stores approval in ``memory/permissions.json``.

    New code MUST use ``security.session_manager.approve_action`` instead,
    which stores approvals in the canonical session approvals file AND
    passes through the audit trail. This shim now emits an audit event so
    usage is visible, but the stored approval only affects legacy callers.
    """

    data = load_permissions()
    expires = datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(minutes=minutes)
    data.setdefault("trusted_sessions", {})[normalize_action(command)] = {
        "expires_at": expires.strftime("%Y-%m-%d %H:%M:%S"),
    }
    save_permissions(data)
    log_action(
        action_name=normalize_action(command),
        session_id="legacy",
        result="allowed",
        trust_level=None,
        reason=f"legacy allow_for_session (ttl={minutes}m)",
        meta={"layer": "permission_engine.legacy"},
    )


def is_session_allowed(command: str) -> bool:
    data = load_permissions()
    trusted = data.get("trusted_sessions", {})
    key = normalize_action(command)
    if key not in trusted:
        return False
    try:
        expires = datetime.strptime(trusted[key]["expires_at"], "%Y-%m-%d %H:%M:%S")
        if datetime.now(timezone.utc).replace(tzinfo=None) <= expires:
            return True
    except Exception:
        pass
    trusted.pop(key, None)
    data["trusted_sessions"] = trusted
    save_permissions(data)
    return False


def set_custom_rule(command: str, rule: str) -> bool:
    rule = str(rule or "").strip().lower()
    if rule not in ("allow", "ask", "session", "pin", "deny"):
        return False
    data = load_permissions()
    data.setdefault("custom_rules", {})[normalize_action(command)] = rule
    data["policy_mode"] = "custom"
    save_permissions(data)
    log_action(
        action_name=normalize_action(command),
        session_id="legacy",
        result="allowed",
        trust_level=None,
        reason=f"legacy set_custom_rule -> {rule}",
        meta={"layer": "permission_engine.legacy"},
    )
    return True


def get_policy_mode() -> str:
    return load_permissions().get("policy_mode", "balanced")


def set_policy_mode(mode: str) -> bool:
    mode = str(mode or "").strip().lower()
    if mode not in ("relaxed", "balanced", "strict", "custom"):
        return False
    data = load_permissions()
    data["policy_mode"] = mode
    save_permissions(data)
    return True
