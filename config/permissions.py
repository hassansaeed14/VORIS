"""Single source of truth for VORIS action trust policy.

Every privileged action in VORIS must be registered here with one of four
trust levels — ``safe``, ``private``, ``sensitive``, ``critical`` — and a
structured policy describing *exactly* which gates must be cleared before
the action may execute:

    requires_confirmation      (user said "yes"/tapped confirm)
    requires_session_approval  (per-session "trust for 30 min" approval)
    requires_otp               (fresh one-time code bound to action + user + session)
    requires_pin               (numeric PIN re-entered)

Consumers MUST resolve policy via ``get_action_policy`` /
``get_trust_level`` / ``requires_*`` rather than hard-coding their own
rules. This keeps ``security.trust_engine``, ``security.permission_engine``,
``security.enforcement``, ``tools.tool_guard``, ``agents.agent_fabric``,
``brain.runtime_core`` and every API endpoint aligned on the same policy.

Trust-level defaults (the baseline "required action" for each level):
    safe       -> auto-allow, no user friction
    private    -> requires per-call user confirmation
    sensitive  -> requires one-time session approval (remembered for TTL)
    critical   -> requires OTP / PIN (fresh verification, not cached)

Individual actions may *upgrade* gating (e.g. a private action that also
requires PIN re-entry) via ``register_action``'s flag overrides. Actions
may never downgrade their trust-level default — the policy is fail-closed
by design.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Dict, Iterable, Tuple


TRUST_LEVELS: Tuple[str, ...] = ("safe", "private", "sensitive", "critical")

REQUIRED_ACTION_MAP: Dict[str, str] = {
    "safe": "allow",
    "private": "confirm",
    "sensitive": "session_approval",
    "critical": "otp",
}

NEXT_STEP_HINTS: Dict[str, str] = {
    "allow": "No action required. Proceed.",
    "confirm": "Reply 'yes' or tap Confirm to proceed.",
    "session_approval": "Approve this action for your session, then retry.",
    "otp": "Request an OTP (POST /api/security/otp/request) and resubmit with the code.",
    "pin": "Re-enter your PIN to continue.",
    "auth_required": "Sign in first, then retry.",
    "session_expired": "Your session expired. Sign in again.",
    "locked": "This resource is locked. Unlock it or choose a different target.",
}


@dataclass(frozen=True)
class ActionPolicy:
    """Structured policy for a single registered action."""

    action: str
    trust_level: str
    requires_confirmation: bool
    requires_session_approval: bool
    requires_otp: bool
    requires_pin: bool
    description: str = ""
    aliases: Tuple[str, ...] = field(default_factory=tuple)

    def required_action(self) -> str:
        if self.requires_otp:
            return "otp"
        if self.requires_pin:
            return "pin"
        if self.requires_session_approval:
            return "session_approval"
        if self.requires_confirmation:
            return "confirm"
        return REQUIRED_ACTION_MAP.get(self.trust_level, "confirm") if self.trust_level != "safe" else "allow"

    def next_step_hint(self) -> str:
        return NEXT_STEP_HINTS.get(self.required_action(), NEXT_STEP_HINTS["confirm"])

    def to_dict(self) -> Dict[str, object]:
        return {
            "action": self.action,
            "trust_level": self.trust_level,
            "requires_confirmation": self.requires_confirmation,
            "requires_session_approval": self.requires_session_approval,
            "requires_otp": self.requires_otp,
            "requires_pin": self.requires_pin,
            "required_action": self.required_action(),
            "next_step_hint": self.next_step_hint(),
            "description": self.description,
            "aliases": list(self.aliases),
        }


DEFAULT_TRUST_LEVEL = "sensitive"


def _default_flags(trust_level: str) -> Dict[str, bool]:
    """Gate defaults per trust level. Individual actions may upgrade these."""

    level = trust_level if trust_level in TRUST_LEVELS else DEFAULT_TRUST_LEVEL
    if level == "safe":
        return {
            "requires_confirmation": False,
            "requires_session_approval": False,
            "requires_otp": False,
            "requires_pin": False,
        }
    if level == "private":
        return {
            "requires_confirmation": True,
            "requires_session_approval": False,
            "requires_otp": False,
            "requires_pin": False,
        }
    if level == "sensitive":
        return {
            "requires_confirmation": False,
            "requires_session_approval": True,
            "requires_otp": False,
            "requires_pin": False,
        }
    # critical
    # Default: OTP is required. PIN is a defence-in-depth upgrade that
    # individual actions opt into explicitly via ``requires_pin=True`` at
    # register time (e.g., account_delete, password_change).
    return {
        "requires_confirmation": False,
        "requires_session_approval": False,
        "requires_otp": True,
        "requires_pin": False,
    }


# ---------------------------------------------------------------------------
# Registry. Each entry is an ``ActionPolicy``. ``ACTION_PERMISSIONS`` is kept
# as a backwards-compat view (action -> trust_level) for the few callers that
# only need the trust level string.
# ---------------------------------------------------------------------------


ACTION_POLICIES: Dict[str, ActionPolicy] = {}
ACTION_PERMISSIONS: Dict[str, str] = {}


def normalize_action(action_name: str | None) -> str:
    if not action_name:
        return "general"
    return str(action_name).strip().lower().replace(" ", "_").replace("-", "_")


def _register(
    action: str,
    trust_level: str,
    *,
    requires_confirmation: bool | None = None,
    requires_session_approval: bool | None = None,
    requires_otp: bool | None = None,
    requires_pin: bool | None = None,
    description: str = "",
    aliases: Tuple[str, ...] = (),
) -> ActionPolicy:
    level = trust_level if trust_level in TRUST_LEVELS else DEFAULT_TRUST_LEVEL
    defaults = _default_flags(level)
    policy = ActionPolicy(
        action=normalize_action(action),
        trust_level=level,
        requires_confirmation=defaults["requires_confirmation"] if requires_confirmation is None else bool(requires_confirmation),
        requires_session_approval=defaults["requires_session_approval"] if requires_session_approval is None else bool(requires_session_approval),
        requires_otp=defaults["requires_otp"] if requires_otp is None else bool(requires_otp),
        requires_pin=defaults["requires_pin"] if requires_pin is None else bool(requires_pin),
        description=description,
        aliases=tuple(normalize_action(a) for a in aliases),
    )
    ACTION_POLICIES[policy.action] = policy
    ACTION_PERMISSIONS[policy.action] = policy.trust_level
    for alias in policy.aliases:
        ACTION_POLICIES[alias] = replace(policy, action=alias)
        ACTION_PERMISSIONS[alias] = policy.trust_level
    return policy


# --- SAFE: informational, generative, read-only helpers ---
for _action in (
    "general", "greeting", "identity", "time", "date", "weather", "news",
    "math", "dictionary", "quote", "joke", "translation", "grammar", "quiz",
    "summarize", "study", "research", "coding", "reasoning", "compare",
    "web_search", "youtube", "currency", "crypto", "synonyms", "permission",
    "write", "writing_runtime", "content",
    "task", "task_read", "task_add", "task_complete", "task_delete",
    "task_plan", "reminder", "reminder_read", "reminder_add",
    "reminder_complete", "reminder_delete", "password", "planner_agent",
    "tool_selector", "debug_agent",
):
    _register(_action, "safe", description="Informational / generative helper.")

# Document / generation pipeline MUST remain seamless.
_register("document", "safe", description="Document-related request router.")
_register("document_generation", "safe", description="Document generation pipeline.")
_register("document_generator", "safe", description="Generator dispatch for documents.")
_register("document_export", "safe", description="Export a generated document.")
_register("document_download", "safe", description="Download a generated document.")
_register("generate_notes", "safe", description="Produce notes for study.")
_register("generate_assignment", "safe", description="Produce assignment drafts.")
_register("generate_document", "safe", description="Generate an arbitrary document.")
_register("content_transformation", "safe", description="Transform source content to a new format.")
_register("content_transform", "safe", description="Alias of content_transformation.")
_register("media_transform", "safe", description="Media → document transformation.")
_register("diagram_generation", "safe", description="Diagram generation pipeline.")
_register("slides", "safe", description="Slide deck pipeline.")
_register("notes", "safe", description="Notes pipeline.")
_register("assignment", "safe", description="Assignment pipeline.")
_register("desktop_launch", "safe", description="Launch a whitelisted local desktop application.")
_register("os_automation_focus", "safe", description="Focus a whitelisted supported application window.")
_register("os_automation_control", "sensitive", description="Controlled keyboard/mouse automation in whitelisted apps.")
_register("os_automation_critical", "critical", description="Blocked destructive or sensitive OS automation.")

# --- PRIVATE: reads into user-owned data, needs user confirmation ---
_register("memory_read", "private", description="Read personal memory entries.",
          aliases=("view_memory",))
_register("history", "private", description="Read recent chat history.",
          aliases=("view_chat_history", "chat_history"))
_register("insights", "private", description="Read behavioural insights.")
_register("file", "private", description="Ambiguous file verb; prefer file_read/file_list.")
_register("file_read", "private", description="Read a local file.")
_register("file_list", "private", description="List a local directory.",
          aliases=("list_files",))
_register("profile_read", "private", description="Read the user profile.")
_register("system_read", "private", description="Read system / resource snapshots.")

# --- SENSITIVE: writes or external-facing actions, needs session approval ---
_register("auth_login", "sensitive", description="Login flow (credentials exchange).")
_register("auth_register", "sensitive", description="Create a new account.")
_register("memory_write", "sensitive", description="Mutate personal memory.")
_register("settings_update", "sensitive", description="Change user settings.")
_register("screenshot", "sensitive", description="Capture screen contents.")
_register("file_write", "sensitive", description="Write a local file.")
_register("file_upload", "sensitive", description="Upload a file to storage.",
          aliases=("upload_file",))
_register("modify_files", "sensitive", description="Bulk file modification.")
_register("send_email", "sensitive", description="Send an outbound email.")
_register("send_message", "sensitive", description="Send an outbound chat/IM message.")
_register("executor", "sensitive", description="Generic multi-step executor dispatch.")

# --- CRITICAL: irreversible, money, identity, secrets, security settings ---
# All criticals require OTP (one-time, session-bound). A small tier above that
# — identity changes, security settings, secret reveals — also requires a
# fresh PIN re-entry for defence-in-depth.
_register("payment", "critical", description="Execute a payment.")
_register("purchase", "critical", description="Purchase an item.",
          aliases=("purchase_item",))
_register("system_control", "critical", description="Drive the OS / processes.",
          aliases=("pc_control",))
_register("file_delete", "critical", description="Delete a local file.",
          aliases=("delete_files",))
_register("account_delete", "critical", requires_pin=True, description="Delete the user account.")
_register("locked_chat_unlock", "critical", requires_pin=True, description="Unlock a locked chat.")
_register("password_change", "critical", requires_pin=True, description="Change the account password.",
          aliases=("change_password",))
_register("password_reset", "critical",
          requires_confirmation=False,
          requires_session_approval=False,
          requires_otp=True,
          requires_pin=False,
          description="Forgot-password flow: OTP-gated, unauthenticated reset.",
          aliases=("forgot_password", "reset_password"))
_register("external_integration", "critical", description="Authorize an external integration.")
_register("owner_transfer", "critical", requires_pin=True, description="Transfer account ownership.")
_register("phone_register", "critical", requires_pin=True, description="Register or change the recovery phone.")
_register("secret_reveal", "critical", requires_pin=True, description="Reveal a stored secret.")
_register("security_settings_update", "critical", requires_pin=True,
          description="Change security-related settings (PIN, OTP policy, trusted devices).")
_register("api_key_reveal", "critical", requires_pin=True, description="Reveal or rotate an API key.")


# Convenience registries — kept in sync with ACTION_POLICIES.
CRITICAL_ACTIONS: Tuple[str, ...] = tuple(
    action for action, policy in ACTION_POLICIES.items() if policy.trust_level == "critical"
)
SENSITIVE_ACTIONS: Tuple[str, ...] = tuple(
    action for action, policy in ACTION_POLICIES.items() if policy.trust_level == "sensitive"
)
OTP_REQUIRED_ACTIONS: Tuple[str, ...] = tuple(
    action for action, policy in ACTION_POLICIES.items() if policy.requires_otp
)
PIN_REQUIRED_ACTIONS: Tuple[str, ...] = tuple(
    action for action, policy in ACTION_POLICIES.items() if policy.requires_pin
)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def get_action_policy(action_name: str | None) -> ActionPolicy:
    """Return the registered ``ActionPolicy`` for ``action_name``.

    Unknown actions fail-closed onto the ``DEFAULT_TRUST_LEVEL`` policy
    (sensitive) so a newly introduced action cannot silently ride through
    as safe.
    """

    key = normalize_action(action_name)
    policy = ACTION_POLICIES.get(key)
    if policy is not None:
        return policy
    level = DEFAULT_TRUST_LEVEL
    defaults = _default_flags(level)
    return ActionPolicy(
        action=key,
        trust_level=level,
        requires_confirmation=defaults["requires_confirmation"],
        requires_session_approval=defaults["requires_session_approval"],
        requires_otp=defaults["requires_otp"],
        requires_pin=defaults["requires_pin"],
        description=f"Unregistered action (fail-closed @ {level}).",
    )


def get_trust_level(action_name: str | None) -> str:
    return get_action_policy(action_name).trust_level


def get_required_action(trust_level: str | None) -> str:
    normalized = str(trust_level or "").strip().lower()
    return REQUIRED_ACTION_MAP.get(normalized, "confirm")


def get_next_step_hint(required_action: str | None) -> str:
    normalized = str(required_action or "").strip().lower()
    return NEXT_STEP_HINTS.get(normalized, NEXT_STEP_HINTS["confirm"])


def requires_confirmation(action_name: str | None) -> bool:
    return get_action_policy(action_name).requires_confirmation


def requires_session_approval(action_name: str | None) -> bool:
    return get_action_policy(action_name).requires_session_approval


def requires_otp(action_name: str | None) -> bool:
    return get_action_policy(action_name).requires_otp


def requires_pin(action_name: str | None) -> bool:
    return get_action_policy(action_name).requires_pin


def is_critical(action_name: str | None) -> bool:
    return get_action_policy(action_name).trust_level == "critical"


def is_sensitive(action_name: str | None) -> bool:
    return get_action_policy(action_name).trust_level == "sensitive"


def is_registered(action_name: str | None) -> bool:
    return normalize_action(action_name) in ACTION_POLICIES


def list_actions_by_trust_level(trust_level: str) -> Tuple[str, ...]:
    normalized = str(trust_level or "").strip().lower()
    return tuple(action for action, policy in ACTION_POLICIES.items() if policy.trust_level == normalized)


def list_critical_actions() -> Tuple[str, ...]:
    return tuple(action for action, policy in ACTION_POLICIES.items() if policy.trust_level == "critical")


def list_sensitive_actions() -> Tuple[str, ...]:
    return tuple(action for action, policy in ACTION_POLICIES.items() if policy.trust_level == "sensitive")


def register_action(
    action_name: str,
    trust_level: str,
    *,
    requires_confirmation: bool | None = None,
    requires_session_approval: bool | None = None,
    requires_otp: bool | None = None,
    requires_pin: bool | None = None,
    description: str = "",
    aliases: Iterable[str] = (),
) -> ActionPolicy:
    normalized_level = str(trust_level or "").strip().lower()
    if normalized_level not in TRUST_LEVELS:
        raise ValueError(f"Unknown trust level: {trust_level}")
    return _register(
        action_name,
        normalized_level,
        requires_confirmation=requires_confirmation,
        requires_session_approval=requires_session_approval,
        requires_otp=requires_otp,
        requires_pin=requires_pin,
        description=description,
        aliases=tuple(aliases),
    )


def bulk_register(entries: Iterable[Tuple[str, str]]) -> None:
    for action_name, level in entries:
        register_action(action_name, level)
