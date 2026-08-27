import asyncio
import base64
import hashlib
import json
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from urllib.parse import quote
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional
from groq import Groq
from openai import OpenAI
from fastapi import FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from pydantic import BaseModel
import uvicorn
import os
import sys
print(f"--- VORIS is running on Python: {sys.version} ---")
print(f"--- Executable Path: {sys.executable} ---")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
LEGACY_WEB_DIR = PROJECT_ROOT / "interface" / "web"
WEB_V2_DIR = PROJECT_ROOT / "interface" / "web_v2"
MODERN_UI_DIR = PROJECT_ROOT / "static"
MODERN_UI_INDEX = MODERN_UI_DIR / "index.html"
APP_HTML = WEB_V2_DIR / "voris.html"
LOGIN_HTML = WEB_V2_DIR / "login.html"
REGISTER_HTML = WEB_V2_DIR / "register.html"
FORGOT_PASSWORD_HTML = WEB_V2_DIR / "forgot-password.html"
SETUP_HTML = LEGACY_WEB_DIR / "setup.html"
ADMIN_HTML = LEGACY_WEB_DIR / "admin.html"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agents.registry import get_agent_summary, list_agents
from agents.agent_fabric import list_generated_agent_cards, run_generated_agent
from brain.capability_registry import list_capabilities, summarize_capabilities
from brain.understanding_engine import clean_user_input
from brain.intent_engine import detect_intent_with_confidence
from brain.decision_engine import build_decision_summary
from brain.core_ai import AGENT_ROUTER, clear_session_context, process_command_detailed
from brain.telemetry_engine import get_last_telemetry
from brain.response_engine import (
    FALLBACK_USER_MESSAGE,
    build_degraded_reply,
    clean_response,
    generate_response_payload,
    shape_response_for_task,
)
from brain.system_trace import build_action_trace, new_request_id
from brain.provider_hub import (
    SUPPORTED_PROVIDERS,
    STATUS_AUTH_FAILED,
    STATUS_CONFIGURED_UNVERIFIED,
    STATUS_DEGRADED,
    STATUS_HEALTHY,
    STATUS_NOT_CONFIGURED,
    STATUS_RATE_LIMITED,
    STATUS_UNAVAILABLE,
    generate_with_best_provider,
    generate_with_provider,
    get_provider_state_version,
    get_provider_status as get_runtime_provider_status,
    get_runtime_provider_summary,
    extract_vision_payload,
    list_provider_statuses,
    summarize_provider_statuses,
)
from config.master_spec import CAPABILITY_LABELS, HYBRID_IMPLEMENTATION_ORDER
from config.system_modes import list_system_modes
from config.settings import DEFAULT_REASONING_PROVIDER, GROQ_API_KEY, GROQ_VISION_MODEL, MODEL_NAME
from forge.forge_engine import forge_engine
from memory import vector_memory
from memory.chat_history import DB_PATH as CHAT_HISTORY_DB_PATH, clear_history, get_all_sessions, get_history, save_message
from memory.memory_stats import get_memory_stats
from memory.personalization import get_personal_display_name
from security.access_control import AccessController
from security.auth_manager import (
    authenticate_user,
    clear_session_cookie,
    create_owner_account,
    get_auth_state,
    get_request_user,
    get_user as get_auth_user,
    is_admin_user,
    logout_request,
    read_session_token,
    register_user as register_auth_user,
    requires_first_run_setup,
    set_session_cookie,
)
from security.security_config import (
    LEGACY_LOCAL_SESSION_COOKIE_NAMES,
    LOCAL_SESSION_COOKIE_NAME,
)
from security.audit_logger import tail_audit_log
from security.confirmation_system import ConfirmationSystem
from security.enforcement import enforce_action, record_execution_result
from security.lock_manager import is_locked, lock_resource, unlock_resource
from security.otp_manager import get_otp_status, invalidate_otp, request_otp, verify_otp
from security.permission_engine import check_permission
from security.password_reset import (
    confirm_password_reset,
    request_password_reset,
    verify_password_reset,
)
from security.phone_registry import get_phone, list_phones, register_phone, remove_phone
from security.pin_manager import get_pin_status
from security.session_manager import (
    approve_action,
    describe_login_session,
    get_login_session,
    is_action_approved,
    list_login_sessions,
)
from security.status import security_status_summary
from security.trust_engine import build_permission_response
from api.auth import get_user
from voice.voice_controller import (
    get_voice_status,
    speak_response,
    stop_voice_output,
    transcribe_microphone_request,
    update_voice_preferences,
)
from voice.voice_config import list_voice_personas
from voice.assistant_runtime import get_assistant_runtime_status
from voice.desktop_voice_runtime import (
    interrupt_desktop_voice,
    start_desktop_voice,
    stop_desktop_voice,
)
from voice.voice_pipeline import process_voice_text
from voice.voice_manager import load_user_profile, save_user_profile
from tools.document_generator import (
    GENERATED_DIR,
    cleanup_generated_documents,
    detect_document_retrieval_followup,
    generate_document,
    resolve_generated_download_access,
    normalize_citation_style,
    normalize_document_format,
    normalize_document_formats,
    normalize_document_style,
    resolve_document_request,
    _is_unclear_document_request,
    secure_generated_document_access,
)
from tools.image_generation import (
    detect_image_generation_request,
    generate_image,
    get_image_generation_status,
)
from tools import media_generation
from tools.content_extractor import extract_content
from brain.response_engine import generate_transformation_content_payload
from tools.desktop_controller import get_supported_desktop_apps
from tools.os_automation import request_stop as request_os_automation_stop


app = FastAPI()
SERVER_STARTED_AT = time.time()
REQUEST_METRICS = {"total_requests": 0, "failed_requests": 0}
PROVIDER_HEALTH_CACHE: dict[str, Any] = {
    "checked_at_ts": 0.0,
    "checked_at": 0.0,
    "items": [],
    "providers": {},
    "assistant_runtime": {},
    "provider_state_version": -1,
}
PROVIDER_REFRESH_INTERVAL_SECONDS = 60
DOCUMENT_RATE_LIMIT_WINDOW_SECONDS = 300
DOCUMENT_RATE_LIMIT_MAX_REQUESTS = 6
DOCUMENT_RATE_LIMIT_STATE: dict[str, list[float]] = {}

app.mount("/static", StaticFiles(directory=str(LEGACY_WEB_DIR)), name="static")
app.mount("/static-v2", StaticFiles(directory=str(WEB_V2_DIR)), name="static-v2")
if MODERN_UI_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(MODERN_UI_DIR)), name="modern-ui-assets")
GENERATED_DIR.mkdir(parents=True, exist_ok=True)
GENERATED_IMAGE_DIR = PROJECT_ROOT / "generated" / "images"
GENERATED_IMAGE_DIR.mkdir(parents=True, exist_ok=True)


class Command(BaseModel):
    text: str
    username: str = "guest"


class ChatApiRequest(BaseModel):
    message: str
    mode: str = "hybrid"
    confirmation_code: Optional[str] = None
    confirmed: bool = False
    pin: Optional[str] = None
    otp: Optional[str] = None
    otp_token: Optional[str] = None


class LoginData(BaseModel):
    username: str
    password: str


class RegisterData(BaseModel):
    username: str
    password: str
    name: str
    email: str
    title: Optional[str] = "sir"
    preferred_name: Optional[str] = ""


class SetupData(BaseModel):
    username: str
    password: str
    name: str
    email: str
    master_pin: str
    title: Optional[str] = "sir"
    preferred_name: Optional[str] = ""


class TaskCreate(BaseModel):
    text: str
    priority: str = "medium"
    due_date: Optional[str] = None


class TaskUpdate(BaseModel):
    text: Optional[str] = None
    priority: Optional[str] = None
    due_date: Optional[str] = None
    done: Optional[bool] = None


class ReminderCreate(BaseModel):
    text: str
    date: Optional[str] = None
    time: Optional[str] = None


class ReminderUpdate(BaseModel):
    text: Optional[str] = None
    date: Optional[str] = None
    time: Optional[str] = None
    status: Optional[str] = None


class AgentRunRequest(BaseModel):
    text: str
    username: str = "guest"
    session_id: str = "default"
    confirmed: bool = False
    pin: Optional[str] = None
    otp: Optional[str] = None
    otp_token: Optional[str] = None
    save_artifact: Optional[bool] = None


class VoiceTextRequest(BaseModel):
    text: str
    mode: str = "hybrid"


class VoiceCaptureRequest(BaseModel):
    timeout: int = 5
    phrase_time_limit: Optional[int] = None


class VoiceSettingsUpdate(BaseModel):
    """Everything VoiceSettings can persist.

    update_voice_settings() already accepts any field via hasattr, and
    save_voice_settings() already writes them to the user profile. Only this
    model and the allowlist in update_voice_preferences() were narrower, so
    rate/pitch/volume/persona were unreachable from the UI.
    """

    language: Optional[str] = None
    enabled: Optional[bool] = None
    profile_id: Optional[str] = None
    voice_gender: Optional[str] = None
    rate: Optional[float] = None
    pitch: Optional[float] = None
    volume: Optional[float] = None
    wake_words: Optional[list[str]] = None
    wake_word_sensitivity: Optional[float] = None
    phrase_time_limit: Optional[int] = None
    auto_speak_responses: Optional[bool] = None


class SecurityActionRequest(BaseModel):
    action_name: str
    session_id: str = "default"


class OtpRequestBody(BaseModel):
    action_name: str
    purpose: Optional[str] = None


class OtpVerifyBody(BaseModel):
    action_name: str
    code: str
    token: Optional[str] = None


class PhoneRegisterBody(BaseModel):
    phone: str
    pin: Optional[str] = None


class EnforceActionBody(BaseModel):
    action_name: str
    session_id: str = "default"
    confirmed: bool = False
    pin: Optional[str] = None
    otp: Optional[str] = None
    otp_token: Optional[str] = None
    resource_id: Optional[str] = None


class PasswordResetRequestBody(BaseModel):
    identifier: str


class PasswordResetVerifyBody(BaseModel):
    reset_token: str
    code: str
    otp_token: Optional[str] = None


class PasswordResetConfirmBody(BaseModel):
    reset_token: str
    confirm_token: str
    new_password: str


class DocumentGenerateRequest(BaseModel):
    type: str
    topic: str
    format: str = "txt"
    formats: Optional[list[str]] = None
    page_target: Optional[int] = None
    style: Optional[str] = None
    include_references: bool = False
    citation_style: Optional[str] = None


class ImageGenerateRequest(BaseModel):
    prompt: str
    style: Optional[str] = None
    size: Optional[str] = None


class TransformRequest(BaseModel):
    content: str
    document_type: str = "notes"
    topic: Optional[str] = None
    format: str = "txt"
    formats: Optional[list[str]] = None
    page_target: Optional[int] = None
    style: Optional[str] = None
    include_references: bool = False
    citation_style: Optional[str] = None


class LockRequest(BaseModel):
    resource_id: str
    owner: Optional[str] = None


class InviteRequest(BaseModel):
    email: str


class RevokeAccessRequest(BaseModel):
    email: str


class UnblockIpRequest(BaseModel):
    ip_address: str


class ConfirmationCodeSetRequest(BaseModel):
    code: str
    confirm_code: str


class ConfirmationCodeChangeRequest(BaseModel):
    old_code: str
    new_code: str
    confirm_code: str


class UserProfileUpdateRequest(BaseModel):
    preferred_name: Optional[str] = None
    title: Optional[str] = None
    language: Optional[str] = None
    voice_profile: Optional[str] = None
    voice_gender: Optional[str] = None
    voice_rate: Optional[float] = None
    voice_pitch: Optional[float] = None
    voice_volume: Optional[float] = None
    auto_speak: Optional[bool] = None
    proactive_suggestions: Optional[bool] = None


TASKS_FILE = PROJECT_ROOT / "memory" / "tasks.json"
REMINDERS_FILE = PROJECT_ROOT / "memory" / "reminders.json"
USER_MEMORY_FILE = PROJECT_ROOT / "memory" / "user_memory.json"
LEARNING_FILE = PROJECT_ROOT / "memory" / "aura_learning.json"
IMPROVEMENT_FILE = PROJECT_ROOT / "memory" / "aura_improvement_log.json"
PERMISSIONS_FILE = PROJECT_ROOT / "memory" / "permissions.json"
VOICE_SETTINGS_FILE = PROJECT_ROOT / "memory" / "voice_settings.json"
access_controller = AccessController()
confirmation_system = ConfirmationSystem()


def _cors_headers() -> dict[str, str]:
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
    }


def _provider_health_snapshot(*, force: bool = False) -> dict[str, Any]:
    now = time.time()
    provider_state_version = get_provider_state_version()
    cache_age = now - float(PROVIDER_HEALTH_CACHE["checked_at_ts"] or 0.0)
    state_changed = int(PROVIDER_HEALTH_CACHE.get("provider_state_version", -1)) != provider_state_version
    should_rebuild = force or not PROVIDER_HEALTH_CACHE["items"] or state_changed or cache_age >= PROVIDER_REFRESH_INTERVAL_SECONDS
    if not should_rebuild:
        return PROVIDER_HEALTH_CACHE

    summary = summarize_provider_statuses(fresh=force)
    runtime_summary = get_runtime_provider_summary(fresh=force)
    items = summary.get("items", [])
    snapshot = {
        "checked_at_ts": now,
        "checked_at": datetime.now().isoformat(timespec="seconds"),
        "items": items,
        "providers": dict(summary.get("providers", {})),
        "routing_order": list(summary.get("routing_order", [])),
        "healthy": list(summary.get("healthy", [])),
        "configured": list(summary.get("configured", [])),
        "assistant_runtime": runtime_summary,
        "provider_state_version": provider_state_version,
    }
    PROVIDER_HEALTH_CACHE.update(snapshot)
    return PROVIDER_HEALTH_CACHE


def _refresh_requested(request: Optional[Request]) -> bool:
    if request is None:
        return False
    raw = str(request.query_params.get("refresh", "") or "").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _chat_requests_today() -> Optional[int]:
    if not CHAT_HISTORY_DB_PATH.exists():
        return 0
    try:
        with sqlite3.connect(CHAT_HISTORY_DB_PATH, timeout=5) as connection:
            row = connection.execute(
                """
                SELECT COUNT(*) AS total
                FROM chat_history
                WHERE role = 'user' AND timestamp LIKE ?
                """,
                (f"{datetime.now().strftime('%Y-%m-%d')}%",),
            ).fetchone()
        if not row:
            return 0
        return int(row[0] or 0)
    except Exception:
        return None


def _memory_health_label() -> str:
    try:
        get_memory_stats()
        return "working"
    except Exception:
        return "down"


def _vector_memory_health_label() -> str:
    try:
        status = vector_memory.get_status()
    except Exception:
        return "down"

    if status.get("vector_store_ready"):
        return "working"
    if str(status.get("backend") or "").strip().lower() == "fallback":
        return "fallback"
    return "down"


def _brain_health_label(provider_snapshot: dict[str, Any]) -> str:
    telemetry = get_last_telemetry() or {}
    execution = ((telemetry.get("stages") or {}).get("execution") or {})
    status = str(execution.get("status") or "").strip().lower()
    success = execution.get("success")
    if status == "complete" and success is True:
        return "working"
    if status == "failed":
        return "degraded"
    provider_states = [str(item.get("status") or "").strip().lower() for item in provider_snapshot.get("items", [])]
    if STATUS_HEALTHY in provider_states:
        return "working"
    if any(state in {STATUS_CONFIGURED_UNVERIFIED, STATUS_DEGRADED, STATUS_RATE_LIMITED, STATUS_AUTH_FAILED, STATUS_UNAVAILABLE} for state in provider_states):
        return "degraded"
    return "down"


def _system_health_payload() -> dict[str, Any]:
    provider_snapshot = _provider_health_snapshot(force=False)
    voice_status = get_voice_status()
    requests_today = _chat_requests_today()
    voice_tts_status = str((voice_status.get("tts") or {}).get("status") or "").strip().lower()
    return {
        "brain": _brain_health_label(provider_snapshot),
        "memory": _memory_health_label(),
        "vector_memory": _vector_memory_health_label(),
        "voice_stt": "working" if voice_status.get("stt", {}).get("available") else "unavailable",
        "voice_tts": "browser_only" if voice_tts_status == "browser_only" else ("working" if voice_status.get("tts", {}).get("available") else "unavailable"),
        "providers": dict(provider_snapshot.get("providers", {})),
        "provider_details": provider_snapshot.get("items", []),
        "routing_order": list(provider_snapshot.get("routing_order", [])),
        "assistant_runtime": dict(provider_snapshot.get("assistant_runtime") or {}),
        "truth_notes": {
            "voice": "Voice output is browser-managed, and reliable browser wake remains push-to-talk or beta single-phrase capture.",
            "providers": "Provider status reflects the latest runtime snapshot. Configured providers can still be degraded or rate-limited during live requests.",
        },
        "uptime_seconds": round(time.time() - SERVER_STARTED_AT, 2),
        "total_requests": int(REQUEST_METRICS["total_requests"]),
        "failed_requests": int(REQUEST_METRICS["failed_requests"]),
        "requests_today": requests_today,
    }


def _normalize_session_id(session_id: Optional[str]) -> str:
    value = str(session_id or "").strip()
    if not value:
        return "default"
    value = re.sub(r"[^A-Za-z0-9._:-]+", "-", value)
    return value[:120] or "default"


def _generate_local_session_id() -> str:
    return _normalize_session_id(f"local-{datetime.now(timezone.utc).replace(tzinfo=None).strftime('%Y%m%d%H%M%S')}-{time.time_ns() % 1000000}")


def _read_local_session_cookie(request: Request) -> Optional[str]:
    """Read the anonymous session cookie, accepting pre-rename cookie names."""

    for name in (LOCAL_SESSION_COOKIE_NAME, *LEGACY_LOCAL_SESSION_COOKIE_NAMES):
        value = request.cookies.get(name)
        if value:
            return value
    return None


def _resolve_session_id(request: Optional[Request], explicit: Optional[str] = None) -> str:
    if explicit:
        return _normalize_session_id(explicit)
    if request is not None:
        raw_session = (
            request.headers.get("X-VORIS-Session-Id")
            or request.headers.get("X-AURA-Session-Id")
            or _read_local_session_cookie(request)
        )
        return _normalize_session_id(raw_session)
    return "default"


def _ensure_document_session_id(request: Optional[Request]) -> str:
    resolved = _resolve_session_id(request)
    if resolved != "default":
        return resolved
    return _generate_local_session_id()


def _document_rate_limit_identity(
    request: Optional[Request],
    user: Optional[dict[str, Any]],
    *,
    session_id: Optional[str] = None,
) -> str:
    if user and user.get("id"):
        return f"user:{user['id']}"
    normalized_session_id = _normalize_session_id(session_id) if session_id else _resolve_session_id(request)
    if normalized_session_id != "default":
        return f"session:{normalized_session_id}"
    client_host = request.client.host if request and request.client else "unknown"
    return f"ip:{client_host}"


def _consume_document_rate_limit(
    *,
    request: Optional[Request],
    user: Optional[dict[str, Any]],
    channel: str,
    session_id: Optional[str] = None,
) -> Optional[dict[str, Any]]:
    now = time.time()
    key = f"{channel}:{_document_rate_limit_identity(request, user, session_id=session_id)}"
    recent = [
        stamp
        for stamp in DOCUMENT_RATE_LIMIT_STATE.get(key, [])
        if now - stamp < DOCUMENT_RATE_LIMIT_WINDOW_SECONDS
    ]
    if len(recent) >= DOCUMENT_RATE_LIMIT_MAX_REQUESTS:
        retry_after = max(1, int(DOCUMENT_RATE_LIMIT_WINDOW_SECONDS - (now - recent[0])))
        return {
            "success": False,
            "status": "rate_limited",
            "error": "Document generation is temporarily busy. Please wait a moment and try again.",
            "retry_after_seconds": retry_after,
            "kind": "error",
        }
    recent.append(now)
    DOCUMENT_RATE_LIMIT_STATE[key] = recent
    return None


_CHAT_DOCUMENT_RATE_LIMIT_RE = re.compile(
    r"\b(?:make|create|generate|write|prepare|convert|transform|turn|summari[sz]e)\b.{0,80}\b(?:notes|assignment|slides?|presentation|pdf|docx|txt|pptx)\b",
    flags=re.IGNORECASE,
)


def _should_rate_limit_document_request(context: dict[str, Any]) -> bool:
    if context.get("document_request") is not None:
        return True
    cleaned = str(context.get("cleaned_message") or "")
    if detect_document_retrieval_followup(cleaned):
        return False
    return bool(_CHAT_DOCUMENT_RATE_LIMIT_RE.search(cleaned))


def _attach_local_session_cookie(
    response: Response,
    *,
    session_id: Optional[str],
    user: Optional[dict[str, Any]],
) -> None:
    if user:
        return
    normalized = _normalize_session_id(session_id)
    if normalized == "default":
        return
    response.set_cookie(
        key=LOCAL_SESSION_COOKIE_NAME,
        value=normalized,
        max_age=60 * 60 * 24 * 7,
        httponly=False,
        samesite="lax",
        secure=False,
        path="/",
    )


def _normalize_chat_mode(requested_mode: Optional[str], execution_mode: Optional[str], permission: Optional[dict[str, Any]] = None) -> str:
    normalized_requested = (requested_mode or "hybrid").strip().lower() or "hybrid"
    if permission and not permission.get("success", True):
        return "real"

    execution = (execution_mode or "").strip().lower()
    if execution in {
        "greeting",
        "memory",
        "special_intent",
        "single_agent",
        "generated_agent",
        "permission_blocked",
        "document_generation",
        "external_desktop",
        "action_plan",
        "action_plan_failed",
    }:
        return "real"

    if "agent" in execution and "fallback" not in execution:
        return "real"

    if normalized_requested == "real" and execution not in {"fallback_llm", "multi_command", "empty"}:
        return "real"

    return "hybrid"


def _derive_agent_used(core_result: Optional[dict[str, Any]], detected_intent: str, decision: dict[str, Any]) -> str:
    if core_result:
        capability_cards = core_result.get("agent_capabilities") or []
        if capability_cards and capability_cards[0].get("name"):
            return str(capability_cards[0]["name"])

        used_agents = core_result.get("used_agents") or []
        if used_agents:
            return str(used_agents[0])

    if decision.get("use_agent") and detected_intent:
        return detected_intent

    return decision.get("final_route") or detected_intent or "general"


def _permission_reply(permission: dict[str, Any]) -> str:
    permission_info = permission.get("permission", {})
    approval_type = permission_info.get("approval_type")
    reason = permission_info.get("reason") or "Approval is required before execution."

    if approval_type == "pin":
        pin_status = get_pin_status()
        if not pin_status.get("configured"):
            return "Critical action requires PIN. PIN verification is not configured yet."

    return str(reason)


def _confirmation_reply(context: dict[str, Any]) -> str:
    user = context.get("user") or {}
    user_id = str(user.get("id", "")).strip()
    if not user_id:
        return "That action is protected. Sign in before using critical or personal actions."
    if not confirmation_system.code_exists(user_id):
        return "Please set a confirmation code in Settings first."
    return "VORIS requires your confirmation to proceed."


def _build_chat_success_payload(
    *,
    reply: str,
    intent: str,
    agent_used: str,
    mode: str,
    success: bool = True,
    provider: Optional[str] = None,
    error: Optional[str] = None,
    response_kind: str = "chat",
) -> dict[str, Any]:
    content = shape_response_for_task(reply, mode or intent or response_kind) or "Something went wrong on my side. Try again."
    return {
        "success": bool(success),
        "kind": response_kind,
        "content": content,
        "reply": content,
        "intent": intent,
        "agent_used": agent_used,
        "agent": agent_used,
        "mode": mode,
        "provider": provider,
        "error": error,
        "status": "ok" if success else "degraded",
    }


def _runtime_state_from_trace(trace: dict[str, Any]) -> dict[str, Any]:
    response_mode = str(trace.get("response_mode") or "assistant").strip().lower()
    final_status = str(trace.get("final_status") or "ok").strip().lower()
    has_action_plan = bool(trace.get("action_plan"))
    external_mode = response_mode in {"action", "control", "control_pending"} or has_action_plan
    assistant_state = "error" if final_status == "error" else "responding"
    if response_mode == "control_pending":
        assistant_state = "responding"
    return {
        "assistant_state": assistant_state,
        "response_state": final_status,
        "task_scope": "external" if external_mode else "internal",
        "orb_layout": "floating" if external_mode else "left",
        "voice_state": "unchanged",
    }


def _attach_action_trace(
    payload: dict[str, Any],
    *,
    context: Optional[dict[str, Any]] = None,
    request_id: Optional[str] = None,
    raw_input: Optional[str] = None,
    final_status: Optional[str] = None,
) -> dict[str, Any]:
    context = dict(context or {})
    trace = build_action_trace(
        request_id=request_id or payload.get("request_id"),
        raw_input=raw_input if raw_input is not None else str(context.get("raw_message") or ""),
        intent=str(payload.get("intent") or context.get("detected_intent") or "general"),
        provider=payload.get("provider"),
        permission=payload.get("permission") or context.get("permission"),
        action_plan=payload.get("action_plan"),
        response_mode=payload.get("response_mode"),
        final_status=final_status,
        execution_mode=payload.get("execution_mode") or payload.get("mode"),
        used_agents=payload.get("used_agents") or ([payload.get("agent_used")] if payload.get("agent_used") else []),
        document_delivery=payload.get("document_delivery"),
        kind=payload.get("kind"),
        degraded=bool(payload.get("degraded") or payload.get("status") == "degraded"),
        success=payload.get("success") if isinstance(payload.get("success"), bool) else None,
        status=payload.get("action_status") or payload.get("status"),
        error=payload.get("error"),
        source=payload,
    )
    payload["request_id"] = trace["request_id"]
    payload["action_trace"] = trace
    payload["runtime_state"] = _runtime_state_from_trace(trace)
    payload["response_mode"] = trace["response_mode"]
    return payload


DOCUMENT_PAYLOAD_FIELDS = (
    "download_url",
    "file_name",
    "file_path",
    "document_type",
    "document_format",
    "page_target",
    "document_topic",
    "document_source",
    "document_delivery",
    "document_files",
    "requested_formats",
    "document_style",
    "include_references",
    "citation_style",
    "alternate_format_links",
    "format_links",
    "available_formats",
    "document_title",
    "document_subtitle",
    "document_preview",
)


def _append_document_payload_fields(payload: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    for field in DOCUMENT_PAYLOAD_FIELDS:
        if source.get(field) is not None:
            payload[field] = source.get(field)
    if payload.get("document_delivery"):
        payload["kind"] = "document_delivery"
    return payload


def _sse_event(event: str, data: dict[str, Any]) -> str:
    serialized = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event}\ndata: {serialized}\n\n"


def _chunk_stream_text(text: str, *, target_size: int = 72) -> list[str]:
    """Split completed assistant text into stable UI chunks without duplicating content."""

    normalized = str(text or "")
    if not normalized:
        return []
    tokens = re.findall(r"\S+\s*", normalized)
    chunks: list[str] = []
    current = ""
    for token in tokens:
        current += token
        if len(current) >= target_size or token.endswith((". ", "? ", "! ", "\n")):
            chunks.append(current)
            current = ""
    if current:
        chunks.append(current)
    return chunks


POLLINATIONS_TRIGGER_RE = re.compile(
    r"^(?:generate|create|make|draw)\s+(?:an?\s+)?(?:image|picture|photo|drawing)\s+(?:of\s+)?",
    re.IGNORECASE,
)


def _extract_pollinations_prompt(text: str) -> Optional[str]:
    raw = str(text or "").strip()
    if not raw or not POLLINATIONS_TRIGGER_RE.match(raw):
        return None
    prompt = POLLINATIONS_TRIGGER_RE.sub("", raw, count=1).strip()
    if not prompt:
        return None
    return prompt


def _pollinations_api_key() -> str:
    return os.getenv("POLLINATIONS_API_KEY", "").strip()


def _build_pollinations_unavailable_payload(
    *,
    prompt: str,
    session_id: str,
    request_id: str,
    reason: str,
    error: Optional[str] = None,
) -> dict[str, Any]:
    message = (
        "Image generation is not configured right now. Pollinations now requires an API key, "
        "so add POLLINATIONS_API_KEY to your .env file and restart VORIS."
    )
    if reason == "payment_required":
        message = (
            "Pollinations rejected the image request because the configured key has no available balance "
            "or budget. Add credits or use another POLLINATIONS_API_KEY, then try again."
        )
    elif reason == "provider_failed":
        print(f"IMAGE GENERATION ERROR: {error or 'Pollinations provider failed without details.'}")
        message = "Pollinations did not return an image this time. Please try again in a moment."

    return _attach_action_trace(
        {
            "success": True,
            "reply": message,
            "content": message,
            "execution_mode": "image_generation_unavailable",
            "intent": "image_generation",
            "detected_intent": "image_generation",
            "kind": "image_generation",
            "agent_used": "pollinations",
            "mode": "image_generation_unavailable",
            "session_id": session_id,
            "request_id": request_id,
            "degraded": True,
            "provider": "pollinations",
            "status": reason,
            "error": error,
            "image_generation": {
                "success": False,
                "status": reason,
                "provider": "pollinations",
                "prompt": prompt,
                "images": [],
                "error": error,
                "message": message,
            },
        },
        request_id=request_id,
        raw_input=prompt,
        final_status="degraded",
    )


def _try_pollinations_image_bypass(text: str) -> Optional[dict[str, str]]:
    prompt = _extract_pollinations_prompt(text)
    if not prompt:
        return None
    api_key = _pollinations_api_key()
    if not api_key:
        return None
    encoded_prompt = quote(prompt)
    upstream_url = (
        f"https://gen.pollinations.ai/image/{encoded_prompt}"
        f"?model=flux&width=1024&height=1024&nologo=true&key={quote(api_key)}"
    )
    image_id = hashlib.sha256(f"{prompt}:{time.time()}".encode("utf-8")).hexdigest()[:20]
    request = urllib.request.Request(
        upstream_url,
        headers={"User-Agent": "VORIS/1.0 image-generation"},
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            status_code = int(getattr(response, "status", 200) or 200)
            content_type = str(response.headers.get("Content-Type") or "").lower()
            if status_code != 200 or not content_type.startswith("image/"):
                return {
                    "prompt": prompt,
                    "status": "provider_failed",
                    "error": f"Pollinations returned {status_code} {content_type}".strip(),
                }
            extension = ".jpg" if "jpeg" in content_type or "jpg" in content_type else ".webp" if "webp" in content_type else ".png"
            image_bytes = response.read()
    except urllib.error.HTTPError as exc:
        status_code = int(getattr(exc, "code", 0) or 0)
        return {
            "prompt": prompt,
            "status": "payment_required" if status_code == 402 else "provider_failed",
            "error": f"Pollinations returned HTTP {status_code}",
        }
    except Exception as exc:
        return {"prompt": prompt, "status": "provider_failed", "error": str(exc)}

    if not image_bytes:
        return {"prompt": prompt, "status": "provider_failed", "error": "Pollinations returned an empty image."}
    output_path = GENERATED_IMAGE_DIR / f"pollinations-{image_id}{extension}"
    output_path.write_bytes(image_bytes)
    return {"prompt": prompt, "image_url": f"/generated-images/{output_path.name}", "status": "ok"}


def _build_pollinations_bypass_payload(
    *,
    image_url: str,
    session_id: str,
    request_id: str,
) -> dict[str, Any]:
    return {
        "success": True,
        "reply": image_url,
        "content": image_url,
        "image_url": image_url,
        "execution_mode": "image_bypass",
        "intent": "image_generation",
        "detected_intent": "image_generation",
        "kind": "image_generation",
        "agent_used": "pollinations",
        "mode": "image_bypass",
        "session_id": session_id,
        "request_id": request_id,
    }


def _should_stream_reply_payload(payload: dict[str, Any]) -> bool:
    if payload.get("document_delivery") or payload.get("action_plan"):
        return False
    execution_mode = str(payload.get("execution_mode") or payload.get("mode") or "").lower()
    if execution_mode == "image_bypass" or execution_mode.startswith("document") or "action" in execution_mode:
        return False
    return True


def _json_response_payload(response: Response) -> tuple[dict[str, Any], int, Optional[str]]:
    body = getattr(response, "body", b"") or b""
    try:
        payload = json.loads(body.decode("utf-8")) if body else {}
    except Exception:
        payload = {}
    return payload if isinstance(payload, dict) else {}, int(getattr(response, "status_code", 200)), response.headers.get("set-cookie")


def _build_image_generation_chat_payload(
    *,
    raw_message: str,
    request_id: str,
    session_id: str,
    style: Optional[str] = None,
    size: Optional[str] = None,
) -> dict[str, Any]:
    image_result = generate_image(raw_message, style=style, size=size)
    reply = image_result.get("message") or "Image generation is not configured yet."
    payload = _build_chat_success_payload(
        reply=reply,
        intent="image_generation",
        agent_used="image_generation",
        mode="image_generation_unavailable",
        success=True,
        provider=image_result.get("provider"),
        error=image_result.get("error"),
        response_kind="image_generation",
    )
    payload.update(
        {
            "kind": "image_generation",
            "execution_mode": "image_generation_unavailable",
            "session_id": session_id,
            "degraded": True,
            "image_generation": image_result,
            "image_provider_status": get_image_generation_status(),
            "permission": build_permission_response("image_generation", confirmed=True),
            "routing_trace": {
                "input": raw_message,
                "intent": "image_generation",
                "agent": "image_generation",
                "provider": image_result.get("provider") or "none",
                "output": reply,
                "execution_mode": "image_generation_unavailable",
            },
        }
    )
    _attach_action_trace(
        payload,
        request_id=request_id,
        raw_input=raw_message,
        final_status="degraded",
    )
    return payload


def _build_vision_chat_payload(
    *,
    raw_message: str,
    request_id: str,
    session_id: str,
) -> dict[str, Any]:
    provider_result: dict[str, Any] = {}
    error_message: Optional[str] = None
    vision_provider = DEFAULT_REASONING_PROVIDER
    try:
        provider_result = generate_with_provider(
            vision_provider,
            [{"role": "user", "content": raw_message}],
            max_tokens=4096,
            temperature=0.2,
        )
        reply = clean_response(provider_result.get("text")) or "I received the image, but the vision provider returned no description."
        success = bool(provider_result.get("success") and reply)
    except Exception as error:
        error_message = str(error)
        reply = (
            "I received the image, but the vision provider failed before it could describe it. "
            f"Check your {vision_provider} key and vision model setting, then try the same image again."
        )
        success = False

    payload = _build_chat_success_payload(
        reply=reply,
        intent="vision",
        agent_used="groq_vision",
        mode="vision" if success else "vision_error",
        success=success,
        provider=provider_result.get("provider") or "groq",
        error=error_message or provider_result.get("error"),
        response_kind="vision",
    )
    payload.update(
        {
            "kind": "vision",
            "execution_mode": "vision" if success else "vision_error",
            "session_id": session_id,
            "degraded": not success,
            "model": provider_result.get("model") or GROQ_VISION_MODEL,
            "providers_tried": provider_result.get("providers_tried", []),
            "permission": build_permission_response("general", confirmed=True),
            "routing_trace": {
                "input": "[image upload]",
                "intent": "vision",
                "agent": "groq_vision",
                "provider": provider_result.get("provider") or "groq",
                "output": reply,
                "execution_mode": "vision" if success else "vision_error",
            },
        }
    )
    _attach_action_trace(
        payload,
        request_id=request_id,
        raw_input="[image upload]",
        final_status="ok" if success else "error",
    )
    return payload


def _normalize_casual_conversation_input(message: str) -> str:
    lowered = str(message or "").strip().lower()
    lowered = re.sub(r"[^\w\s']", " ", lowered)
    lowered = re.sub(r"\s+", " ", lowered)
    return lowered.strip()


def _build_casual_conversation_reply(
    message: str,
    user_profile: Optional[dict[str, Any]] = None,
    *,
    session_id: Optional[str] = None,
) -> Optional[str]:
    normalized = _normalize_casual_conversation_input(message)
    if not normalized:
        return None

    profile = dict(user_profile or {})
    display_name = get_personal_display_name(
        profile,
        allow_memory_fallback=True,
        session_id=session_id,
    )
    greeting_prefix = f"Hey {display_name}." if display_name else "Hey."

    greeting_inputs = {
        "hi": f"{greeting_prefix} What can I help you with?",
        "hello": f"{greeting_prefix} What can I help you with?",
        "hey": f"{greeting_prefix} What can I help you with?",
        "hi voris": f"{greeting_prefix} I'm here.",
        "hello voris": f"{greeting_prefix} I'm here.",
        "hey voris": f"{greeting_prefix} I'm here.",
        "hi aura": f"{greeting_prefix} I'm here.",
        "hello aura": f"{greeting_prefix} I'm here.",
        "hey aura": f"{greeting_prefix} I'm here.",
    }
    if normalized in greeting_inputs:
        return greeting_inputs[normalized]

    check_in_inputs = {
        "how are you",
        "how are you doing",
        "how are you doing today",
        "how are you today",
        "hi how are you",
        "hello how are you",
        "hey how are you",
        "hi voris how are you",
        "hello voris how are you",
        "hey voris how are you",
        "hi voris how are you doing",
        "hello voris how are you doing",
        "hey voris how are you doing",
        "hello voris how are you doing today",
        "hi aura how are you",
        "hello aura how are you",
        "hey aura how are you",
        "hi aura how are you doing",
        "hello aura how are you doing",
        "hey aura how are you doing",
        "hello aura how are you doing today",
    }
    if normalized in check_in_inputs:
        return "I'm doing great. What do you need?"

    return None


def _build_casual_chat_payload(context: dict[str, Any]) -> Optional[dict[str, Any]]:
    profile = {**(context.get("user_profile") or {}), **(context.get("user") or {})}
    reply = _build_casual_conversation_reply(
        context.get("raw_message") or context.get("cleaned_message") or "",
        profile,
        session_id=context.get("session_id"),
    )
    if not reply:
        return None

    permission = build_permission_response("general", confirmed=True)
    intent = str(context.get("detected_intent") or "conversation")
    payload = _build_chat_success_payload(
        reply=reply,
        intent=intent,
        agent_used="General VORIS",
        mode=_normalize_chat_mode(context.get("requested_mode"), "greeting", permission),
        provider="local",
    )
    payload["decision"] = context.get("decision", {})
    payload["permission"] = permission
    payload["execution_mode"] = "casual_local"
    payload["used_agents"] = ["general"]
    payload["plan"] = []
    payload["orchestration"] = {
        "primary_agent": "general",
        "secondary_agents": [],
        "execution_order": [],
        "requires_multiple": False,
        "primary_selection_source": "casual_shortcut",
        "reason": "Local casual conversation shortcut handled a simple greeting or check-in.",
    }
    payload["confidence"] = context.get("confidence", 1.0)
    payload["session_id"] = context.get("session_id")
    payload["provider"] = "local"
    payload["model"] = "local"
    payload["providers_tried"] = []
    payload["degraded"] = False
    return payload


def _persist_chat_turn(context: dict[str, Any], reply: str, intent: str, agent_used: Optional[str], mode: Optional[str]) -> None:
    save_message(
        context["session_id"],
        "user",
        context["raw_message"],
        intent=intent,
        agent_used=None,
        mode=context["requested_mode"],
    )
    save_message(
        context["session_id"],
        "assistant",
        reply,
        intent=intent,
        agent_used=agent_used,
        mode=mode or context["requested_mode"],
    )


def _attempt_persist_chat_turn(context: dict[str, Any], reply: str, intent: str, agent_used: Optional[str], mode: Optional[str]) -> dict[str, Any]:
    if not context.get("user"):
        return {"saved": False, "backend": "session", "reason": "public_memory_not_persisted"}
    try:
        _persist_chat_turn(context, reply, intent, agent_used, mode)
        return {"saved": True, "backend": "sqlite"}
    except Exception as error:
        return {"saved": False, "backend": "sqlite", "error": str(error)}


def _public_access_override(
    permission: dict[str, Any],
    *,
    user: Optional[dict[str, Any]],
) -> dict[str, Any]:
    if user:
        return permission

    permission_info = dict(permission.get("permission") or {})
    trust_level = str(permission_info.get("trust_level") or "").strip().lower()
    if trust_level not in {"private", "sensitive", "critical"}:
        return permission

    approval_type = permission_info.get("approval_type") or "none"
    reason = "Sign in to use protected, personal, or system-level actions. Basic assistant chat stays available without an account."
    return {
        "success": False,
        "status": "login_required",
        "mode": "real",
        "permission": {
            **permission_info,
            "approval_type": approval_type,
            "reason": reason,
        },
    }


def _prepare_chat_context(
    raw_message: str,
    requested_mode: Optional[str],
    session_id: Optional[str] = None,
    *,
    user: Optional[dict[str, Any]] = None,
    confirmation_code: Optional[str] = None,
    confirmed: bool = False,
    pin: Optional[str] = None,
    otp: Optional[str] = None,
    otp_token: Optional[str] = None,
    session_token: Optional[str] = None,
) -> dict[str, Any]:
    message = (raw_message or "").strip()
    mode = (requested_mode or "hybrid").strip().lower() or "hybrid"
    if not message:
        raise ValueError("message is required")

    cleaned_message = clean_user_input(message)
    if not cleaned_message:
        raise ValueError("message is required")

    normalized_session_id = _normalize_session_id(session_id)
    document_request = resolve_document_request(cleaned_message, session_id=normalized_session_id)
    if document_request is None and _is_unclear_document_request(cleaned_message):
        print(f"[CHAT] Unclear document request detected — returning clarification. input={repr(cleaned_message[:120])}")
        return {
            "clarification_reply": "What topic would you like the document to cover? For example: \"notes on machine learning\" or \"assignment on the French Revolution\".",
            "session_id": normalized_session_id,
        }
    retrieval_followup = None
    if document_request is None:
        retrieval_followup = detect_document_retrieval_followup(cleaned_message)
    detected_intent, confidence = detect_intent_with_confidence(cleaned_message)
    if document_request is not None or retrieval_followup is not None:
        permission_action = "document_generation"
        detected_intent = "document"
        confidence = 1.0
    else:
        permission_action = detected_intent
    decision = build_decision_summary(detected_intent, confidence, AGENT_ROUTER)
    security_context = {
        "username": user.get("username") if user else None,
        "user_id": user.get("id") if user else None,
        "session_token": session_token if user else None,
        "confirmed": bool(confirmed),
        "pin": pin,
        "otp": otp,
        "otp_token": otp_token,
    }
    access = enforce_action(
        permission_action,
        username=str(user.get("username")) if user else None,
        user_id=str(user.get("id")) if user else None,
        session_id=normalized_session_id,
        session_token=session_token if user else None,
        confirmed=bool(confirmed),
        pin=pin,
        otp=otp,
        otp_token=otp_token,
        require_auth=permission_action != "document_generation",
        meta={"layer": "api", "endpoint": "chat_precheck"},
    )
    permission = {
        "success": bool(access.get("allowed")),
        "status": "approved" if access.get("allowed") else str(access.get("status") or "blocked"),
        "mode": "real",
        "permission": {
            **dict(access.get("decision") or {}),
            "action_name": permission_action,
            "trust_level": str(access.get("trust_level") or ((access.get("decision") or {}).get("trust_level") or "safe")),
            "approval_type": str(access.get("approval_type") or ((access.get("decision") or {}).get("approval_type") or "none")),
            "reason": str(access.get("reason") or ((access.get("decision") or {}).get("reason") or "")),
            "required_action": str(access.get("required_action") or "allow"),
            "next_step_hint": str(access.get("next_step_hint") or ""),
        },
        "enforcement": access,
    }
    confirmation_required = False
    confirmation_ok = False
    return {
        "raw_message": message,
        "requested_mode": mode,
        "session_id": normalized_session_id,
        "cleaned_message": cleaned_message,
        "document_request": document_request,
        "document_retrieval_followup": retrieval_followup,
        "detected_intent": detected_intent,
        "confidence": confidence,
        "decision": decision,
        "permission": permission,
        "permission_action": permission_action,
        "user": user,
        "user_profile": dict(user or {}),
        "confirmation_required": confirmation_required,
        "confirmation_ok": confirmation_ok,
        "security_context": security_context,
    }


def _build_blocked_chat_payload(context: dict[str, Any], permission: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    active_permission = permission or context["permission"]
    if context.get("confirmation_required") and not context.get("confirmation_ok"):
        blocked_reply = _confirmation_reply(context)
    else:
        blocked_reply = _permission_reply(active_permission)
    agent_used = _derive_agent_used(None, context["detected_intent"], context["decision"])
    payload = _build_chat_success_payload(
        reply=blocked_reply,
        intent=context["detected_intent"] or "permission",
        agent_used=agent_used,
        mode=_normalize_chat_mode(context["requested_mode"], "permission_blocked", active_permission),
        provider="policy",
    )
    payload["permission"] = active_permission
    payload["decision"] = context["decision"]
    payload["confidence"] = context["confidence"]
    payload["session_id"] = context["session_id"]
    payload["confirmation_required"] = bool(context.get("confirmation_required"))
    return payload


UNUSABLE_CHAT_REPLY_MARKERS = (
    FALLBACK_USER_MESSAGE.strip().lower(),
    "couldn't generate a useful response",
    "is planned, but it is not available for live chat yet.",
    "agent failed:",
)


def _emit_chat_log(message: str, *, fallback: Optional[str] = None) -> None:
    try:
        print(message)
    except UnicodeEncodeError:
        print(fallback or message.encode("ascii", "replace").decode("ascii"))


def _chat_log_preview(value: Any, limit: int = 140) -> str:
    text = clean_response(str(value or ""))
    if len(text) > limit:
        return text[:limit]
    return text


def _log_chat_trace(
    *,
    raw_input: str,
    intent: str,
    agent: str,
    provider: Optional[str],
    output: str,
    execution_mode: Optional[str] = None,
    status: Optional[str] = None,
    request_id: Optional[str] = None,
) -> None:
    input_preview = _chat_log_preview(raw_input, limit=120)
    output_preview = _chat_log_preview(output, limit=160)
    provider_label = str(provider or "none").strip().lower() or "none"
    intent_label = str(intent or "general").strip().lower() or "general"
    agent_label = str(agent or "general").strip().lower() or "general"
    extra = []
    if execution_mode:
        extra.append(f"mode={execution_mode}")
    if status:
        extra.append(f"status={status}")
    if request_id:
        extra.append(f"request_id={request_id}")
    suffix = f" ({', '.join(extra)})" if extra else ""
    unicode_message = (
        f"[CHAT TRACE] input={input_preview} → intent={intent_label} → agent={agent_label} "
        f"→ provider={provider_label} → output={output_preview}{suffix}"
    )
    ascii_message = (
        f"[CHAT TRACE] input={input_preview} -> intent={intent_label} -> agent={agent_label} "
        f"-> provider={provider_label} -> output={output_preview}{suffix}"
    )
    _emit_chat_log(unicode_message, fallback=ascii_message)


def _is_unusable_reply_text(text: Optional[str]) -> bool:
    normalized = clean_response(text).strip().lower()
    if not normalized:
        return True
    return any(marker in normalized for marker in UNUSABLE_CHAT_REPLY_MARKERS)

def _execute_chat_pipeline(context: dict[str, Any]) -> dict[str, Any]:
    result = process_command_detailed(
        context["cleaned_message"],
        session_id=context["session_id"],
        user_profile={**(context.get("user_profile") or {}), **(context.get("user") or {})},
        current_mode=context["requested_mode"],
        security_context=context.get("security_context") or {},
    )
    execution_mode = result.get("execution_mode")
    _chat_intent = result.get("detected_intent") or result.get("intent")
    print(
        f"[CHAT] Agent selected: {result.get('used_agents')}  "
        f"execution_mode={execution_mode!r}  "
        f"intent={_chat_intent!r}  "
        f"confidence={result.get('confidence', 0):.2f}"
    )

    if result.get("intent") == "error" or execution_mode == "error":
        print(f"[CHAT FALLBACK] Brain returned error intent: {result.get('response')!r}")
        result["response"] = clean_response(result.get("response")) or build_degraded_reply(
            context["cleaned_message"],
            result.get("providers_tried") or [],
        )
        result["execution_mode"] = "degraded_assistant"
        result["degraded"] = True
        result["provider"] = None
        result["model"] = None
        execution_mode = "degraded_assistant"

    runtime_permission = result.get("permission")
    if runtime_permission and not runtime_permission.get("success", True):
        payload = _build_blocked_chat_payload(context, runtime_permission)
        payload["decision"] = result.get("decision") or context["decision"]
        return payload

    reply_text = shape_response_for_task(result.get("response"), execution_mode or _chat_intent)
    if execution_mode == "document_generation":
        document_delivery = result.get("document_delivery") or {}
        delivery_message = clean_response(document_delivery.get("delivery_message"))
        if delivery_message:
            reply_text = delivery_message

    if _is_unusable_reply_text(reply_text):
        _raw_reply_preview = repr(str(result.get("response") or ""))[:80]
        print(
            f"[CHAT FALLBACK] Initial reply unusable — "
            f"raw={_raw_reply_preview}  "
            f"execution_mode={execution_mode!r}. "
            f"Attempting generate_response_payload fallback."
        )
        fallback_payload = generate_response_payload(context["cleaned_message"])
        if fallback_payload.get("success"):
            reply_text = shape_response_for_task(fallback_payload.get("content"), execution_mode or context["detected_intent"])
            result["provider"] = fallback_payload.get("provider")
            result["model"] = fallback_payload.get("model")
            result["providers_tried"] = fallback_payload.get("providers_tried") or []
            print(f"[CHAT FALLBACK] Fallback succeeded via provider={result['provider']!r}")
        else:
            providers_tried = fallback_payload.get("providers_tried") or []
            error_msg = fallback_payload.get("error") or "All configured providers failed."
            print(
                f"[CHAT FALLBACK] All providers failed. "
                f"providers_tried={providers_tried}  error={error_msg!r}. "
                f"Using degraded reply."
            )
            reply_text = shape_response_for_task(
                fallback_payload.get("degraded_reply")
                or build_degraded_reply(context["cleaned_message"], providers_tried),
                "degraded_assistant",
            )
            result["provider"] = None
            result["model"] = None
            result["providers_tried"] = providers_tried
            result["degraded"] = True
            result["error"] = error_msg
            execution_mode = "degraded_assistant"

    if _is_unusable_reply_text(reply_text):
        print(f"[CHAT FALLBACK] Reply still unusable after all fallbacks — raising RuntimeError.")
        providers_tried = list(result.get("providers_tried") or [])
        error_message = str(result.get("error") or "The response path returned unusable content.").strip()
        _emit_chat_log("[CHAT FALLBACK] Reply still unusable after all fallbacks. Using structured degraded reply.")
        reply_text = shape_response_for_task(build_degraded_reply(context["cleaned_message"], providers_tried), "degraded_assistant")
        result["provider"] = None
        result["model"] = None
        result["providers_tried"] = providers_tried
        result["degraded"] = True
        result["error"] = error_message
        execution_mode = "degraded_assistant"

    agent_used = _derive_agent_used(result, context["detected_intent"], context["decision"])
    response_mode = _normalize_chat_mode(context["requested_mode"], execution_mode, runtime_permission)
    degraded = bool(result.get("degraded") or result.get("execution_mode") == "degraded_assistant")
    provider_name = result.get("provider") or ("local" if not degraded else None)
    error_message = str(result.get("error") or "").strip() or None

    payload = _build_chat_success_payload(
        reply=reply_text,
        intent=str(result.get("detected_intent") or result.get("intent") or context["detected_intent"] or "general"),
        agent_used=agent_used,
        mode=response_mode,
        success=not degraded,
        provider=provider_name,
        error=error_message,
        response_kind="document_delivery" if execution_mode == "document_generation" else "chat",
    )
    payload["decision"] = result.get("decision") or context["decision"]
    payload["permission"] = runtime_permission or context["permission"]
    payload["execution_mode"] = execution_mode
    payload["used_agents"] = result.get("used_agents", [])
    payload["plan"] = result.get("plan", [])
    payload["orchestration"] = result.get("orchestration", {})
    payload["confidence"] = result.get("confidence", context["confidence"])
    payload["session_id"] = context["session_id"]
    payload["provider"] = provider_name
    payload["model"] = result.get("model")
    payload["providers_tried"] = result.get("providers_tried", [])
    payload["degraded"] = degraded
    if result.get("personal_context"):
        payload["personal_context"] = result.get("personal_context")
    payload["routing_trace"] = {
        "input": clean_response(context["raw_message"]),
        "intent": str(result.get("detected_intent") or result.get("intent") or context["detected_intent"] or "general"),
        "agent": agent_used,
        "provider": provider_name or "none",
        "output": reply_text,
        "execution_mode": execution_mode or "unknown",
    }
    for field in (
        "desktop_app",
        "desktop_label",
        "desktop_launch_status",
        "desktop_launch_success",
        "desktop_launched_with",
        "desktop_pid",
        "action_plan",
        "action_steps",
        "action_success",
        "action_status",
        "failed_action_step",
        "action_suggestions",
        "action_memory",
        "automation_confirmation_required",
        "automation_control",
    ):
        if field in result:
            payload[field] = result.get(field)
    return _append_document_payload_fields(payload, result)


def _now_string() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def _read_json_list(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        return payload if isinstance(payload, list) else []
    except Exception:
        return []


def _read_json_object(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as file:
            payload = json.load(file)
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _write_json_list(path: Path, items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(items, file, indent=2, ensure_ascii=False)


def _next_id(items: list[dict[str, Any]]) -> int:
    return max((int(item.get("id", 0)) for item in items), default=0) + 1


def _task_summary(tasks: list[dict[str, Any]]) -> dict[str, int]:
    pending = sum(1 for task in tasks if task.get("status") != "completed")
    completed = sum(1 for task in tasks if task.get("status") == "completed")
    return {
        "total": len(tasks),
        "pending": pending,
        "completed": completed,
    }


def _reminder_summary(reminders: list[dict[str, Any]]) -> dict[str, int]:
    active = sum(1 for reminder in reminders if reminder.get("status", "active") == "active")
    completed = sum(1 for reminder in reminders if reminder.get("status") == "completed")
    return {
        "total": len(reminders),
        "active": active,
        "completed": completed,
    }


def _build_personalized_greeting(user_name: str | None) -> str:
    if user_name:
        return f"Welcome back, {user_name}. VORIS is ready."
    return "Hello. VORIS is ready."


def _normalize_name(*values: Any) -> Optional[str]:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text.title()
    return None


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _is_secure_request(request: Request) -> bool:
    return str(request.url.scheme).lower() == "https"


def _read_html(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _current_user(request: Request) -> Optional[dict[str, Any]]:
    return get_request_user(request)


def _require_authenticated_user(request: Request) -> dict[str, Any]:
    user = _current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required.")
    return user


def _require_admin_user(request: Request) -> dict[str, Any]:
    user = _require_authenticated_user(request)
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="Admin access required.")
    return user


PUBLIC_PATHS = {
    "/",
    "/ping",
    "/classic",
    "/login",
    "/register",
    "/forgot-password",
    "/setup",
    "/api/login",
    "/api/register",
    "/api/setup",
    "/api/auth/session",
    "/api/auth/password-reset/request",
    "/api/auth/password-reset/verify",
    "/api/auth/password-reset/confirm",
    "/api/chat",
    "/api/chat/file",
    "/api/capabilities",
    "/api/providers",
    "/api/telemetry/providers",
    "/api/system/health",
    "/api/assistant/runtime",
    "/api/voice/desktop/start",
    "/api/voice/desktop/stop",
    "/api/voice/desktop/interrupt",
    "/api/voice/status",
    "/api/voice/text",
    "/api/desktop/apps",
    "/api/chat/stream",
    "/api/generate/document",
    "/api/generate/image",
    "/api/image/status",
    "/api/media/status",
    "/api/media/job",
    "/api/transform",
    "/api/transform/file",
}


@app.middleware("http")
async def aura_request_metrics_middleware(request: Request, call_next):
    track_request = request.url.path in {"/api/chat", "/chat"}
    try:
        response = await call_next(request)
    except Exception:
        if track_request:
            REQUEST_METRICS["total_requests"] += 1
            REQUEST_METRICS["failed_requests"] += 1
        raise

    if track_request:
        REQUEST_METRICS["total_requests"] += 1
        if int(getattr(response, "status_code", 200)) >= 400:
            REQUEST_METRICS["failed_requests"] += 1
    return response


@app.middleware("http")
async def aura_private_access_middleware(request: Request, call_next):
    path = request.url.path
    if path.startswith("/static") or path.startswith("/assets") or path.startswith("/downloads") or path.startswith("/generated-images") or path.startswith("/generated-media"):
        return await call_next(request)

    setup_required = requires_first_run_setup()
    user = _current_user(request)

    if setup_required:
        if path in {"/setup", "/api/setup", "/api/auth/session"}:
            return await call_next(request)
        if path.startswith("/api/"):
            return JSONResponse(status_code=503, content={"error": "VORIS setup is required.", "status": "setup_required"})
        if path != "/setup":
            return RedirectResponse("/setup", status_code=302)
        return await call_next(request)

    if path in PUBLIC_PATHS:
        return await call_next(request)

    if user:
        return await call_next(request)

    if path.startswith("/api/"):
        return JSONResponse(status_code=401, content={"error": "Authentication required.", "status": "error"})

    if path != "/login":
        return RedirectResponse("/login", status_code=302)
    return await call_next(request)


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    if requires_first_run_setup():
        return RedirectResponse("/setup", status_code=302)
    if MODERN_UI_INDEX.is_file():
        return HTMLResponse(_read_html(MODERN_UI_INDEX))
    return HTMLResponse(_read_html(APP_HTML))


@app.get("/ping")
async def ping():
    return {"status": "online"}


@app.get("/classic", response_class=HTMLResponse)
async def classic_workspace(request: Request):
    if requires_first_run_setup():
        return RedirectResponse("/setup", status_code=302)
    return HTMLResponse(_read_html(APP_HTML))


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if requires_first_run_setup():
        return RedirectResponse("/setup", status_code=302)
    if _current_user(request):
        return RedirectResponse("/", status_code=302)
    return HTMLResponse(_read_html(LOGIN_HTML))


@app.get("/setup", response_class=HTMLResponse)
async def setup_page(request: Request):
    if not requires_first_run_setup() and _current_user(request):
        return RedirectResponse("/", status_code=302)
    if not requires_first_run_setup() and not _current_user(request):
        return RedirectResponse("/login", status_code=302)
    return HTMLResponse(_read_html(SETUP_HTML))


@app.get("/register", response_class=HTMLResponse)
async def register_page(request: Request):
    if requires_first_run_setup():
        return RedirectResponse("/setup", status_code=302)
    if _current_user(request):
        return RedirectResponse("/", status_code=302)
    return HTMLResponse(_read_html(REGISTER_HTML))


@app.get("/signup", response_class=HTMLResponse)
async def signup_page(request: Request):
    if requires_first_run_setup():
        return RedirectResponse("/setup", status_code=302)
    if _current_user(request):
        return RedirectResponse("/", status_code=302)
    return HTMLResponse(_read_html(REGISTER_HTML))


@app.get("/forgot-password", response_class=HTMLResponse)
async def forgot_password_page(request: Request):
    if requires_first_run_setup():
        return RedirectResponse("/setup", status_code=302)
    if _current_user(request):
        return RedirectResponse("/", status_code=302)
    return HTMLResponse(_read_html(FORGOT_PASSWORD_HTML))


@app.get("/reset", response_class=HTMLResponse)
async def reset_page(request: Request):
    if requires_first_run_setup():
        return RedirectResponse("/setup", status_code=302)
    if _current_user(request):
        return RedirectResponse("/", status_code=302)
    return HTMLResponse(_read_html(FORGOT_PASSWORD_HTML))


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request):
    _require_admin_user(request)
    return HTMLResponse(_read_html(ADMIN_HTML))


@app.post("/api/login")
async def login(data: LoginData, request: Request):
    success, result, session_token = authenticate_user(
        data.username,
        data.password,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
    )
    if not success or not session_token:
        raise HTTPException(status_code=401, detail=result)

    response = JSONResponse(
        {
            "success": True,
            "user": result,
            "message": f"Welcome back, {result.get('preferred_name') or result.get('name') or result.get('username')}. How may I assist you?",
        }
    )
    set_session_cookie(response, session_token, secure=_is_secure_request(request))
    return response


@app.post("/api/register")
async def register(data: RegisterData):
    success, result = register_auth_user(
        data.username,
        data.password,
        data.name,
        data.email,
        title=data.title or "sir",
        preferred_name=data.preferred_name or "",
    )
    if success:
        return {"success": True, "user": result, "message": "Registration complete. You may now sign in."}
    raise HTTPException(status_code=400, detail=result)


@app.post("/api/setup")
async def setup_owner(data: SetupData):
    success, result = create_owner_account(
        username=data.username,
        password=data.password,
        name=data.name,
        email=data.email,
        master_pin=data.master_pin,
        title=data.title or "sir",
        preferred_name=data.preferred_name or "",
    )
    if success:
        return {"success": True, "user": result, "message": "VORIS online. Owner account created."}
    raise HTTPException(status_code=400, detail=result)


@app.post("/api/logout")
async def logout_endpoint(request: Request):
    session_id = _resolve_session_id(request)
    clear_session_context(session_id)
    logout_request(request)
    response = JSONResponse({"success": True, "message": "Session secured."})
    clear_session_cookie(response, secure=_is_secure_request(request))
    for _cookie_name in (LOCAL_SESSION_COOKIE_NAME, *LEGACY_LOCAL_SESSION_COOKIE_NAMES):
        response.delete_cookie(_cookie_name, path="/")
    return response


@app.get("/logout")
async def logout_page(request: Request):
    session_id = _resolve_session_id(request)
    clear_session_context(session_id)
    logout_request(request)
    response = RedirectResponse("/login", status_code=302)
    clear_session_cookie(response, secure=_is_secure_request(request))
    for _cookie_name in (LOCAL_SESSION_COOKIE_NAME, *LEGACY_LOCAL_SESSION_COOKIE_NAMES):
        response.delete_cookie(_cookie_name, path="/")
    return response


@app.post("/api/auth/password-reset/request")
async def password_reset_request_endpoint(payload: PasswordResetRequestBody, request: Request):
    result = request_password_reset(
        payload.identifier,
        ip_address=_client_ip(request),
        user_agent=request.headers.get("user-agent", ""),
        session_id=_resolve_session_id(request),
    )
    status_code = 200 if result.get("success") else 429 if result.get("status") == "rate_limited" else 400
    return JSONResponse(result, status_code=status_code)


@app.post("/api/auth/password-reset/verify")
async def password_reset_verify_endpoint(payload: PasswordResetVerifyBody, request: Request):
    result = verify_password_reset(
        payload.reset_token,
        payload.code,
        otp_token=payload.otp_token,
        ip_address=_client_ip(request),
    )
    status_code = 200 if result.get("success") else 400
    return JSONResponse(result, status_code=status_code)


@app.post("/api/auth/password-reset/confirm")
async def password_reset_confirm_endpoint(payload: PasswordResetConfirmBody, request: Request):
    result = confirm_password_reset(
        payload.reset_token,
        payload.confirm_token,
        payload.new_password,
        ip_address=_client_ip(request),
    )
    status_code = 200 if result.get("success") else 400
    response = JSONResponse(result, status_code=status_code)
    # Defence-in-depth: if the caller's cookie session belongs to the user
    # whose password just rotated, clear it so the next request forces a
    # fresh login with the new credentials.
    if result.get("success"):
        clear_session_cookie(response, secure=_is_secure_request(request))
    return response


@app.get("/api/auth/session")
async def auth_session_status(request: Request):
    user = _current_user(request)
    session_snapshot = describe_login_session(read_session_token(request))
    return {
        "authenticated": bool(user),
        "access_mode": "authenticated" if user else "public",
        "setup_required": requires_first_run_setup(),
        "user": user,
        "session_valid": bool(session_snapshot.get("valid")),
        "session_reason": session_snapshot.get("reason"),
        "session_expires_at": session_snapshot.get("expires_at"),
        "session_remaining_seconds": session_snapshot.get("remaining_seconds"),
        "status": "ok",
    }


# Legacy compatibility endpoint. The web_v2 source of truth is POST /api/chat;
# keep this narrow wrapper traceable so old callers do not bypass observability.
@app.post("/chat")
async def chat(command: Command):
    request_id = new_request_id("legacy-chat")

    vision_payload = extract_vision_payload(command.text)
    if vision_payload is not None:
        try:
            vision_provider = DEFAULT_REASONING_PROVIDER
            print(f"[DISPATCHER] Vision detected. Routing to {vision_provider}.")
            provider_result = generate_with_provider(
                vision_provider,
                [{"role": "user", "content": command.text}],
                max_tokens=4096,
                temperature=0.7,
            )
            vision_response = clean_response(provider_result.get("text")) or (
                "I received the image, but the vision provider returned no description."
            )
            return {
                "intent": "vision",
                "detected_intent": "vision",
                "confidence": 1.0,
                "response": vision_response,
                "username": command.username,
                "plan": [],
                "used_agents": [f"{vision_provider}_vision"],
                "execution_mode": "vision_bypass",
            }
        except Exception as e:
            print(f"[ERROR] Vision engine failed: {e}")

    pollinations_bypass = _try_pollinations_image_bypass(command.text)
    if pollinations_bypass and pollinations_bypass.get("image_url"):
        return {
            "intent": "image_generation",
            "detected_intent": "image_generation",
            "confidence": 1.0,
            "response": pollinations_bypass["image_url"],
            "image_url": pollinations_bypass["image_url"],
            "username": command.username,
            "plan": [],
            "used_agents": ["pollinations"],
            "execution_mode": "image_bypass",
        }
    if pollinations_bypass:
        return {
            "intent": "image_generation",
            "detected_intent": "image_generation",
            "confidence": 1.0,
            "response": "Image generation is unavailable right now.",
            "username": command.username,
            "plan": [],
            "used_agents": [],
            "execution_mode": "image_unavailable",
            "error": pollinations_bypass.get("error"),
        }

    try:
        result = process_command_detailed(command.text)
        response = result["response"]

        legacy_context = {
            "session_id": _normalize_session_id(command.username or "default"),
            "raw_message": command.text,
            "requested_mode": "hybrid",
        }
        history_status = _attempt_persist_chat_turn(
            legacy_context,
            response,
            result.get("detected_intent") or result.get("intent") or "general",
            (result.get("used_agents") or [None])[0],
            result.get("execution_mode") or "hybrid",
        )

        response_payload = {
            "intent": result["intent"],
            "detected_intent": result["detected_intent"],
            "confidence": round(result["confidence"], 2),
            "response": response,
            "username": command.username,
            "plan": result.get("plan", []),
            "used_agents": result.get("used_agents", []),
            "agent_capabilities": result.get("agent_capabilities", []),
            "execution_mode": result.get("execution_mode"),
            "decision": result.get("decision", {}),
            "orchestration": result.get("orchestration", {}),
            "permission_action": result.get("permission_action"),
            "permission": result.get("permission", {}),
            "history_status": history_status,
        }
        _attach_action_trace(
            response_payload,
            request_id=request_id,
            raw_input=command.text,
            final_status="ok",
        )
        return response_payload

    except Exception as e:
        response_payload = {
            "intent": "error",
            "detected_intent": "error",
            "confidence": 0.0,
            "response": f"Sorry, I encountered an error: {str(e)}",
            "username": command.username,
            "plan": [],
            "used_agents": [],
            "agent_capabilities": [],
            "execution_mode": "error",
            "decision": {},
            "orchestration": {},
            "permission_action": None,
            "permission": {},
        }
        _attach_action_trace(
            response_payload,
            request_id=request_id,
            raw_input=command.text,
            final_status="error",
        )
        return response_payload


@app.post("/api/chat")
async def api_chat(payload: ChatApiRequest, request: Request):
    try:
        user = _current_user(request)
        session_id = _resolve_session_id(request)
        request_id = new_request_id("chat")

        def _json_response(content: dict[str, Any], *, status_code: int = 200) -> JSONResponse:
            response = JSONResponse(content=content, status_code=status_code, headers=_cors_headers())
            _attach_local_session_cookie(
                response,
                session_id=content.get("session_id") or session_id,
                user=user,
            )
            return response

        raw_msg = str(payload.message or "").strip()
        if not raw_msg:
            reply = "Please send a message so I can help."
            _log_chat_trace(
                raw_input="",
                intent="validation",
                agent="api_chat",
                provider=None,
                output=reply,
                execution_mode="validation_error",
                status="error",
                request_id=request_id,
            )
            error_payload = _attach_action_trace(
                {
                    "success": False,
                    "content": reply,
                    "provider": None,
                    "reply": reply,
                    "intent": "validation",
                    "agent_used": "api_chat",
                    "mode": payload.mode or "hybrid",
                    "status": "error",
                    "error": "No message provided",
                },
                request_id=request_id,
                raw_input="",
                final_status="error",
            )
            return _json_response(error_payload, status_code=400)

        print(f"[CHAT] Incoming message: {repr(raw_msg[:160])}")

        is_vision_request = extract_vision_payload(raw_msg) is not None
        if is_vision_request:
            vision_payload = _build_vision_chat_payload(
                raw_message=raw_msg,
                request_id=request_id,
                session_id=session_id,
            )
            vision_payload["history_status"] = _attempt_persist_chat_turn(
                {
                    "raw_message": "[image upload]",
                    "session_id": session_id,
                    "user": user,
                    "user_profile": dict(user or {}),
                    "requested_mode": payload.mode,
                },
                vision_payload["reply"],
                vision_payload["intent"],
                vision_payload.get("agent_used"),
                vision_payload.get("mode"),
            )
            _log_chat_trace(
                raw_input="[image upload]",
                intent="vision",
                agent="groq_vision",
                provider=vision_payload.get("provider"),
                output=vision_payload["reply"],
                execution_mode=vision_payload.get("execution_mode"),
                status=vision_payload.get("status"),
                request_id=request_id,
            )
            return _json_response(vision_payload)

        pollinations_prompt = _extract_pollinations_prompt(raw_msg)
        if pollinations_prompt and not _pollinations_api_key():
            return _json_response(
                _build_pollinations_unavailable_payload(
                    prompt=pollinations_prompt,
                    session_id=session_id,
                    request_id=request_id,
                    reason="not_configured",
                )
            )

        pollinations_bypass = _try_pollinations_image_bypass(raw_msg)
        if pollinations_bypass and pollinations_bypass.get("image_url"):
            bypass_payload = _build_pollinations_bypass_payload(
                image_url=pollinations_bypass["image_url"],
                session_id=session_id,
                request_id=request_id,
            )
            _attach_action_trace(
                bypass_payload,
                request_id=request_id,
                raw_input=raw_msg,
                final_status="ok",
            )
            return _json_response(bypass_payload)
        if pollinations_bypass:
            return _json_response(
                _build_pollinations_unavailable_payload(
                    prompt=pollinations_bypass.get("prompt") or raw_msg,
                    session_id=session_id,
                    request_id=request_id,
                    reason=pollinations_bypass.get("status") or "provider_failed",
                    error=pollinations_bypass.get("error"),
                )
            )

        if not is_vision_request and detect_image_generation_request(raw_msg):
            image_payload = _build_image_generation_chat_payload(
                raw_message=raw_msg,
                request_id=request_id,
                session_id=session_id,
            )
            image_payload["history_status"] = _attempt_persist_chat_turn(
                {
                    "raw_message": raw_msg,
                    "session_id": session_id,
                    "user": user,
                    "user_profile": dict(user or {}),
                },
                image_payload["reply"],
                image_payload["intent"],
                image_payload.get("agent_used"),
                image_payload.get("mode"),
            )
            _log_chat_trace(
                raw_input=raw_msg,
                intent="image_generation",
                agent="image_generation",
                provider=image_payload.get("provider"),
                output=image_payload["reply"],
                execution_mode=image_payload.get("execution_mode"),
                status=image_payload.get("status"),
                request_id=request_id,
            )
            return _json_response(image_payload)

        session_token = read_session_token(request) if user else None
        context = _prepare_chat_context(
            payload.message,
            payload.mode,
            session_id,
            user=user,
            confirmation_code=payload.confirmation_code,
            confirmed=payload.confirmed,
            pin=payload.pin,
            otp=payload.otp,
            otp_token=payload.otp_token,
            session_token=session_token,
        )
        if not user and _normalize_session_id(context.get("session_id")) == "default":
            context["session_id"] = _generate_local_session_id()

        if "clarification_reply" in context:
            clarification_payload = _build_chat_success_payload(
                reply=context["clarification_reply"],
                intent="document",
                agent_used="document_clarification",
                mode="clarification",
                provider="local",
            )
            clarification_payload["session_id"] = context.get("session_id", session_id)
            _log_chat_trace(
                raw_input=context["raw_message"],
                intent="document",
                agent="document_clarification",
                provider="local",
                output=clarification_payload["reply"],
                execution_mode="clarification",
                status=clarification_payload.get("status"),
                request_id=request_id,
            )
            _attach_action_trace(clarification_payload, context=context, request_id=request_id, raw_input=raw_msg, final_status="ok")
            return _json_response(clarification_payload)

        if _should_rate_limit_document_request(context):
            rate_limited = _consume_document_rate_limit(
                request=request,
                user=user,
                channel="chat_document",
                session_id=context.get("session_id"),
            )
            if rate_limited is not None:
                rate_limited["reply"] = rate_limited["error"]
                rate_limited["content"] = rate_limited["error"]
                rate_limited["session_id"] = context.get("session_id", session_id)
                _log_chat_trace(
                    raw_input=context["raw_message"],
                    intent="document",
                    agent="document_generator",
                    provider=None,
                    output=rate_limited["reply"],
                    execution_mode="rate_limited",
                    status=rate_limited.get("status"),
                    request_id=request_id,
                )
                _attach_action_trace(rate_limited, context=context, request_id=request_id, final_status="error")
                return _json_response(rate_limited, status_code=429)

        print(
            f"[CHAT] Intent: {context['detected_intent']!r}  "
            f"confidence={context['confidence']:.2f}  "
            f"permission={'ALLOWED' if context['permission'].get('success') else 'BLOCKED'}  "
            f"user={'auth' if user else 'public'}"
        )

        casual_payload = _build_casual_chat_payload(context)
        if casual_payload is not None:
            print(f"[CHAT] Path: casual_local shortcut  reply={repr(casual_payload['reply'][:80])}")
            casual_payload["history_status"] = _attempt_persist_chat_turn(
                context,
                casual_payload["reply"],
                casual_payload["intent"],
                casual_payload.get("agent_used"),
                casual_payload.get("mode"),
            )
            _log_chat_trace(
                raw_input=context["raw_message"],
                intent=casual_payload["intent"],
                agent=str(casual_payload.get("agent_used") or "general"),
                provider=casual_payload.get("provider"),
                output=casual_payload["reply"],
                execution_mode=casual_payload.get("execution_mode"),
                status=casual_payload.get("status"),
                request_id=request_id,
            )
            _attach_action_trace(casual_payload, context=context, request_id=request_id, final_status="ok")
            return _json_response(casual_payload)

        if not context["permission"].get("success", False):
            perm_reason = (context["permission"].get("permission") or {}).get("reason", "no reason")
            print(f"[CHAT] Path: permission_blocked  reason={perm_reason!r}")
            blocked_payload = _build_blocked_chat_payload(context)
            blocked_payload["history_status"] = _attempt_persist_chat_turn(
                context,
                blocked_payload["reply"],
                blocked_payload["intent"],
                blocked_payload.get("agent_used"),
                blocked_payload.get("mode"),
            )
            _log_chat_trace(
                raw_input=context["raw_message"],
                intent=blocked_payload["intent"],
                agent=str(blocked_payload.get("agent_used") or "policy"),
                provider=blocked_payload.get("provider"),
                output=blocked_payload["reply"],
                execution_mode=blocked_payload.get("execution_mode"),
                status=blocked_payload.get("status"),
                request_id=request_id,
            )
            _attach_action_trace(blocked_payload, context=context, request_id=request_id, final_status="blocked")
            return _json_response(blocked_payload)

        print(f"[CHAT] Path: pipeline  mode={payload.mode!r}")
        response_payload = _execute_chat_pipeline(context)
        response_payload["history_status"] = _attempt_persist_chat_turn(
            context,
            response_payload["reply"],
            response_payload["intent"],
            response_payload.get("agent_used"),
            response_payload.get("mode"),
        )
        print(
            f"[CHAT] Final response: agent={response_payload.get('agent_used')!r}  "
            f"provider={response_payload.get('provider')!r}  "
            f"degraded={response_payload.get('degraded')}  "
            f"reply={repr(str(response_payload.get('reply') or '')[:120])}"
        )
        _log_chat_trace(
            raw_input=context["raw_message"],
            intent=str(response_payload.get("intent") or context["detected_intent"] or "general"),
            agent=str(response_payload.get("agent_used") or "general"),
            provider=response_payload.get("provider"),
            output=str(response_payload.get("reply") or ""),
            execution_mode=response_payload.get("execution_mode"),
            status=response_payload.get("status"),
            request_id=request_id,
        )

        _attach_action_trace(response_payload, context=context, request_id=request_id)
        return _json_response(response_payload)
    except ValueError as error:
        print(f"[CHAT ERROR] Validation: {error}")
        reply = "I couldn't process that message cleanly. Please check the request and try again."
        request_id = locals().get("request_id") or new_request_id("chat")
        _log_chat_trace(
            raw_input=str(payload.message or ""),
            intent="validation",
            agent="api_chat",
            provider=None,
            output=reply,
            execution_mode="validation_error",
            status="error",
            request_id=request_id,
        )
        error_payload = _attach_action_trace(
            {
                "success": False,
                "content": reply,
                "provider": None,
                "reply": reply,
                "intent": "validation",
                "agent_used": "api_chat",
                "mode": payload.mode or "hybrid",
                "error": str(error),
                "status": "error",
            },
            request_id=request_id,
            raw_input=str(payload.message or ""),
            final_status="error",
        )
        return JSONResponse(
            status_code=400,
            content=error_payload,
            headers=_cors_headers(),
        )
    except Exception as error:
        print(f"[CHAT ERROR] Unhandled: {type(error).__name__}: {error}")
        reply = "I couldn't complete that request cleanly, but the chat path is still available. Please try again."
        request_id = locals().get("request_id") or new_request_id("chat")
        _log_chat_trace(
            raw_input=str(payload.message or ""),
            intent="error",
            agent="api_chat",
            provider=None,
            output=reply,
            execution_mode="server_error",
            status="error",
            request_id=request_id,
        )
        error_payload = _attach_action_trace(
            {
                "success": False,
                "content": reply,
                "provider": None,
                "reply": reply,
                "intent": "error",
                "agent_used": "api_chat",
                "mode": payload.mode or "hybrid",
                "error": str(error),
                "status": "error",
            },
            request_id=request_id,
            raw_input=str(payload.message or ""),
            final_status="error",
        )
        return JSONResponse(
            status_code=500,
            content=error_payload,
            headers=_cors_headers(),
        )


@app.post("/api/chat/file")
async def api_chat_file(
    request: Request,
    message: str = Form(""),
    file: UploadFile = File(...),
):
    try:
        user = _current_user(request)
        session_id = _resolve_session_id(request)
        request_id = new_request_id("chat-file")
        filename = Path(file.filename or "uploaded-file").name
        content_type = str(file.content_type or "").strip().lower()
        file_bytes = await file.read()
        if not file_bytes:
            return JSONResponse(
                status_code=400,
                content={"success": False, "status": "error", "error": "Uploaded file is empty."},
                headers=_cors_headers(),
            )

        def _json_response(content: dict[str, Any], *, status_code: int = 200) -> JSONResponse:
            response = JSONResponse(content=content, status_code=status_code, headers=_cors_headers())
            _attach_local_session_cookie(
                response,
                session_id=content.get("session_id") or session_id,
                user=user,
            )
            return response

        extension = Path(filename).suffix.lower()
        is_image = content_type.startswith("image/") or extension in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".tiff", ".tif"}
        prompt = str(message or "").strip()
        if is_image:
            mime_type = content_type if content_type.startswith("image/") else "image/png"
            data_url = f"data:{mime_type};base64,{base64.b64encode(file_bytes).decode('ascii')}"
            vision_prompt = prompt or "Describe this image clearly. Tell me what it is and any important details you can see."
            raw_msg = f"[VISION_PROMPT]{vision_prompt}[/VISION_PROMPT][VISION_URL]{data_url}[/VISION_URL]"
            payload = _build_vision_chat_payload(
                raw_message=raw_msg,
                request_id=request_id,
                session_id=session_id,
            )
            payload["uploaded_file"] = {
                "name": filename,
                "content_type": content_type,
                "size_bytes": len(file_bytes),
            }
            return _json_response(payload)

        extracted = extract_content(file_bytes, filename=filename)
        if not extracted.success or not extracted.text.strip():
            reply = (
                f"I received {filename}, but I could not read its contents. "
                f"{extracted.error or 'The file type may not be supported yet.'}"
            )
            payload = _build_chat_success_payload(
                reply=reply,
                intent="file_analysis",
                agent_used="file_reader",
                mode="file_error",
                success=False,
                provider="local",
                error=extracted.error,
                response_kind="file",
            )
            payload.update(
                {
                    "session_id": session_id,
                    "uploaded_file": {
                        "name": filename,
                        "content_type": content_type,
                        "size_bytes": len(file_bytes),
                    },
                }
            )
            _attach_action_trace(payload, request_id=request_id, raw_input=f"[file upload] {filename}", final_status="error")
            return _json_response(payload, status_code=400)

        prompt = prompt or "Tell me what this uploaded file is. Identify the file type and summarize the important content clearly."
        extracted_text = extracted.text.strip()
        if len(extracted_text) > 12000:
            extracted_text = extracted_text[:12000].rstrip() + "\n\n[File text truncated for chat context.]"
        raw_msg = (
            f"{prompt}\n\n"
            f"Uploaded file name: {filename}\n"
            f"Detected file type: {extracted.source_type}\n"
            f"Extraction mode: {extracted.extraction_mode or 'text'}\n\n"
            f"--- FILE CONTENT START ---\n{extracted_text}\n--- FILE CONTENT END ---"
        )
        provider_result = generate_with_best_provider(
            [
                {
                    "role": "system",
                    "content": (
                        "You are VORIS file analysis. Identify the uploaded file type, "
                        "explain what the file appears to contain, and answer the user's request. "
                        "Do not treat file extensions such as txt, csv, pdf, or docx as currencies."
                    ),
                },
                {"role": "user", "content": raw_msg},
            ],
            max_tokens=1200,
            temperature=0.2,
        )
        reply = clean_response(provider_result.get("text"))
        success = bool(provider_result.get("success") and reply)
        if not reply:
            preview = extracted_text[:900].strip()
            reply = (
                f"This is a {extracted.source_type.upper()} file named {filename}. "
                f"I extracted readable content from it. Preview: {preview}"
            )

        response_payload = _build_chat_success_payload(
            reply=reply,
            intent="file_analysis",
            agent_used="file_reader",
            mode="file_analysis",
            success=success,
            provider=provider_result.get("provider"),
            error=provider_result.get("error"),
            response_kind="file",
        )
        response_payload.update(
            {
                "session_id": session_id,
                "execution_mode": "file_analysis",
                "model": provider_result.get("model"),
                "providers_tried": provider_result.get("providers_tried", []),
                "degraded": not success,
                "permission": build_permission_response("general", confirmed=True),
            }
        )
        response_payload["uploaded_file"] = {
            "name": filename,
            "content_type": content_type,
            "size_bytes": len(file_bytes),
            "source_type": extracted.source_type,
            "extraction_mode": extracted.extraction_mode,
        }
        _attach_action_trace(response_payload, request_id=request_id, raw_input=f"[file upload] {filename}")
        return _json_response(response_payload)
    except Exception as error:
        print(f"[CHAT FILE ERROR] {type(error).__name__}: {error}")
        payload = _attach_action_trace(
            {
                "success": False,
                "content": "I could not process that uploaded file. Please try another image, PDF, DOCX, TXT, or CSV file.",
                "reply": "I could not process that uploaded file. Please try another image, PDF, DOCX, TXT, or CSV file.",
                "intent": "file_analysis",
                "agent_used": "file_reader",
                "mode": "file_error",
                "status": "error",
                "error": str(error),
            },
            request_id=locals().get("request_id") or new_request_id("chat-file"),
            raw_input="[file upload]",
            final_status="error",
        )
        return JSONResponse(status_code=500, content=payload, headers=_cors_headers())


@app.post("/api/chat/stream")
async def api_chat_stream(payload: ChatApiRequest, request: Request):
    """SSE wrapper around the trusted chat path.

    This prepares ChatGPT-style progressive rendering without depending on any
    private provider streaming internals. The existing /api/chat path remains
    the source of truth for metadata, document cards, action traces, and safety.
    """

    response = await api_chat(payload, request)
    response_payload, status_code, set_cookie = _json_response_payload(response)
    request_id = str(response_payload.get("request_id") or new_request_id("stream"))
    reply_text = str(response_payload.get("reply") or response_payload.get("content") or "").strip()

    async def _events():
        yield _sse_event(
            "start",
            {
                "request_id": request_id,
                "status": "started",
                "streaming": _should_stream_reply_payload(response_payload),
            },
        )
        if status_code >= 400:
            yield _sse_event(
                "error",
                {
                    "request_id": request_id,
                    "status_code": status_code,
                    "message": reply_text or response_payload.get("error") or "The chat request could not complete.",
                },
            )
        elif _should_stream_reply_payload(response_payload):
            for index, chunk in enumerate(_chunk_stream_text(reply_text), start=1):
                if await request.is_disconnected():
                    break
                yield _sse_event(
                    "chunk",
                    {
                        "request_id": request_id,
                        "index": index,
                        "text": chunk,
                    },
                )
                await asyncio.sleep(0.012)
        yield _sse_event("final", response_payload)

    stream_response = StreamingResponse(
        _events(),
        media_type="text/event-stream",
        headers={
            **_cors_headers(),
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
    if set_cookie:
        stream_response.headers["set-cookie"] = set_cookie
    return stream_response


@app.get("/api/image/status")
async def api_image_status():
    return JSONResponse(
        content={
            "success": True,
            "status": "ok",
            "image_generation": get_image_generation_status(),
        },
        headers=_cors_headers(),
    )


@app.post("/api/generate/image")
async def api_generate_image(payload: ImageGenerateRequest, request: Request):
    request_id = new_request_id("image")
    session_id = _resolve_session_id(request)
    pollinations_prompt = _extract_pollinations_prompt(payload.prompt) or str(payload.prompt or "").strip()
    if pollinations_prompt:
        if not _pollinations_api_key():
            return JSONResponse(
                content=_build_pollinations_unavailable_payload(
                    prompt=pollinations_prompt,
                    session_id=session_id,
                    request_id=request_id,
                    reason="not_configured",
                ),
                headers=_cors_headers(),
            )
        pollinations_result = _try_pollinations_image_bypass(f"generate image of {pollinations_prompt}")
        if pollinations_result and pollinations_result.get("image_url"):
            response_payload = _build_pollinations_bypass_payload(
                image_url=pollinations_result["image_url"],
                session_id=session_id,
                request_id=request_id,
            )
            _attach_action_trace(
                response_payload,
                request_id=request_id,
                raw_input=payload.prompt,
                final_status="ok",
            )
            return JSONResponse(content=response_payload, headers=_cors_headers())
        if pollinations_result:
            return JSONResponse(
                content=_build_pollinations_unavailable_payload(
                    prompt=pollinations_result.get("prompt") or pollinations_prompt,
                    session_id=session_id,
                    request_id=request_id,
                    reason=pollinations_result.get("status") or "provider_failed",
                    error=pollinations_result.get("error"),
                ),
                headers=_cors_headers(),
            )

    result = generate_image(payload.prompt, style=payload.style, size=payload.size)
    response_payload = {
        "success": bool(result.get("success")),
        "kind": "image_generation",
        "status": result.get("status"),
        "reply": result.get("message"),
        "content": result.get("message"),
        "image_generation": result,
        "image_provider_status": get_image_generation_status(),
        "provider": result.get("provider"),
        "error": result.get("error"),
        "execution_mode": "image_generation" if result.get("success") else "image_generation_unavailable",
        "permission": build_permission_response("image_generation", confirmed=True),
    }
    _attach_action_trace(
        response_payload,
        request_id=request_id,
        raw_input=payload.prompt,
        final_status="ok" if result.get("success") else "degraded",
    )
    return JSONResponse(content=response_payload, headers=_cors_headers())


@app.post("/api/generate/document")
async def api_generate_document(payload: DocumentGenerateRequest, request: Request):
    try:
        request_id = new_request_id("document")
        user = _current_user(request)
        owner_session_id = _ensure_document_session_id(request)
        rate_limited = _consume_document_rate_limit(
            request=request,
            user=user,
            channel="api_document",
            session_id=owner_session_id,
        )
        if rate_limited is not None:
            response = JSONResponse(status_code=429, content=rate_limited, headers=_cors_headers())
            _attach_local_session_cookie(response, session_id=owner_session_id, user=user)
            return response

        cleanup_generated_documents()
        requested_formats = normalize_document_formats(payload.formats or [payload.format])
        generated = generate_document(
            payload.type,
            payload.topic,
            normalize_document_format(payload.format),
            formats=requested_formats,
            page_target=payload.page_target,
            style=normalize_document_style(payload.style),
            include_references=payload.include_references,
            citation_style=normalize_citation_style(payload.citation_style),
        )
        generated = secure_generated_document_access(
            generated,
            owner_session_id=owner_session_id,
            owner_user_id=user.get("id") if user else None,
        )
        response_payload = {
            "success": True,
            "kind": "document_delivery",
            "download_url": generated["download_url"],
            "file_name": generated["file_name"],
            "document_type": generated["document_type"],
            "format": generated["format"],
            "page_target": generated.get("page_target"),
            "topic": generated["topic"],
            "provider": generated.get("provider"),
            "source": generated.get("source"),
            "title": generated.get("title"),
            "subtitle": generated.get("subtitle"),
            "preview_text": generated.get("preview_text"),
            "files": generated.get("files") or [],
            "requested_formats": generated.get("requested_formats") or [],
            "style": generated.get("style"),
            "include_references": generated.get("include_references"),
            "citation_style": generated.get("citation_style"),
            "access_scope": generated.get("access_scope"),
            "available_formats": generated.get("available_formats") or [],
            "format_links": generated.get("format_links") or {},
            "alternate_format_links": generated.get("alternate_format_links") or {},
            "document_delivery": generated.get("document_delivery"),
            "reply": generated.get("message"),
            "content": generated.get("message"),
            "execution_mode": "document_generation",
            "permission": build_permission_response("document_generation", confirmed=True),
            "status": "ok",
        }
        _attach_action_trace(
            response_payload,
            request_id=request_id,
            raw_input=f"{payload.type} on {payload.topic}",
            final_status="ok",
        )
        response = JSONResponse(
            content=response_payload,
            headers=_cors_headers(),
        )
        _attach_local_session_cookie(response, session_id=owner_session_id, user=user)
        return response
    except ValueError as error:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": str(error), "status": "error"},
            headers=_cors_headers(),
        )
    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(error), "status": "error"},
            headers=_cors_headers(),
        )


def _build_transform_response(generated: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "success": True,
        "kind": "document_delivery",
        "download_url": generated["download_url"],
        "file_name": generated["file_name"],
        "document_type": generated["document_type"],
        "format": generated["format"],
        "page_target": generated.get("page_target"),
        "topic": generated["topic"],
        "provider": generated.get("provider"),
        "source": generated.get("source"),
        "title": generated.get("title"),
        "subtitle": generated.get("subtitle"),
        "preview_text": generated.get("preview_text"),
        "files": generated.get("files") or [],
        "requested_formats": generated.get("requested_formats") or [],
        "style": generated.get("style"),
        "include_references": generated.get("include_references"),
        "citation_style": generated.get("citation_style"),
        "access_scope": generated.get("access_scope"),
        "available_formats": generated.get("available_formats") or [],
        "format_links": generated.get("format_links") or {},
        "alternate_format_links": generated.get("alternate_format_links") or {},
        "document_delivery": generated.get("document_delivery"),
        "reply": generated.get("message"),
        "content": generated.get("message"),
        "execution_mode": "document_transformation",
        "permission": build_permission_response("document_generation", confirmed=True),
        "status": "ok",
    }
    return _attach_action_trace(
        payload,
        request_id=new_request_id("transform"),
        raw_input=f"transform {generated.get('document_type') or 'document'} on {generated.get('topic') or ''}",
        final_status="ok",
    )


@app.post("/api/transform")
async def api_transform(payload: TransformRequest, request: Request):
    """Transform pasted text or a YouTube URL into a structured document."""
    try:
        user = _current_user(request)
        owner_session_id = _ensure_document_session_id(request)
        rate_limited = _consume_document_rate_limit(
            request=request,
            user=user,
            channel="api_document",
            session_id=owner_session_id,
        )
        if rate_limited is not None:
            response = JSONResponse(status_code=429, content=rate_limited, headers=_cors_headers())
            _attach_local_session_cookie(response, session_id=owner_session_id, user=user)
            return response

        cleanup_generated_documents()
        extracted = extract_content(payload.content.strip())
        if not extracted.success or not extracted.text.strip():
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": extracted.error or "Could not extract content.", "status": "error"},
                headers=_cors_headers(),
            )

        topic = (payload.topic or "").strip() or extracted.source_label or "Source Material"
        doc_type = str(payload.document_type or "notes").strip().lower()
        if doc_type not in {"notes", "assignment"}:
            doc_type = "notes"

        requested_formats = normalize_document_formats(payload.formats or [payload.format])
        normalized_style = normalize_document_style(payload.style)
        normalized_citation = normalize_citation_style(payload.citation_style)

        transformation_payload = generate_transformation_content_payload(
            extracted.text,
            doc_type,
            topic,
            page_target=payload.page_target,
            style=normalized_style,
            include_references=payload.include_references,
            citation_style=normalized_citation,
        )

        structured_content = transformation_payload.get("content") or extracted.text

        generated = generate_document(
            doc_type,
            topic,
            normalize_document_format(payload.format),
            formats=requested_formats,
            page_target=payload.page_target,
            style=normalized_style,
            include_references=payload.include_references,
            citation_style=normalized_citation,
            prebuilt_content=structured_content,
        )
        generated = secure_generated_document_access(
            generated,
            owner_session_id=owner_session_id,
            owner_user_id=user.get("id") if user else None,
        )
        response = JSONResponse(content=_build_transform_response(generated), headers=_cors_headers())
        _attach_local_session_cookie(response, session_id=owner_session_id, user=user)
        return response

    except ValueError as error:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": str(error), "status": "error"},
            headers=_cors_headers(),
        )
    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(error), "status": "error"},
            headers=_cors_headers(),
        )


@app.post("/api/transform/file")
async def api_transform_file(
    request: Request,
    file: UploadFile = File(...),
    document_type: str = Form("notes"),
    topic: str = Form(""),
    format: str = Form("txt"),
    formats: Optional[str] = Form(None),
    page_target: Optional[int] = Form(None),
    style: Optional[str] = Form(None),
    include_references: bool = Form(False),
    citation_style: Optional[str] = Form(None),
):
    """Transform an uploaded file (.txt, .pdf, .docx, or image) into a structured document."""
    try:
        user = _current_user(request)
        owner_session_id = _ensure_document_session_id(request)
        rate_limited = _consume_document_rate_limit(
            request=request,
            user=user,
            channel="api_document",
            session_id=owner_session_id,
        )
        if rate_limited is not None:
            response = JSONResponse(status_code=429, content=rate_limited, headers=_cors_headers())
            _attach_local_session_cookie(response, session_id=owner_session_id, user=user)
            return response

        cleanup_generated_documents()
        file_bytes = await file.read()
        filename = file.filename or ""

        extracted = extract_content(file_bytes, filename=filename)
        if not extracted.success or not extracted.text.strip():
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": extracted.error or "Could not extract content from file.", "status": "error"},
                headers=_cors_headers(),
            )

        resolved_topic = topic.strip() or extracted.source_label or "Source Material"
        doc_type = str(document_type or "notes").strip().lower()
        if doc_type not in {"notes", "assignment"}:
            doc_type = "notes"

        raw_formats = [f.strip() for f in (formats or "").split(",") if f.strip()] if formats else [format]
        requested_formats = normalize_document_formats(raw_formats)
        normalized_style = normalize_document_style(style)
        normalized_citation = normalize_citation_style(citation_style)

        transformation_payload = generate_transformation_content_payload(
            extracted.text,
            doc_type,
            resolved_topic,
            page_target=page_target,
            style=normalized_style,
            include_references=include_references,
            citation_style=normalized_citation,
        )

        structured_content = transformation_payload.get("content") or extracted.text

        generated = generate_document(
            doc_type,
            resolved_topic,
            normalize_document_format(format),
            formats=requested_formats,
            page_target=page_target,
            style=normalized_style,
            include_references=include_references,
            citation_style=normalized_citation,
            prebuilt_content=structured_content,
        )
        generated = secure_generated_document_access(
            generated,
            owner_session_id=owner_session_id,
            owner_user_id=user.get("id") if user else None,
        )

        response_payload = _build_transform_response(generated)
        response_payload["source_file"] = filename
        response_payload["source_type"] = extracted.source_type
        response = JSONResponse(content=response_payload, headers=_cors_headers())
        _attach_local_session_cookie(response, session_id=owner_session_id, user=user)
        return response

    except ValueError as error:
        return JSONResponse(
            status_code=400,
            content={"success": False, "error": str(error), "status": "error"},
            headers=_cors_headers(),
        )
    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={"success": False, "error": str(error), "status": "error"},
            headers=_cors_headers(),
        )


@app.get("/downloads/{file_name}")
async def download_generated_document(file_name: str, request: Request):
    user = _current_user(request)
    access = resolve_generated_download_access(
        file_name,
        access_token=request.query_params.get("access"),
        session_id=_resolve_session_id(request),
        user_id=user.get("id") if user else None,
    )
    if not access.get("allowed"):
        return JSONResponse(
            status_code=403,
            content={
                "success": False,
                "status": access.get("status") or "forbidden",
                "error": access.get("reason") or "Download access denied.",
            },
            headers=_cors_headers(),
        )
    response = FileResponse(access["file_path"], filename=access["file_name"])
    _attach_local_session_cookie(response, session_id=_resolve_session_id(request), user=user)
    return response


@app.get("/generated-images/{file_name}")
async def serve_generated_image(file_name: str):
    safe_name = Path(file_name or "").name
    if safe_name != file_name or not safe_name.startswith("pollinations-"):
        raise HTTPException(status_code=404, detail="Image not found.")
    image_path = GENERATED_IMAGE_DIR / safe_name
    if not image_path.is_file():
        raise HTTPException(status_code=404, detail="Image not found.")
    media_type = "image/jpeg" if image_path.suffix.lower() in {".jpg", ".jpeg"} else "image/webp" if image_path.suffix.lower() == ".webp" else "image/png"
    return FileResponse(image_path, media_type=media_type)


@app.get("/api/media/status")
async def api_media_status():
    """Backend + weight availability, including what is missing and how to get it."""
    return JSONResponse(content={"success": True, "status": "ok",
                                 "media_generation": media_generation.get_media_generation_status()})


@app.get("/api/media/job")
async def api_media_job(job_id: str = ""):
    """Progress for one generation.

    Polling rather than a push: this codebase has no WebSocket, and adding one
    purely for progress would be new plumbing for a job that finishes in
    minutes. The job id is returned by media_generation.generate_image().

    A query parameter rather than a path segment so the route is an exact
    string in PUBLIC_PATHS; that set is matched by equality, and a path
    parameter would never match it.
    """
    job = media_generation.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found.")
    return JSONResponse(content={"success": True, "status": "ok", "job": job})


@app.get("/generated-media/{file_name}")
async def serve_generated_media(file_name: str):
    safe_name = Path(file_name or "").name
    if safe_name != file_name or not safe_name.startswith("img-"):
        raise HTTPException(status_code=404, detail="Media not found.")
    media_path = media_generation.GENERATED_MEDIA_DIR / safe_name
    if not media_path.is_file():
        raise HTTPException(status_code=404, detail="Media not found.")
    return FileResponse(media_path, media_type="image/png")


@app.get("/history")
async def history(request: Request, session_id: str = "default"):
    user = _current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required.")
    normalized_session = _normalize_session_id(session_id)
    if normalized_session != _resolve_session_id(request) and not is_admin_user(user):
        raise HTTPException(status_code=403, detail="History access denied.")
    return get_history(normalized_session)


@app.get("/api/history")
async def api_history(request: Request, session_id: str = "default", limit: int = 50):
    try:
        user = _current_user(request)
        if not user:
            return JSONResponse(
                status_code=401,
                content={"error": "Authentication required.", "status": "error"},
                headers=_cors_headers(),
            )
        normalized_session = _normalize_session_id(session_id)
        if normalized_session != _resolve_session_id(request) and not is_admin_user(user):
            return JSONResponse(
                status_code=403,
                content={"error": "History access denied.", "status": "error"},
                headers=_cors_headers(),
            )
        messages = get_history(normalized_session, limit=limit)
        return {
            "session_id": normalized_session,
            "messages": messages,
            "count": len(messages),
            "status": "ok",
        }
    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={"error": str(error), "status": "error"},
            headers=_cors_headers(),
        )


@app.delete("/api/history")
async def api_history_delete(request: Request, session_id: str = "default"):
    try:
        user = _current_user(request)
        if not user:
            return JSONResponse(
                status_code=401,
                content={"error": "Authentication required.", "status": "error"},
                headers=_cors_headers(),
            )
        normalized_session = _normalize_session_id(session_id)
        if normalized_session != _resolve_session_id(request) and not is_admin_user(user):
            return JSONResponse(
                status_code=403,
                content={"error": "History access denied.", "status": "error"},
                headers=_cors_headers(),
            )
        deleted = clear_history(normalized_session)
        clear_session_context(normalized_session)
        return {
            "session_id": normalized_session,
            "deleted": deleted,
            "status": "ok",
        }
    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={"error": str(error), "status": "error"},
            headers=_cors_headers(),
        )


@app.get("/api/sessions")
async def api_sessions(request: Request):
    try:
        user = _current_user(request)
        if not user:
            return JSONResponse(
                status_code=401,
                content={"error": "Authentication required.", "status": "error"},
                headers=_cors_headers(),
            )
        sessions = get_all_sessions()
        if not is_admin_user(user):
            current_session = _resolve_session_id(request)
            sessions = [item for item in sessions if item.get("session_id") == current_session]
        return {
            "sessions": sessions,
            "status": "ok",
        }
    except Exception as error:
        return JSONResponse(
            status_code=500,
            content={"error": str(error), "status": "error"},
            headers=_cors_headers(),
        )


@app.get("/api/desktop/apps")
async def api_desktop_apps():
    return JSONResponse(
        content={
            "success": True,
            "status": "ok",
            "apps": get_supported_desktop_apps(),
        },
        headers=_cors_headers(),
    )


@app.post("/api/os-automation/stop")
async def api_os_automation_stop():
    result = request_os_automation_stop()
    return JSONResponse(content=result, headers=_cors_headers())


@app.get("/api/admin/users")
async def admin_list_users(request: Request):
    _require_admin_user(request)
    whitelist_users = access_controller.list_users()
    registered_users = load_user_profile()
    return {
        "status": "ok",
        "users": whitelist_users,
        "profile_defaults": registered_users,
    }


@app.post("/api/admin/invite")
async def admin_invite_user(payload: InviteRequest, request: Request):
    admin_user = _require_admin_user(request)
    invited = access_controller.invite_user(payload.email, invited_by_admin=admin_user.get("username", "admin"))
    return {"status": "ok", "user": invited, "message": "User invited."}


@app.post("/api/admin/revoke")
async def admin_revoke_user(payload: RevokeAccessRequest, request: Request):
    _require_admin_user(request)
    revoked = access_controller.revoke_access(payload.email)
    if not revoked:
        raise HTTPException(status_code=404, detail="User not found in whitelist.")
    return {"status": "ok", "message": "Access revoked."}


@app.get("/api/admin/rate-limits")
async def admin_list_rate_limits(request: Request):
    _require_admin_user(request)
    return {"status": "ok", "items": access_controller.list_rate_limits()}


@app.post("/api/admin/unblock")
async def admin_unblock_ip(payload: UnblockIpRequest, request: Request):
    _require_admin_user(request)
    unblocked = access_controller.unblock_ip(payload.ip_address)
    if not unblocked:
        raise HTTPException(status_code=404, detail="IP address not found.")
    return {"status": "ok", "message": "IP unblocked."}


@app.get("/api/settings/profile")
async def get_user_profile_settings(request: Request):
    user = _require_authenticated_user(request)
    profile = load_user_profile()
    profile["username"] = user.get("username", "")
    profile["name"] = user.get("name", "")
    profile["preferred_name"] = user.get("preferred_name", "") or user.get("name", "")
    profile["title"] = user.get("title", profile.get("title", "sir"))
    return {"status": "ok", "profile": profile, "user": user}


@app.patch("/api/settings/profile")
async def update_user_profile_settings(payload: UserProfileUpdateRequest, request: Request):
    _require_authenticated_user(request)
    profile = load_user_profile()
    updates = {
        key: value
        for key, value in payload.model_dump(exclude_none=True).items()
        if key not in {"username", "name", "email", "preferred_name", "title"}
    }
    profile.update(updates)
    save_user_profile(profile)
    update_voice_preferences(
        persona=profile.get("voice_profile"),
        voice_gender=profile.get("voice_gender"),
        rate=profile.get("voice_rate"),
        volume=profile.get("voice_volume"),
        language=profile.get("language"),
    )
    return {"status": "ok", "profile": load_user_profile()}


@app.get("/api/confirmation-code/status")
async def confirmation_code_status(request: Request):
    user = _require_authenticated_user(request)
    return {
        "status": "ok",
        "configured": confirmation_system.code_exists(user.get("id", "")),
        "critical_actions": [
            "Deleting files or data",
            "Sending emails or messages",
            "Making purchases",
            "Changing security settings",
            "Accessing locked chats",
            "Any critical action requested through agents",
        ],
    }


@app.post("/api/confirmation-code/set")
async def set_confirmation_code_endpoint(payload: ConfirmationCodeSetRequest, request: Request):
    user = _require_authenticated_user(request)
    if payload.code != payload.confirm_code:
        raise HTTPException(status_code=400, detail="Confirmation codes do not match.")
    if not confirmation_system.set_confirmation_code(user.get("id", ""), payload.code):
        raise HTTPException(status_code=400, detail="Confirmation code must be at least 4 characters.")
    return {"status": "ok", "message": "Confirmation code saved."}


@app.post("/api/confirmation-code/change")
async def change_confirmation_code_endpoint(payload: ConfirmationCodeChangeRequest, request: Request):
    user = _require_authenticated_user(request)
    if payload.new_code != payload.confirm_code:
        raise HTTPException(status_code=400, detail="New confirmation codes do not match.")
    if not confirmation_system.change_code(user.get("id", ""), payload.old_code, payload.new_code):
        raise HTTPException(status_code=400, detail="Confirmation code could not be changed.")
    return {"status": "ok", "message": "Confirmation code updated."}


@app.get("/api/user/{username}")
async def get_user_info(username: str):
    user = get_user(username)
    if user:
        return {"success": True, "user": user}
    raise HTTPException(status_code=404, detail="User not found")


@app.get("/api/memory/insights")
async def get_memory_insights(username: str = "guest"):
    user = get_user(username) or {}
    explicit_memory = _read_json_object(USER_MEMORY_FILE)
    learning = _read_json_object(LEARNING_FILE)

    user_profile = learning.get("user_profile", {})
    preferences = user_profile.get("preferences") or learning.get("user_preferences") or {}
    interests = user_profile.get("interests") or []
    learned_facts = learning.get("learned_facts") or []
    topic_frequency = learning.get("topic_frequency") or learning.get("frequent_topics") or {}
    top_intents = sorted(topic_frequency.items(), key=lambda item: item[1], reverse=True)[:6]

    remembered_name = _normalize_name(
        user.get("name"),
        explicit_memory.get("user_name"),
        user_profile.get("name"),
    )
    profile_name = remembered_name or "Guest"

    return {
        "mode": "hybrid",
        "remembered_name": profile_name,
        "greeting_preview": _build_personalized_greeting(remembered_name),
        "profile": {
            "name": profile_name,
            "plan": user.get("plan", "free"),
            "created": user.get("created"),
            "city": explicit_memory.get("user_city"),
            "age": explicit_memory.get("user_age"),
        },
        "preferences": preferences,
        "interests": interests,
        "learned_facts": learned_facts,
        "top_intents": [
            {"intent": intent, "count": count}
            for intent, count in top_intents
        ],
        "insights": [
            f"Top intent right now is {top_intents[0][0]}." if top_intents else "VORIS is still learning your recurring intent patterns.",
            "Stored facts come from explicit memory and interaction learning.",
            "Preferences are limited until more real UI controls are connected.",
        ],
        "sources": {
            "explicit_memory": str(USER_MEMORY_FILE.relative_to(PROJECT_ROOT)),
            "learning": str(LEARNING_FILE.relative_to(PROJECT_ROOT)),
        },
    }


@app.get("/api/intelligence/insights")
async def get_intelligence_insights():
    improvement = _read_json_object(IMPROVEMENT_FILE)
    permissions = _read_json_object(PERMISSIONS_FILE)
    voice = _read_json_object(VOICE_SETTINGS_FILE)

    failures = improvement.get("failures") or []
    low_confidence = improvement.get("low_confidence_commands") or []
    suggestions = improvement.get("improvement_suggestions") or []

    return {
        "mode": "hybrid",
        "reasoning_status": "available",
        "low_confidence_count": len(low_confidence),
        "failure_count": len(failures),
        "recent_low_confidence": low_confidence[-6:],
        "recent_failures": failures[-6:],
        "improvement_suggestions": suggestions[-6:],
        "permissions": permissions,
        "voice": voice,
        "sources": {
            "improvement_log": str(IMPROVEMENT_FILE.relative_to(PROJECT_ROOT)),
            "permissions": str(PERMISSIONS_FILE.relative_to(PROJECT_ROOT)),
            "voice": str(VOICE_SETTINGS_FILE.relative_to(PROJECT_ROOT)),
        },
    }


@app.get("/api/tasks")
async def get_tasks():
    tasks = _read_json_list(TASKS_FILE)
    tasks.sort(key=lambda item: (item.get("status") == "completed", -int(item.get("id", 0))))
    return {
        "items": tasks,
        "summary": _task_summary(tasks),
        "mode": "real",
        "source": str(TASKS_FILE.relative_to(PROJECT_ROOT)),
    }


@app.post("/api/tasks")
async def create_task(task: TaskCreate):
    text = task.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Task text is required")

    tasks = _read_json_list(TASKS_FILE)
    item = {
        "id": _next_id(tasks),
        "task": text,
        "priority": (task.priority or "medium").strip().lower() or "medium",
        "due_date": task.due_date.strip() if task.due_date else None,
        "status": "pending",
        "created": _now_string(),
    }
    tasks.append(item)
    _write_json_list(TASKS_FILE, tasks)
    return {
        "success": True,
        "item": item,
        "summary": _task_summary(tasks),
    }


@app.patch("/api/tasks/{task_id}")
async def update_task(task_id: int, task: TaskUpdate):
    tasks = _read_json_list(TASKS_FILE)
    item = next((entry for entry in tasks if int(entry.get("id", 0)) == task_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if task.text is not None:
        text = task.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="Task text is required")
        item["task"] = text

    if task.priority is not None:
        item["priority"] = task.priority.strip().lower() or "medium"

    if task.due_date is not None:
        item["due_date"] = task.due_date.strip() or None

    if task.done is not None:
        if task.done:
            item["status"] = "completed"
            item["completed_at"] = _now_string()
        else:
            item["status"] = "pending"
            item.pop("completed_at", None)

    _write_json_list(TASKS_FILE, tasks)
    return {
        "success": True,
        "item": item,
        "summary": _task_summary(tasks),
    }


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: int):
    tasks = _read_json_list(TASKS_FILE)
    updated = [entry for entry in tasks if int(entry.get("id", 0)) != task_id]
    if len(updated) == len(tasks):
        raise HTTPException(status_code=404, detail="Task not found")
    _write_json_list(TASKS_FILE, updated)
    return {
        "success": True,
        "summary": _task_summary(updated),
    }


@app.get("/api/reminders")
async def get_reminders():
    reminders = _read_json_list(REMINDERS_FILE)
    reminders.sort(key=lambda item: (item.get("status") == "completed", -int(item.get("id", 0))))
    return {
        "items": reminders,
        "summary": _reminder_summary(reminders),
        "mode": "real",
        "source": str(REMINDERS_FILE.relative_to(PROJECT_ROOT)),
    }


@app.post("/api/reminders")
async def create_reminder(reminder: ReminderCreate):
    text = reminder.text.strip()
    if not text:
        raise HTTPException(status_code=400, detail="Reminder text is required")

    reminders = _read_json_list(REMINDERS_FILE)
    item = {
        "id": _next_id(reminders),
        "text": text,
        "time": reminder.time.strip() if reminder.time else None,
        "date": reminder.date.strip() if reminder.date else None,
        "created": _now_string(),
        "status": "active",
        "completed_at": None,
    }
    reminders.append(item)
    _write_json_list(REMINDERS_FILE, reminders)
    return {
        "success": True,
        "item": item,
        "summary": _reminder_summary(reminders),
    }


@app.patch("/api/reminders/{reminder_id}")
async def update_reminder(reminder_id: int, reminder: ReminderUpdate):
    reminders = _read_json_list(REMINDERS_FILE)
    item = next((entry for entry in reminders if int(entry.get("id", 0)) == reminder_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="Reminder not found")

    if reminder.text is not None:
        text = reminder.text.strip()
        if not text:
            raise HTTPException(status_code=400, detail="Reminder text is required")
        item["text"] = text

    if reminder.date is not None:
        item["date"] = reminder.date.strip() or None

    if reminder.time is not None:
        item["time"] = reminder.time.strip() or None

    if reminder.status is not None:
        status = reminder.status.strip().lower()
        if status not in {"active", "completed"}:
            raise HTTPException(status_code=400, detail="Reminder status must be active or completed")
        item["status"] = status
        item["completed_at"] = _now_string() if status == "completed" else None

    _write_json_list(REMINDERS_FILE, reminders)
    return {
        "success": True,
        "item": item,
        "summary": _reminder_summary(reminders),
    }


@app.delete("/api/reminders/{reminder_id}")
async def delete_reminder(reminder_id: int):
    reminders = _read_json_list(REMINDERS_FILE)
    updated = [entry for entry in reminders if int(entry.get("id", 0)) != reminder_id]
    if len(updated) == len(reminders):
        raise HTTPException(status_code=404, detail="Reminder not found")
    _write_json_list(REMINDERS_FILE, updated)
    return {
        "success": True,
        "summary": _reminder_summary(updated),
    }


@app.get("/api/system/status")
async def system_status(request: Request):
    user = _require_authenticated_user(request)
    summary = get_agent_summary()
    memory_status = vector_memory.get_status()
    memory_connected = memory_status["vector_store_ready"]
    memory_health = "connected" if memory_connected else "degraded"
    memory_mode = "real" if memory_connected else "fallback"
    provider_snapshot = _provider_health_snapshot(force=False)
    provider_summary = {
        "routing_order": provider_snapshot.get("routing_order", []),
        "healthy": provider_snapshot.get("healthy", []),
        "configured": provider_snapshot.get("configured", []),
        "items": provider_snapshot.get("items", []),
        "providers": provider_snapshot.get("providers", {}),
        "assistant_runtime": provider_snapshot.get("assistant_runtime", {}),
    }
    assistant_runtime = provider_snapshot.get("assistant_runtime") or {}
    primary_provider = assistant_runtime.get("preferred_provider")
    active_provider = assistant_runtime.get("active_provider")
    displayed_provider = active_provider or primary_provider
    displayed_model = assistant_runtime.get("active_model") or next(
        (item.get("model") for item in provider_snapshot.get("items", []) if item.get("provider") == displayed_provider),
        None,
    )
    profile = load_user_profile()
    voice_status = get_voice_status()
    return {
        "status": "online",
        "version": "1.0.0",
        "model": displayed_model or MODEL_NAME,
        "primary_provider": primary_provider,
        "active_provider": active_provider,
        "orchestrator": "rule_based_available",
        "reasoning": "hybrid_available",
        "memory": memory_health,
        "planner": "hybrid_available",
        "agents": summary,
        "capability_summary": summary.get("capability_modes", {}),
        "brain_capabilities": summarize_capabilities(),
        "memory_stats": get_memory_stats(),
        "memory_backend": memory_status,
        "providers": provider_summary,
        "assistant_runtime": assistant_runtime,
        "truth_notes": {
            "agents": "Agent listings include real, hybrid, and placeholder entries. Capability mode is the source of truth for how live each agent really is.",
            "providers": "Provider health reflects the latest runtime snapshot. Live requests can still degrade when a configured provider is rate-limited or unavailable.",
            "voice": "Browser voice is real, but continuous ambient wake is not guaranteed. Treat wake mode as beta single-phrase listening while the page is open.",
        },
        "security": {
            "pin": get_pin_status(),
            "auth": {"authenticated": True, "user": user},
            "confirmation_code": confirmation_system.code_exists(user.get("id", "")),
            "whitelist_count": len(access_controller.list_users()),
        },
        "profile": profile,
        "subsystems": {
            "orchestrator": {"status": "available", "mode": "real", "source": "rule_based"},
            "reasoning": {"status": "available", "mode": "hybrid"},
            "planner": {"status": "available", "mode": "hybrid"},
            "voice": {
                "status": "available" if voice_status["settings"]["enabled"] else "standby",
                "mode": "browser_push_to_talk_beta",
                "summary": "Browser voice is available, but continuous ambient wake is not guaranteed.",
            },
            "providers": {
                "status": assistant_runtime.get("status") or ("healthy" if provider_summary["healthy"] else "degraded"),
                "mode": "real" if assistant_runtime.get("active_provider") else "hybrid",
                "available": provider_summary["healthy"],
                "routing_order": provider_summary["routing_order"],
                "summary": assistant_runtime.get("message") or "Provider routing data is not available yet.",
                "truth_note": "Healthy means the latest provider snapshot looked usable. Live requests can still degrade on rate limits or upstream failures.",
                "active_provider": assistant_runtime.get("active_provider"),
            },
            "memory": {
                "status": memory_health,
                "mode": memory_mode,
                "vector_store_ready": memory_connected,
                "backend": memory_status["backend"],
                "last_error": memory_status["last_error"],
            },
        },
        "implementation_doctrine": {
            "capability_labels": list(CAPABILITY_LABELS),
            "hybrid_order": list(HYBRID_IMPLEMENTATION_ORDER),
            "implementation_priority": list(CAPABILITY_LABELS),
        },
    }


@app.get("/api/agents")
async def get_agents():
    return {
        # Placeholder agents are quarantined under agents/experimental and are
        # excluded from the catalog so the UI only advertises real/hybrid agents.
        "agents": list_agents(include_placeholders=False),
        "generated_agents": list_generated_agent_cards(),
        "providers": summarize_provider_statuses(fresh=False),
        "summary": get_agent_summary(),
        "truth_note": "This registry includes real, hybrid, and placeholder entries. Use capability_mode to judge how live each agent actually is.",
        "doctrine": {
            "capability_labels": list(CAPABILITY_LABELS),
            "hybrid_order": list(HYBRID_IMPLEMENTATION_ORDER),
            "implementation_priority": list(CAPABILITY_LABELS),
        },
    }


@app.get("/api/capabilities")
async def get_capabilities():
    return {
        "items": list_capabilities(),
        "summary": summarize_capabilities(),
    }


@app.get("/api/providers")
async def get_provider_status(request: Request):
    snapshot = _provider_health_snapshot(force=_refresh_requested(request))
    return {
        "success": True,
        "status": "ok",
        "default_provider": snapshot.get("routing_order", [None])[0],
        "routing_order": snapshot.get("routing_order", []),
        "available": snapshot.get("healthy", []),
        "healthy": snapshot.get("healthy", []),
        "configured": snapshot.get("configured", []),
        "verified": [item.get("provider") for item in snapshot.get("items", []) if item.get("verified")],
        "items": snapshot.get("items", []),
        "providers": snapshot.get("providers", {}),
        "checked_at": snapshot.get("checked_at"),
        "assistant_runtime": snapshot.get("assistant_runtime", {}),
        "truth_note": "Provider health reflects the latest runtime snapshot. A configured provider can still degrade or rate-limit live requests.",
    }


@app.get("/api/telemetry/last")
async def get_last_request_telemetry():
    return {
        "status": "ok",
        "telemetry": get_last_telemetry(),
    }


@app.get("/api/telemetry/providers")
async def get_provider_health(request: Request):
    snapshot = _provider_health_snapshot(force=_refresh_requested(request))
    return {
        "status": "ok",
        "checked_at": snapshot.get("checked_at"),
        "items": snapshot.get("items", []),
        "providers": snapshot.get("providers", {}),
        "routing_order": snapshot.get("routing_order", []),
        "healthy": snapshot.get("healthy", []),
        "configured": snapshot.get("configured", []),
        "assistant_runtime": snapshot.get("assistant_runtime", {}),
    }


@app.get("/api/system/health")
async def get_system_health():
    payload = _system_health_payload()
    payload["status"] = "ok"
    return payload


@app.get("/api/memory/stats")
async def get_memory_status():
    return get_memory_stats()


@app.get("/api/security/status")
async def get_security_status(request: Request, session_id: str = "default", resource_id: Optional[str] = None):
    user = _require_authenticated_user(request)
    session_snapshot = describe_login_session(read_session_token(request))
    return {
        "pin": get_pin_status(),
        "auth": {"authenticated": True, "user": user},
        "session_id": session_id,
        "session": session_snapshot,
        "resource_locked": is_locked(resource_id) if resource_id else False,
        "confirmation_code": confirmation_system.code_exists(user.get("id", "")),
        "rate_limits": access_controller.list_rate_limits() if is_admin_user(user) else [],
    }


@app.get("/api/admin/system-status")
async def admin_system_status(request: Request):
    _require_admin_user(request)
    return await system_status(request)


@app.get("/api/forge/report")
async def get_forge_report(request: Request):
    _require_admin_user(request)
    return forge_engine.run_audit_cycle(fresh=_refresh_requested(request))


@app.get("/api/system/modes")
async def get_modes():
    return {
        "items": list_system_modes(),
    }


@app.post("/api/agents/run/{agent_id}")
async def run_agent_endpoint(agent_id: str, payload: AgentRunRequest, request: Request):
    user = _current_user(request)
    session_token = read_session_token(request) if user else None
    normalized_session_id = _resolve_session_id(request, payload.session_id)
    runtime_security_context = {
        "username": user.get("username") if user else payload.username,
        "user_id": user.get("id") if user else None,
        "session_token": session_token,
        "confirmed": payload.confirmed,
        "pin": payload.pin,
        "otp": payload.otp,
        "otp_token": payload.otp_token,
    }
    generated_ids = {item["id"] for item in list_generated_agent_cards()}
    if agent_id in generated_ids:
        result = run_generated_agent(
            agent_id,
            payload.text,
            username=user.get("username") if user else payload.username,
            user_id=user.get("id") if user else None,
            session_id=normalized_session_id,
            session_token=session_token,
            confirmed=payload.confirmed,
            pin=payload.pin,
            otp=payload.otp,
            otp_token=payload.otp_token,
            save_artifact=payload.save_artifact,
        )
        return {
            "success": bool(result.get("success")),
            "dispatch_mode": "generated_agent",
            "agent_id": agent_id,
            "result": result,
        }

    runtime_result = process_command_detailed(
        payload.text,
        session_id=normalized_session_id,
        security_context=runtime_security_context,
    )
    matched_target = (
        agent_id == runtime_result.get("intent")
        or agent_id == runtime_result.get("detected_intent")
        or agent_id in runtime_result.get("used_agents", [])
    )
    return {
        "success": True,
        "dispatch_mode": "runtime_route",
        "agent_id": agent_id,
        "matched_target": matched_target,
        "result": runtime_result,
    }


@app.get("/api/voice/status")
async def get_voice_runtime_status():
    return get_voice_status()


@app.get("/api/assistant/runtime")
async def get_assistant_runtime_endpoint():
    return get_assistant_runtime_status()


@app.post("/api/voice/desktop/start")
async def start_desktop_voice_endpoint(request: Request):
    user = _current_user(request)
    session_id = _resolve_session_id(request)
    return start_desktop_voice(
        session_id=session_id,
        user_profile=user or {},
    )


@app.post("/api/voice/desktop/stop")
async def stop_desktop_voice_endpoint():
    return stop_desktop_voice()


@app.post("/api/voice/desktop/interrupt")
async def interrupt_desktop_voice_endpoint():
    return interrupt_desktop_voice()


@app.patch("/api/voice/settings")
async def update_voice_settings_endpoint(settings: VoiceSettingsUpdate):
    return update_voice_preferences(**settings.model_dump(exclude_none=True))


@app.get("/api/voice/personas")
async def list_voice_personas_endpoint():
    return {"success": True, "personas": list_voice_personas()}


@app.post("/api/voice/text")
async def process_voice_text_endpoint(payload: VoiceTextRequest, request: Request):
    user = _current_user(request)
    session_id = _resolve_session_id(request)
    return process_voice_text(
        payload.text,
        session_id=session_id,
        user_profile=user,
        current_mode=payload.mode,
    )


@app.post("/api/voice/speak")
async def speak_voice_text_endpoint(request: VoiceTextRequest):
    return speak_response(request.text)


@app.post("/api/voice/stop")
async def stop_voice_text_endpoint():
    return stop_voice_output()


@app.post("/api/voice/microphone")
async def transcribe_voice_microphone_endpoint(request: VoiceCaptureRequest):
    return transcribe_microphone_request(timeout=request.timeout, phrase_time_limit=request.phrase_time_limit)


@app.post("/api/security/session-approve")
async def approve_security_action(payload: SecurityActionRequest, request: Request):
    user = _require_authenticated_user(request)
    result = approve_action(payload.session_id, payload.action_name)
    record_execution_result(
        payload.action_name,
        session_id=payload.session_id,
        username=user.get("username"),
        success=bool(result.get("success")),
        trust_level="sensitive",
        meta={"layer": "api", "endpoint": "session_approve"},
    )
    return result


@app.post("/api/security/lock")
async def lock_resource_endpoint(request: LockRequest):
    return lock_resource(request.resource_id, owner=request.owner)


@app.post("/api/security/unlock")
async def unlock_resource_endpoint(request: LockRequest):
    return unlock_resource(request.resource_id)


@app.post("/api/security/enforce")
async def enforce_action_endpoint(payload: EnforceActionBody, request: Request):
    user = _current_user(request)
    user_id = str(user.get("id")) if user else None
    username = user.get("username") if user else None
    session_token = read_session_token(request)
    result = enforce_action(
        payload.action_name,
        username=username,
        user_id=user_id,
        session_id=payload.session_id,
        session_token=session_token,
        confirmed=payload.confirmed,
        pin=payload.pin,
        otp=payload.otp,
        otp_token=payload.otp_token,
        resource_id=payload.resource_id,
        meta={"layer": "api", "endpoint": "enforce"},
    )
    return result


@app.post("/api/security/otp/request")
async def request_otp_endpoint(payload: OtpRequestBody, request: Request):
    user = _current_user(request)
    if not user:
        return JSONResponse({"success": False, "reason": "Authentication required."}, status_code=401)
    user_id = str(user.get("id") or user.get("username") or "anonymous")
    session_id = _resolve_session_id(request)
    result = request_otp(user_id, payload.action_name, purpose=payload.purpose, session_id=session_id)
    return {
        "success": result.get("success", False),
        "status": result.get("status"),
        "token": result.get("token"),
        "expires_at": result.get("expires_at"),
        "expires_in_seconds": result.get("expires_in_seconds"),
        "action_name": result.get("action_name"),
        "delivery": result.get("delivery"),
        "phone_recipient": result.get("phone_recipient"),
        "code": result.get("code") if not result.get("phone_recipient") else None,
        "session_id": result.get("session_id"),
    }


@app.post("/api/security/otp/verify")
async def verify_otp_endpoint(payload: OtpVerifyBody, request: Request):
    user = _current_user(request)
    if not user:
        return JSONResponse({"success": False, "reason": "Authentication required."}, status_code=401)
    user_id = str(user.get("id") or user.get("username") or "anonymous")
    session_id = _resolve_session_id(request)
    result = verify_otp(user_id, payload.action_name, payload.code, token=payload.token, session_id=session_id)
    return result


@app.get("/api/security/dashboard")
async def security_status_endpoint(request: Request, limit: int = 25):
    """Operator dashboard: recent blocks / approvals / OTP / PIN lockouts."""

    user = _current_user(request)
    if not user:
        return JSONResponse({"success": False, "reason": "Authentication required."}, status_code=401)
    if not is_admin_user(user):
        return JSONResponse({"success": False, "reason": "Admin access required."}, status_code=403)
    capped_limit = max(1, min(int(limit or 25), 200))
    return {"success": True, "status": security_status_summary(limit=capped_limit)}


@app.get("/api/security/otp/status")
async def otp_status_endpoint(action_name: str, request: Request):
    user = _current_user(request)
    if not user:
        return JSONResponse({"success": False, "reason": "Authentication required."}, status_code=401)
    user_id = str(user.get("id") or user.get("username") or "anonymous")
    return get_otp_status(user_id, action_name)


@app.post("/api/security/phone/register")
async def register_phone_endpoint(payload: PhoneRegisterBody, request: Request):
    user = _current_user(request)
    if not user:
        return JSONResponse({"success": False, "reason": "Authentication required."}, status_code=401)
    user_id = str(user.get("id") or user.get("username") or "anonymous")
    session_token = read_session_token(request)
    access = enforce_action(
        "phone_register",
        username=user.get("username"),
        user_id=user_id,
        session_id=_resolve_session_id(request),
        session_token=session_token,
        pin=payload.pin,
        require_auth=True,
        meta={"layer": "api", "endpoint": "phone_register"},
    )
    if not access.get("allowed"):
        return JSONResponse(
            {
                "success": False,
                "status": access.get("status"),
                "reason": access.get("reason"),
                "access": access,
            },
            status_code=403,
        )

    result = register_phone(user_id, payload.phone)
    record_execution_result(
        "phone_register",
        session_id=_resolve_session_id(request),
        username=user.get("username"),
        success=bool(result.get("success")),
        reason=None if result.get("success") else str(result.get("reason") or "phone_register_failed"),
        trust_level="critical",
        meta={"layer": "api", "endpoint": "phone_register"},
    )
    return result


@app.get("/api/security/phone")
async def get_phone_endpoint(request: Request):
    user = _current_user(request)
    if not user:
        return JSONResponse({"success": False, "reason": "Authentication required."}, status_code=401)
    user_id = str(user.get("id") or user.get("username") or "anonymous")
    entry = get_phone(user_id)
    return {"success": bool(entry), "phone": entry}


@app.delete("/api/security/phone")
async def delete_phone_endpoint(request: Request):
    user = _current_user(request)
    if not user:
        return JSONResponse({"success": False, "reason": "Authentication required."}, status_code=401)
    user_id = str(user.get("id") or user.get("username") or "anonymous")
    ok = remove_phone(user_id)
    return {"success": ok}


@app.get("/api/security/audit")
async def audit_log_endpoint(limit: int = 100, kind: Optional[str] = None, request: Request = None):
    user = _current_user(request) if request else None
    if not user or not is_admin_user(user):
        return JSONResponse({"success": False, "reason": "Admin privileges required."}, status_code=403)
    kinds = [kind] if kind else None
    return {"success": True, "events": tail_audit_log(limit=limit, kinds=kinds)}


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
