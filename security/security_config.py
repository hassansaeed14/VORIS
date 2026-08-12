from __future__ import annotations

from datetime import timedelta
from pathlib import Path


SECURITY_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SECURITY_DIR.parent
MEMORY_DIR = PROJECT_ROOT / "memory"

WHITELIST_FILE = SECURITY_DIR / "whitelist.json"
RATE_LIMITS_FILE = SECURITY_DIR / "rate_limits.json"
SESSIONS_FILE = SECURITY_DIR / "sessions.json"
CONFIRMATION_CODES_FILE = SECURITY_DIR / "confirmation_codes.json"
SECURITY_KEY_FILE = SECURITY_DIR / ".secret.key"
USERS_FILE = MEMORY_DIR / "users.json"
PIN_STATE_FILE = MEMORY_DIR / "pin_state.json"
LOCKS_FILE = MEMORY_DIR / "locks.json"
AUDIT_LOG_FILE = MEMORY_DIR / "security_audit.jsonl"
ACTION_APPROVAL_FILE = MEMORY_DIR / "session_approvals.json"
OTP_VERIFIED_FILE = MEMORY_DIR / "otp_verified.json"

AUTH_COOKIE_NAME = "voris_session"
# Cookies issued before the AURA -> VORIS rename. Read-only: still accepted so
# existing logins survive the upgrade, but never issued again.
LEGACY_AUTH_COOKIE_NAMES = ("aura_session",)
LOCAL_SESSION_COOKIE_NAME = "voris_local_session"
LEGACY_LOCAL_SESSION_COOKIE_NAMES = ("aura_local_session",)
AUTH_COOKIE_MAX_AGE_SECONDS = 60 * 60 * 24
AUTH_COOKIE_SAMESITE = "lax"

PIN_RETRY_LIMIT = 5
PIN_LOCKOUT_MINUTES = 15
SESSION_APPROVAL_MINUTES = 30
LOCK_DEFAULT_MINUTES = 30

LOGIN_ATTEMPT_LIMIT = 5
LOGIN_WINDOW_MINUTES = 15
LOGIN_BLOCK_MINUTES = 60

PIN_LOCKOUT_DELTA = timedelta(minutes=PIN_LOCKOUT_MINUTES)
SESSION_APPROVAL_DELTA = timedelta(minutes=SESSION_APPROVAL_MINUTES)
LOCK_DEFAULT_DELTA = timedelta(minutes=LOCK_DEFAULT_MINUTES)
AUTH_SESSION_IDLE_DELTA = timedelta(seconds=AUTH_COOKIE_MAX_AGE_SECONDS)
LOGIN_WINDOW_DELTA = timedelta(minutes=LOGIN_WINDOW_MINUTES)
LOGIN_BLOCK_DELTA = timedelta(minutes=LOGIN_BLOCK_MINUTES)
