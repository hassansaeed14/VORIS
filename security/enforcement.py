from __future__ import annotations

from typing import Any, Dict, Optional

from config.permissions import (
    NEXT_STEP_HINTS,
    get_action_policy,
    get_next_step_hint,
    requires_otp as policy_requires_otp,
    requires_pin as policy_requires_pin,
)
from security.audit_logger import log_action, record_audit_event
from security.lock_manager import is_locked
from security.otp_manager import verify_otp
from security.pin_manager import verify_pin
from security.session_manager import (
    get_login_session,
    is_action_approved,
    mark_otp_verified,
    require_recent_auth,
    session_age_seconds,
)
from security.trust_engine import ApprovalType, TrustLevel, evaluate_action


# Actions that are so dangerous they must be re-validated against a *fresh*
# session (not just the long-lived idle timer). Tuned in seconds.
CRITICAL_REAUTH_WINDOW_SECONDS = 300


def _structured_response(
    *,
    action_name: str,
    trust_level: str,
    allowed: bool,
    reason: str,
    required_action: str,
    status: str,
    approval_type: str,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Uniform shape returned by every enforce_action branch.

    Every privileged decision surfaces:
        action, trust_level, allowed, reason, required_action, next_step_hint

    plus the legacy ``status`` + ``approval_type`` fields the runtime already
    consumes. Additional branch-specific metadata rides under ``extra``.
    """

    payload: Dict[str, Any] = {
        "allowed": bool(allowed),
        "action": action_name,
        "action_name": action_name,
        "trust_level": trust_level,
        "reason": reason,
        "required_action": required_action,
        "next_step_hint": get_next_step_hint(required_action),
        "status": status,
        "approval_type": approval_type,
    }
    if extra:
        for key, value in extra.items():
            if key not in payload or payload[key] is None:
                payload[key] = value
    return payload


def _validate_session(
    session_token: Optional[str],
) -> Dict[str, Any]:
    if not session_token:
        return {"valid": False, "reason": "no_session_token", "session": None}
    session = get_login_session(session_token, touch=True)
    if not session:
        return {"valid": False, "reason": "expired_or_missing", "session": None}
    return {"valid": True, "reason": "active", "session": session}


def _needs_otp(action_name: str, trust_level: TrustLevel) -> bool:
    """Route OTP decision exclusively through ``config.permissions``.

    A ``critical`` trust level alone does NOT guarantee OTP — the policy for
    the action is authoritative. That way we can have, say, ``system_control``
    at critical without OTP (PIN only) but ``payment`` with both PIN + OTP.
    """

    return bool(policy_requires_otp(action_name))


def enforce_action(
    action_name: str,
    *,
    username: Optional[str] = None,
    user_id: Optional[str] = None,
    session_id: str = "default",
    session_token: Optional[str] = None,
    confirmed: bool = False,
    pin: Optional[str] = None,
    otp: Optional[str] = None,
    otp_token: Optional[str] = None,
    resource_id: Optional[str] = None,
    require_auth: bool = True,
    trust_level_override: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Single centralized guard for every privileged action in AURA.

    Runtime, agents, tools, and API routes MUST route through this before
    executing a sensitive or critical action. The returned dict always
    includes ``allowed``, ``action``, ``trust_level``, ``reason``,
    ``required_action`` and ``next_step_hint`` so callers can respond
    uniformly.
    """

    action_key = str(action_name or "").strip().lower() or "unknown"
    meta = dict(meta or {})
    policy = get_action_policy(action_key)

    # --- LOCK CHECK ------------------------------------------------------
    if resource_id and is_locked(resource_id):
        event = record_audit_event(
            action_name=action_key,
            allowed=False,
            trust_level="critical",
            reason="resource_locked",
            username=username,
            session_id=session_id,
        )
        log_action(
            action_name=action_key,
            session_id=session_id,
            result="blocked",
            trust_level="critical",
            username=username,
            reason="resource_locked",
            meta=meta,
        )
        return _structured_response(
            action_name=action_key,
            trust_level="critical",
            allowed=False,
            reason="Resource is locked.",
            required_action="locked",
            status="locked",
            approval_type="none",
            extra={"audit": event, "resource_id": resource_id},
        )

    # --- SESSION VALIDATION ---------------------------------------------
    session_check = (
        _validate_session(session_token)
        if session_token
        else {"valid": True, "reason": "not_required", "session": None}
    )
    active_session = session_check.get("session")
    if session_token and not session_check["valid"]:
        event = record_audit_event(
            action_name=action_key,
            allowed=False,
            trust_level="session",
            reason=f"session_{session_check['reason']}",
            username=username,
            session_id=session_id,
        )
        log_action(
            action_name=action_key,
            session_id=session_id,
            result="session_invalid",
            username=username,
            reason=session_check["reason"],
            meta=meta,
        )
        return _structured_response(
            action_name=action_key,
            trust_level="session",
            allowed=False,
            reason="Your session has expired. Sign in again to continue.",
            required_action="session_expired",
            status="session_expired",
            approval_type="none",
            extra={"audit": event},
        )

    if active_session:
        username = username or active_session.get("username")
        user_id = user_id or active_session.get("user_id")

    # --- TRUST DECISION (confirm / session / PIN) -----------------------
    pin_verified = (
        bool(verify_pin(pin, username=username, session_id=session_id).get("success"))
        if pin
        else False
    )
    session_approved = is_action_approved(session_id, action_key)
    decision = evaluate_action(
        action_key,
        confirmed=confirmed,
        session_approved=session_approved,
        pin_verified=pin_verified,
        trust_level_override=trust_level_override,
    )

    auth_state = {"authenticated": bool(active_session), "session": active_session}
    if require_auth and decision.approval_type != ApprovalType.NONE and not auth_state.get("authenticated"):
        event = record_audit_event(
            action_name=action_key,
            allowed=False,
            trust_level=decision.trust_level.value,
            reason="authentication_required",
            username=username,
            session_id=session_id,
        )
        log_action(
            action_name=action_key,
            session_id=session_id,
            result="auth_required",
            trust_level=decision.trust_level.value,
            username=username,
            reason="authentication_required",
            meta=meta,
        )
        return _structured_response(
            action_name=action_key,
            trust_level=decision.trust_level.value,
            allowed=False,
            reason="Authentication required for this action.",
            required_action="auth_required",
            status="auth_required",
            approval_type=decision.approval_type.value,
            extra={"audit": event},
        )

    # --- CRITICAL ACTION FRESH-AUTH GATE --------------------------------
    # Even if the idle timer says the session is alive, critical actions
    # must have had activity within the last few minutes. If the session
    # has been dormant we force the user to re-authenticate.
    if (
        decision.trust_level == TrustLevel.CRITICAL
        and active_session
        and session_token
    ):
        recent = require_recent_auth(session_token, max_age_seconds=CRITICAL_REAUTH_WINDOW_SECONDS)
        if not recent.get("valid"):
            event = record_audit_event(
                action_name=action_key,
                allowed=False,
                trust_level="critical",
                reason="reauth_required",
                username=username,
                session_id=session_id,
            )
            log_action(
                action_name=action_key,
                session_id=session_id,
                result="reauth_required",
                trust_level="critical",
                username=username,
                reason="reauth_required",
                meta={**meta, "session_age_seconds": recent.get("age_seconds")},
            )
            return _structured_response(
                action_name=action_key,
                trust_level="critical",
                allowed=False,
                reason="This action requires a recently active session. Sign in again to continue.",
                required_action="auth_required",
                status="reauth_required",
                approval_type=decision.approval_type.value,
                extra={"audit": event, "session_age_seconds": recent.get("age_seconds")},
            )

    # --- OTP GATE -------------------------------------------------------
    needs_otp = _needs_otp(action_key, decision.trust_level)
    otp_ok = False
    if needs_otp and otp:
        otp_result = verify_otp(
            str(user_id or username or "anonymous"),
            action_key,
            otp,
            token=otp_token,
            session_id=session_id,
        )
        otp_ok = bool(otp_result.get("success"))
        if not otp_ok:
            event = record_audit_event(
                action_name=action_key,
                allowed=False,
                trust_level="critical",
                reason=f"otp_{otp_result.get('status', 'failed')}",
                username=username,
                session_id=session_id,
            )
            log_action(
                action_name=action_key,
                session_id=session_id,
                result="otp_failed",
                trust_level="critical",
                username=username,
                reason=str(otp_result.get("reason") or "OTP verification failed."),
                meta=meta,
            )
            return _structured_response(
                action_name=action_key,
                trust_level="critical",
                allowed=False,
                reason=str(otp_result.get("reason") or "OTP verification failed."),
                required_action="otp",
                status="otp_required",
                approval_type="otp",
                extra={"otp": otp_result, "audit": event},
            )

    if needs_otp and not otp and not otp_ok:
        event = record_audit_event(
            action_name=action_key,
            allowed=False,
            trust_level="critical",
            reason="otp_required",
            username=username,
            session_id=session_id,
        )
        log_action(
            action_name=action_key,
            session_id=session_id,
            result="otp_required",
            trust_level="critical",
            username=username,
            reason="otp_required",
            meta=meta,
        )
        return _structured_response(
            action_name=action_key,
            trust_level="critical",
            allowed=False,
            reason="This action requires an OTP sent to your registered phone.",
            required_action="otp",
            status="otp_required",
            approval_type="otp",
            extra={"audit": event},
        )

    # --- PIN DOUBLE-CHECK (defence-in-depth) ----------------------------
    # Some criticals require BOTH OTP and PIN. If the policy says
    # requires_pin and we haven't seen a verified PIN, block even when OTP
    # succeeded.
    if policy.requires_pin and not pin_verified and decision.trust_level == TrustLevel.CRITICAL:
        event = record_audit_event(
            action_name=action_key,
            allowed=False,
            trust_level="critical",
            reason="pin_required",
            username=username,
            session_id=session_id,
        )
        log_action(
            action_name=action_key,
            session_id=session_id,
            result="pin_required",
            trust_level="critical",
            username=username,
            reason="pin_required",
            meta=meta,
        )
        return _structured_response(
            action_name=action_key,
            trust_level="critical",
            allowed=False,
            reason="This action requires your PIN in addition to OTP.",
            required_action="pin",
            status="pin_required",
            approval_type="pin",
            extra={"audit": event, "otp_verified": bool(otp_ok)},
        )

    # --- FINAL DECISION -------------------------------------------------
    final_allowed = decision.allowed or (needs_otp and otp_ok)
    status = "approved" if final_allowed else decision.approval_type.value
    reason = decision.reason
    if needs_otp and otp_ok:
        reason = "Critical action approved by OTP."
        try:
            mark_otp_verified(session_id, action_key)
        except Exception:
            pass

    required_action = (
        "allow" if final_allowed else
        "otp" if needs_otp else
        ("pin" if policy.requires_pin else
         ("session_approval" if decision.approval_type == ApprovalType.SESSION_APPROVAL else
          ("confirm" if decision.approval_type == ApprovalType.CONFIRM else "allow")))
    )

    event = record_audit_event(
        action_name=action_key,
        allowed=final_allowed,
        trust_level=decision.trust_level.value,
        reason=decision.reason_code if not (needs_otp and otp_ok) else "OTP_OK",
        username=username,
        session_id=session_id,
    )
    log_action(
        action_name=action_key,
        session_id=session_id,
        result="allowed" if final_allowed else "blocked",
        trust_level=decision.trust_level.value,
        username=username,
        reason=reason,
        meta=meta,
    )

    approval_type = decision.approval_type.value if not (needs_otp and otp_ok) else "otp"
    return _structured_response(
        action_name=action_key,
        trust_level=decision.trust_level.value,
        allowed=final_allowed,
        reason=reason,
        required_action=required_action,
        status=status,
        approval_type=approval_type,
        extra={
            "session_approved": session_approved,
            "pin_verified": pin_verified,
            "otp_verified": bool(needs_otp and otp_ok),
            "policy": policy.to_dict(),
            "audit": event,
            "decision": decision.to_dict(),
        },
    )


def record_execution_result(
    action_name: str,
    *,
    session_id: str = "default",
    username: Optional[str] = None,
    success: bool,
    reason: Optional[str] = None,
    trust_level: Optional[str] = None,
    meta: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Called after an allowed action finishes so the audit trail has the full
    lifecycle: request -> allow -> execute -> success/fail."""

    return log_action(
        action_name=action_name,
        session_id=session_id,
        result="success" if success else "failure",
        trust_level=trust_level,
        username=username,
        reason=reason,
        meta=meta or {},
    )
