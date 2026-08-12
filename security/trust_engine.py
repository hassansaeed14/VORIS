# security/trust_engine.py

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, Optional

from config.permissions import (
    ACTION_PERMISSIONS as _CONFIG_ACTION_PERMISSIONS,
    DEFAULT_TRUST_LEVEL as _CONFIG_DEFAULT_TRUST_LEVEL,
    OTP_REQUIRED_ACTIONS as _CONFIG_OTP_REQUIRED_ACTIONS,
    PIN_REQUIRED_ACTIONS as _CONFIG_PIN_REQUIRED_ACTIONS,
    get_action_policy as _config_get_action_policy,
    normalize_action as _config_normalize_action,
    requires_otp as _config_requires_otp,
    requires_pin as _config_requires_pin,
)


class TrustLevel(str, Enum):
    SAFE = "safe"
    PRIVATE = "private"
    SENSITIVE = "sensitive"
    CRITICAL = "critical"


class ApprovalType(str, Enum):
    NONE = "none"
    CONFIRM = "confirm"
    SESSION_APPROVAL = "session_approval"
    PIN = "pin"


@dataclass(frozen=True)
class TrustDecision:
    action_name: str
    trust_level: TrustLevel
    approval_type: ApprovalType
    allowed: bool
    reason: str
    reason_code: str
    policy_source: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "action_name": self.action_name,
            "trust_level": self.trust_level.value,
            "approval_type": self.approval_type.value,
            "allowed": self.allowed,
            "reason": self.reason,
            "reason_code": self.reason_code,
            "policy_source": self.policy_source,
            "requires_approval": self.approval_type != ApprovalType.NONE,
            "requires_pin": self.approval_type == ApprovalType.PIN,
        }


# Single source of truth lives in ``config.permissions``. We mirror it here
# as ``TrustLevel`` enum values so downstream code that compares against
# ``TrustLevel.SAFE`` etc. keeps working unchanged.
ACTION_TRUST_MAP: Dict[str, TrustLevel] = {
    action: TrustLevel(level)
    for action, level in _CONFIG_ACTION_PERMISSIONS.items()
}

_DEFAULT_TRUST_LEVEL = TrustLevel(_CONFIG_DEFAULT_TRUST_LEVEL)


LEVEL_TO_APPROVAL: Dict[TrustLevel, ApprovalType] = {
    TrustLevel.SAFE: ApprovalType.NONE,
    TrustLevel.PRIVATE: ApprovalType.CONFIRM,
    TrustLevel.SENSITIVE: ApprovalType.SESSION_APPROVAL,
    TrustLevel.CRITICAL: ApprovalType.PIN,
}


def normalize_action_name(action_name: Optional[str]) -> str:
    return _config_normalize_action(action_name)


def get_trust_level(action_name: Optional[str]) -> TrustLevel:
    normalized = normalize_action_name(action_name)
    return ACTION_TRUST_MAP.get(normalized, _DEFAULT_TRUST_LEVEL)


def coerce_trust_level(value: Optional[str]) -> Optional[TrustLevel]:
    if value is None:
        return None
    normalized = str(value or "").strip().lower()
    if not normalized:
        return None
    try:
        return TrustLevel(normalized)
    except ValueError:
        return None


def get_approval_type(trust_level: TrustLevel) -> ApprovalType:
    return LEVEL_TO_APPROVAL[trust_level]


def get_policy_source(action_name: Optional[str]) -> str:
    normalized = normalize_action_name(action_name)
    if normalized in ACTION_TRUST_MAP:
        return "action_trust_map"
    return "default_sensitive_fallback"


def action_requires_otp(action_name: Optional[str]) -> bool:
    """True if the action's policy says an OTP must be provided."""

    return bool(_config_requires_otp(action_name))


def action_requires_pin(action_name: Optional[str]) -> bool:
    """True if the action's policy says a PIN must be re-entered."""

    return bool(_config_requires_pin(action_name))


def get_action_policy(action_name: Optional[str]) -> Dict[str, Any]:
    """Return the full structured policy for ``action_name``."""

    return _config_get_action_policy(action_name).to_dict()


def evaluate_action(
    action_name: Optional[str],
    *,
    confirmed: bool = False,
    session_approved: bool = False,
    pin_verified: bool = False,
    trust_level_override: Optional[str] = None,
) -> TrustDecision:
    normalized = normalize_action_name(action_name)
    override_level = coerce_trust_level(trust_level_override)
    trust_level = override_level or get_trust_level(normalized)
    approval_type = get_approval_type(trust_level)
    policy_source = "trust_level_override" if override_level else get_policy_source(normalized)

    if trust_level == TrustLevel.SAFE:
        return TrustDecision(
            action_name=normalized,
            trust_level=trust_level,
            approval_type=approval_type,
            allowed=True,
            reason="Safe action. No approval required.",
            reason_code="SAFE_ACTION",
            policy_source=policy_source,
        )

    if trust_level == TrustLevel.PRIVATE:
        if confirmed:
            return TrustDecision(
                action_name=normalized,
                trust_level=trust_level,
                approval_type=approval_type,
                allowed=True,
                reason="Private action approved.",
                reason_code="PRIVATE_CONFIRMED",
                policy_source=policy_source,
            )
        return TrustDecision(
            action_name=normalized,
            trust_level=trust_level,
            approval_type=approval_type,
            allowed=False,
            reason="Private action requires confirmation.",
            reason_code="CONFIRM_REQUIRED",
            policy_source=policy_source,
        )

    if trust_level == TrustLevel.SENSITIVE:
        if session_approved:
            return TrustDecision(
                action_name=normalized,
                trust_level=trust_level,
                approval_type=approval_type,
                allowed=True,
                reason="Sensitive action approved.",
                reason_code="SESSION_APPROVED",
                policy_source=policy_source,
            )
        return TrustDecision(
            action_name=normalized,
            trust_level=trust_level,
            approval_type=approval_type,
            allowed=False,
            reason="Sensitive action requires session approval.",
            reason_code="SESSION_REQUIRED",
            policy_source=policy_source,
        )

    if pin_verified:
        return TrustDecision(
            action_name=normalized,
            trust_level=trust_level,
            approval_type=approval_type,
            allowed=True,
            reason="Critical action approved by PIN.",
            reason_code="PIN_OK",
            policy_source=policy_source,
        )

    return TrustDecision(
        action_name=normalized,
        trust_level=trust_level,
        approval_type=approval_type,
        allowed=False,
        reason="Critical action requires PIN.",
        reason_code="PIN_REQUIRED",
        policy_source=policy_source,
    )


def build_permission_response(
    action_name: Optional[str],
    *,
    confirmed: bool = False,
    session_approved: bool = False,
    pin_verified: bool = False,
    trust_level_override: Optional[str] = None,
    trace_id: Optional[str] = None,
) -> Dict[str, Any]:
    decision = evaluate_action(
        action_name,
        confirmed=confirmed,
        session_approved=session_approved,
        pin_verified=pin_verified,
        trust_level_override=trust_level_override,
    )

    if decision.allowed:
        return {
            "success": True,
            "status": "approved",
            "mode": "real",
            "trace_id": trace_id,
            "permission": decision.to_dict(),
        }

    status_map = {
        ApprovalType.CONFIRM: "needs_confirmation",
        ApprovalType.SESSION_APPROVAL: "needs_session_approval",
        ApprovalType.PIN: "needs_pin",
        ApprovalType.NONE: "approved",
    }

    return {
        "success": False,
        "status": status_map[decision.approval_type],
        "mode": "real",
        "trace_id": trace_id,
        "permission": decision.to_dict(),
    }
