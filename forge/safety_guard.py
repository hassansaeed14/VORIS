from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Iterable, List


SAFE_FORGE_ACTIONS = {"audit", "report", "plan_repair", "record_patch"}


@dataclass(slots=True)
class SafetyDecision:
    action: str
    allowed: bool
    risk_level: str
    reason: str
    targets: List[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class SafetyGuard:
    """Prevent AURA Forge from drifting into unsafe self-modification."""

    def evaluate(self, action: str, targets: Iterable[str] | None = None) -> SafetyDecision:
        normalized_action = str(action or "").strip().lower() or "unknown"
        normalized_targets = [str(target).strip() for target in (targets or []) if str(target).strip()]

        if normalized_action in SAFE_FORGE_ACTIONS:
            return SafetyDecision(
                action=normalized_action,
                allowed=True,
                risk_level="low",
                reason="Read-only audit and planning actions are allowed.",
                targets=normalized_targets,
            )

        if normalized_action in {"apply_patch", "self_modify", "delete", "execute_shell"}:
            return SafetyDecision(
                action=normalized_action,
                allowed=False,
                risk_level="high",
                reason="AURA Forge does not self-modify or execute unsafe repair actions automatically.",
                targets=normalized_targets,
            )

        return SafetyDecision(
            action=normalized_action,
            allowed=False,
            risk_level="medium",
            reason="Unknown Forge action denied by default.",
            targets=normalized_targets,
        )
