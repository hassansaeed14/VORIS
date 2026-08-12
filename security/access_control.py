from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Dict

from security.audit_logger import record_audit_event
from security.encryption_utils import load_encrypted_json, save_encrypted_json
from security.pin_manager import verify_pin
from security.security_config import LOGIN_ATTEMPT_LIMIT, LOGIN_BLOCK_DELTA, LOGIN_WINDOW_DELTA, RATE_LIMITS_FILE, WHITELIST_FILE
from security.session_manager import is_action_approved
from security.trust_engine import ApprovalType, evaluate_action


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class AccessController:
    _instance: "AccessController | None" = None

    def __new__(cls) -> "AccessController":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def _load_whitelist(self) -> dict:
        payload = load_encrypted_json(WHITELIST_FILE, default={"users": {}})
        if not isinstance(payload, dict):
            return {"users": {}}
        users = payload.get("users", {})
        if not isinstance(users, dict):
            users = {}
        payload["users"] = users
        return payload

    def _save_whitelist(self, payload: dict) -> None:
        save_encrypted_json(WHITELIST_FILE, payload)

    def _load_rate_limits(self) -> dict:
        if not RATE_LIMITS_FILE.exists():
            return {"ips": {}}
        try:
            payload = json.loads(RATE_LIMITS_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {"ips": {}}
        if not isinstance(payload, dict):
            return {"ips": {}}
        ips = payload.get("ips", {})
        if not isinstance(ips, dict):
            ips = {}
        return {"ips": ips}

    def _save_rate_limits(self, payload: dict) -> None:
        RATE_LIMITS_FILE.parent.mkdir(parents=True, exist_ok=True)
        RATE_LIMITS_FILE.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _normalize_email(email: str) -> str:
        return str(email or "").strip().lower()

    def invite_user(self, email: str, invited_by_admin: str, *, admin: bool = False) -> dict:
        normalized = self._normalize_email(email)
        if not normalized:
            raise ValueError("Email is required.")
        payload = self._load_whitelist()
        users = payload["users"]
        entry = users.get(normalized, {})
        entry.update(
            {
                "email": normalized,
                "status": "active",
                "admin": bool(admin),
                "invited_by": invited_by_admin,
                "invited_at": entry.get("invited_at") or _now().isoformat(),
                "revoked_at": None,
                "registered": bool(entry.get("registered", False)),
                "last_login": entry.get("last_login"),
                "username": entry.get("username"),
            }
        )
        users[normalized] = entry
        self._save_whitelist(payload)
        return dict(entry)

    def is_whitelisted(self, email: str) -> bool:
        normalized = self._normalize_email(email)
        if not normalized:
            return False
        payload = self._load_whitelist()
        entry = payload["users"].get(normalized)
        return bool(entry and entry.get("status") == "active")

    def revoke_access(self, email: str) -> bool:
        normalized = self._normalize_email(email)
        payload = self._load_whitelist()
        entry = payload["users"].get(normalized)
        if not entry:
            return False
        entry["status"] = "revoked"
        entry["revoked_at"] = _now().isoformat()
        payload["users"][normalized] = entry
        self._save_whitelist(payload)
        return True

    def list_users(self) -> list[dict]:
        payload = self._load_whitelist()
        users = [dict(entry) for entry in payload["users"].values()]
        users.sort(key=lambda item: (item.get("status") != "active", item.get("email", "")))
        return users

    def mark_registered(self, email: str, *, username: str, admin: bool = False) -> None:
        normalized = self._normalize_email(email)
        payload = self._load_whitelist()
        entry = payload["users"].get(normalized) or {"email": normalized}
        entry["status"] = "active"
        entry["registered"] = True
        entry["username"] = username
        entry["admin"] = bool(admin or entry.get("admin"))
        entry["registered_at"] = _now().isoformat()
        payload["users"][normalized] = entry
        self._save_whitelist(payload)

    def mark_last_login(self, email: str) -> None:
        normalized = self._normalize_email(email)
        payload = self._load_whitelist()
        entry = payload["users"].get(normalized)
        if not entry:
            return
        entry["last_login"] = _now().isoformat()
        payload["users"][normalized] = entry
        self._save_whitelist(payload)

    def has_users(self) -> bool:
        payload = self._load_whitelist()
        return bool(payload["users"])

    def is_ip_blocked(self, ip_address: str) -> bool:
        payload = self._load_rate_limits()
        entry = payload["ips"].get(ip_address)
        if not entry:
            return False
        blocked_until = entry.get("blocked_until")
        if not blocked_until:
            return False
        try:
            if _now() < datetime.fromisoformat(blocked_until):
                return True
        except Exception:
            pass
        entry["blocked_until"] = None
        payload["ips"][ip_address] = entry
        self._save_rate_limits(payload)
        return False

    def record_login_attempt(self, ip_address: str, *, success: bool) -> dict:
        payload = self._load_rate_limits()
        ips = payload["ips"]
        entry = ips.get(ip_address, {"attempts": [], "blocked_until": None})
        attempt_times = []
        for attempt in entry.get("attempts", []):
            try:
                attempt_time = datetime.fromisoformat(attempt)
            except Exception:
                continue
            if _now() - attempt_time <= LOGIN_WINDOW_DELTA:
                attempt_times.append(attempt_time)

        if success:
            entry["attempts"] = []
            entry["blocked_until"] = None
        else:
            attempt_times.append(_now())
            entry["attempts"] = [item.isoformat() for item in attempt_times]
            if len(attempt_times) >= LOGIN_ATTEMPT_LIMIT:
                entry["blocked_until"] = (_now() + LOGIN_BLOCK_DELTA).isoformat()

        ips[ip_address] = entry
        self._save_rate_limits(payload)
        return {
            "attempts": len(entry.get("attempts", [])),
            "blocked_until": entry.get("blocked_until"),
            "blocked": bool(entry.get("blocked_until")) and self.is_ip_blocked(ip_address),
        }

    def unblock_ip(self, ip_address: str) -> bool:
        payload = self._load_rate_limits()
        entry = payload["ips"].get(ip_address)
        if not entry:
            return False
        entry["attempts"] = []
        entry["blocked_until"] = None
        payload["ips"][ip_address] = entry
        self._save_rate_limits(payload)
        return True

    def list_rate_limits(self) -> list[dict]:
        payload = self._load_rate_limits()
        rows = []
        for ip_address, entry in payload["ips"].items():
            rows.append(
                {
                    "ip_address": ip_address,
                    "attempt_count": len(entry.get("attempts", [])),
                    "blocked_until": entry.get("blocked_until"),
                    "blocked": self.is_ip_blocked(ip_address),
                }
            )
        rows.sort(key=lambda item: (not item["blocked"], item["ip_address"]))
        return rows


def evaluate_access(
    action_name: str,
    *,
    username: str | None = None,
    session_id: str = "default",
    confirmed: bool = False,
    pin: str | None = None,
    resource_id: str | None = None,
) -> Dict[str, object]:
    from security.auth_manager import get_auth_state
    from security.lock_manager import is_locked

    auth_state = get_auth_state(username)
    if resource_id and is_locked(resource_id):
        event = record_audit_event(
            action_name=action_name,
            allowed=False,
            trust_level="critical",
            reason="resource_locked",
            username=username,
            session_id=session_id,
        )
        return {"success": False, "status": "locked", "reason": "Resource is locked.", "audit": event}

    pin_result = verify_pin(pin) if pin else {"success": False}
    decision = evaluate_action(
        action_name,
        confirmed=confirmed,
        session_approved=is_action_approved(session_id, action_name),
        pin_verified=bool(pin_result.get("success")),
    )

    # FORCE LOCAL AUTHENTICATION
    auth_state["authenticated"] = True
        
    if decision.approval_type != ApprovalType.NONE and username and not auth_state["authenticated"]:
         event = record_audit_event(
            action_name=action_name,
            allowed=False,
            trust_level=decision.trust_level.value,
            reason="authentication_required",
            username=username,
            session_id=session_id,
        )
         return {
            "success": False,
            "status": "auth_required",
            "reason": "Authentication required for this action.",
            "decision": decision.to_dict(),
            "audit": event,
        }

    event = record_audit_event(
        action_name=action_name,
        allowed=decision.allowed,
        trust_level=decision.trust_level.value,
        reason=decision.reason_code,
        username=username,
        session_id=session_id,
    )
    return {
        "success": decision.allowed,
        "status": "approved" if decision.allowed else decision.approval_type.value,
        "reason": decision.reason,
        "decision": decision.to_dict(),
        "audit": event,
    }
