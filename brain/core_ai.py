from __future__ import annotations

import os
import re
import time
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

import brain.response_engine as response_engine_module
from agents.agent_bus import agent_bus
from agents.agent_registry import AgentRegistry
from agents.context import VORISContext
from brain import runtime_core as runtime_core_module
from brain.response_engine import FALLBACK_USER_MESSAGE, build_degraded_reply, clean_response, generate_response, generate_response_payload
from config.settings import GROQ_API_KEY, MODEL_NAME
from memory.chat_history import get_history
from memory.personalization import (
    append_relevant_suggestion,
    build_personal_context,
    build_personalized_system_prompt,
    clear_session_personal_context,
    get_personal_display_name,
    remember_explicit_personal_signals,
    remember_profile_identity,
)
from memory.working_memory import load_working_memory
from security.enforcement import enforce_action

load_dotenv()
if not GROQ_API_KEY:
    print("[PROVIDER] Groq is not configured; live Groq responses will be unavailable.")


AGENT_ROUTER = runtime_core_module.AGENT_ROUTER
SESSION_CONTEXT_HISTORY: dict[str, list[dict[str, str]]] = {}
MAX_SESSION_EXCHANGES = 10

JARVIS_SYSTEM_PROMPT = response_engine_module.JARVIS_SYSTEM_PROMPT

UNUSABLE_RESPONSE_MARKERS = (
    FALLBACK_USER_MESSAGE.strip().lower(),
    "i couldn't generate a useful response right now.",
    "i ran into a problem while generating a response. please try again.",
    "is planned, but it is not available for live chat yet.",
    "agent failed:",
)


def _normalize_session_id(session_id: Optional[str]) -> str:
    value = str(session_id or "default").strip()
    return value or "default"


def _get_session_history(session_id: str) -> list[dict[str, str]]:
    return SESSION_CONTEXT_HISTORY.setdefault(session_id, [])


def _load_persisted_history(session_id: str) -> list[dict[str, str]]:
    try:
        rows = get_history(session_id, limit=10)
    except Exception:
        return []

    messages: list[dict[str, str]] = []
    for row in rows:
        role = str(row.get("role", "")).strip().lower()
        content = str(row.get("message", "")).strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    return messages


def build_messages_with_history(
    user_input: str,
    session_id: str,
    user_profile: Optional[dict[str, Any]] = None,
    personal_context: Optional[dict[str, Any]] = None,
) -> list[dict[str, str]]:
    # Persisted chat rows are session-only today, not user-owned. Keep the live
    # response context to in-process session history until durable history has
    # explicit owner metadata.
    persisted_history: list[dict[str, str]] = []
    in_memory_history = list(_get_session_history(session_id))
    merged: list[dict[str, str]] = []

    for item in persisted_history + in_memory_history:
        role = str(item.get("role", "")).strip().lower()
        content = str(item.get("content", "")).strip()
        normalized = {"role": role, "content": content}
        if role not in {"user", "assistant"} or not content:
            continue
        if merged and merged[-1] == normalized:
            continue
        merged.append(normalized)

    context = personal_context or build_personal_context(
        user_input,
        session_id=session_id,
        user_profile=user_profile,
        history=merged,
    )
    system_prompt = build_personalized_system_prompt(JARVIS_SYSTEM_PROMPT, context)

    return response_engine_module.build_messages(
        user_input,
        system_prompt,
        history=merged[-MAX_SESSION_EXCHANGES * 2 :],
    )


def _sync_context_into_response_engine(
    session_id: str,
    user_profile: Optional[dict[str, Any]] = None,
    personal_context: Optional[dict[str, Any]] = None,
) -> None:
    response_engine_module.clear_history()
    merged_messages = build_messages_with_history("", session_id, user_profile=user_profile, personal_context=personal_context)
    for item in merged_messages:
        if item.get("role") in {"user", "assistant"} and str(item.get("content", "")).strip():
            response_engine_module.add_to_history(item.get("role", "user"), item.get("content", ""))


def _record_exchange(session_id: str, user_message: str, assistant_message: str) -> None:
    history = _get_session_history(session_id)
    if user_message.strip():
        history.append({"role": "user", "content": user_message.strip()})
    if assistant_message.strip():
        history.append({"role": "assistant", "content": assistant_message.strip()})
    max_messages = MAX_SESSION_EXCHANGES * 2
    if len(history) > max_messages:
        del history[:-max_messages]


def clear_session_context(session_id: Optional[str] = None) -> None:
    if session_id is None:
        SESSION_CONTEXT_HISTORY.clear()
        clear_session_personal_context()
        return
    normalized_session = _normalize_session_id(session_id)
    SESSION_CONTEXT_HISTORY.pop(normalized_session, None)
    clear_session_personal_context(normalized_session)


def _build_user_reference(user_profile: Optional[dict[str, Any]]) -> str:
    profile = dict(user_profile or {})
    preferred_name = str(profile.get("preferred_name") or "").strip()
    if preferred_name:
        return preferred_name
    username = str(profile.get("username") or "").strip()
    if username:
        return username
    return ""


def _knowledge_base_request(command: str) -> Optional[dict[str, str]]:
    text = str(command or "").strip().lower()
    if "what is my name" in text:
        return {"action_name": "memory_read", "field": "name"}
    if "what is my age" in text or "how old am i" in text:
        return {"action_name": "memory_read", "field": "age"}
    if "what is my city" in text or "where do i live" in text:
        return {"action_name": "memory_read", "field": "city"}
    return None


def _infer_proactive_suggestion(intent: str, command: str) -> Optional[str]:
    normalized_intent = str(intent or "general").strip().lower()
    text = str(command or "").strip().lower()
    if normalized_intent == "research":
        return "turn the research into a brief summary or task list"
    if normalized_intent == "study":
        return "generate revision questions or flashcards"
    if normalized_intent in {"task", "reminder"}:
        return "schedule a reminder or break the plan into smaller steps"
    if normalized_intent == "code" or "code" in text:
        return "review the implementation risks or test plan"
    if normalized_intent == "file":
        return "summarize the file findings or extract action items"
    return None


def _jarvis_prefix(intent: str, execution_mode: str) -> str:
    normalized_intent = str(intent or "general").strip().lower()
    normalized_mode = str(execution_mode or "").strip().lower()
    if normalized_mode == "permission_blocked":
        return ""
    if normalized_intent in {"task", "reminder"}:
        return "Done. "
    if normalized_mode in {"generated_agent", "multi_agent"} and normalized_intent in {"research", "reasoning", "compare", "study"}:
        return "Here is the answer. "
    return ""


def _jarvisize_response(
    response: str,
    *,
    intent: str,
    execution_mode: str,
    user_profile: Optional[dict[str, Any]],
    session_id: str,
    command: str,
    personal_context: Optional[dict[str, Any]] = None,
) -> str:
    text = response_engine_module.polish_assistant_reply(response, user_input=command)
    if not text:
        text = clean_response(response)
    if not text:
        return text

    prefix = _jarvis_prefix(intent, execution_mode)
    if prefix and not re.match(r"^(certainly|analysis complete|right away|welcome back|task complete|processing your request)\b", text, flags=re.IGNORECASE):
        text = f"{prefix}{text[0].lower() + text[1:] if len(text) > 1 and text[0].isupper() else text}"

    suggestions_enabled = user_profile is None or bool(user_profile.get("proactive_suggestions", True))
    if suggestions_enabled and str(execution_mode or "").strip().lower() not in {
        "document_generation",
        "permission_blocked",
        "action_plan",
        "action_plan_failed",
    }:
        text = append_relevant_suggestion(text, personal_context)

    return clean_response(text)


def _build_reasoning_trace(result: dict[str, Any], elapsed_ms: float) -> dict[str, Any]:
    confidence = float(result.get("confidence", 0.0) or 0.0)
    return {
        "intent_detected": result.get("detected_intent") or result.get("intent") or "general",
        "confidence_score": round(confidence, 4),
        "agents_involved": list(result.get("used_agents") or []),
        "critical_thinking_result": "clarify" if confidence < 0.45 else "ready",
        "time_taken_ms": round(elapsed_ms, 2),
    }


def _build_context(session_id: str, user_profile: Optional[dict[str, Any]] = None, current_mode: str = "hybrid") -> VORISContext:
    user_profile = dict(user_profile or {})
    return VORISContext(
        user_id=str(user_profile.get("id") or user_profile.get("username") or "guest"),
        session_id=session_id,
        current_mode=current_mode,
        language=str(user_profile.get("language") or "en"),
        memory=load_working_memory(session_id),
        trust_level="safe",
        conversation_history=list(_get_session_history(session_id)),
        metadata=dict(user_profile),
    )


def _security_context_with_personal_context(
    security_context: Optional[dict[str, Any]],
    personal_context: dict[str, Any],
) -> dict[str, Any]:
    context = dict(security_context or {})
    if personal_context:
        context["personal_context"] = personal_context
    return context


def _is_unusable_response(text: Optional[str]) -> bool:
    normalized = clean_response(text).strip().lower()
    if not normalized:
        return True
    return any(marker in normalized for marker in UNUSABLE_RESPONSE_MARKERS)


def _structured_degraded_response(command: str, providers_tried: Optional[List[Any]] = None) -> str:
    reply = clean_response(build_degraded_reply(command, providers_tried))
    if reply:
        return reply
    return "I couldn't complete that request cleanly, but the request path is still available. Please try again in a moment."


def _ensure_meaningful_brain_response(
    enriched: dict[str, Any],
    *,
    command: str,
    session_id: str,
    user_profile: Optional[dict[str, Any]] = None,
    personal_context: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    response_text = clean_response(enriched.get("response"))
    if not _is_unusable_response(response_text):
        return enriched

    print("[BRAIN ERROR] Runtime pipeline produced an unusable response. Attempting live provider fallback.")
    fallback = _call_live_brain_direct(
        command,
        session_id,
        user_profile=user_profile,
        personal_context=personal_context,
    )
    fallback_text = clean_response(fallback.get("content"))
    if fallback.get("success") and not _is_unusable_response(fallback_text):
        enriched["response"] = fallback_text
        enriched["provider"] = fallback.get("provider")
        enriched["model"] = fallback.get("model")
        enriched["providers_tried"] = list(fallback.get("providers_tried") or [])
        return enriched

    combined_attempts = list(enriched.get("providers_tried") or [])
    for item in list(fallback.get("providers_tried") or []):
        if item not in combined_attempts:
            combined_attempts.append(item)

    enriched["response"] = _structured_degraded_response(command, combined_attempts)
    enriched["provider"] = None
    enriched["model"] = None
    enriched["providers_tried"] = combined_attempts
    enriched["execution_mode"] = "degraded_assistant"
    enriched["degraded"] = True
    if not enriched.get("error"):
        enriched["error"] = str(fallback.get("error") or "The live response path did not return usable content.")
    return enriched


def _call_live_brain_direct(
    command: str,
    session_id: str,
    *,
    user_profile: Optional[dict[str, Any]] = None,
    personal_context: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    context = personal_context or build_personal_context(
        command,
        session_id=session_id,
        user_profile=user_profile,
        history=list(_get_session_history(session_id)),
    )
    system_prompt = build_personalized_system_prompt(JARVIS_SYSTEM_PROMPT, context)
    messages = build_messages_with_history(
        command,
        session_id,
        user_profile=user_profile,
        personal_context=context,
    )
    payload = generate_response_payload(messages, system_override=system_prompt)
    if not payload.get("success"):
        print(f"[BRAIN ERROR] Live provider fallback failed: {payload.get('error')}")
    return payload


def _knowledge_base_result(
    command: str,
    session_id: str,
    user_profile: Optional[dict[str, Any]],
    current_mode: str,
    security_context: Optional[dict[str, Any]] = None,
) -> Optional[dict[str, Any]]:
    lookup = _knowledge_base_request(command)
    if not lookup:
        return None
    profile = dict(user_profile or {})
    identity = dict(security_context or {})
    access = enforce_action(
        str(lookup.get("action_name") or "memory_read"),
        username=str(identity.get("username") or profile.get("username") or "").strip() or None,
        user_id=str(identity.get("user_id") or profile.get("id") or "").strip() or None,
        session_id=session_id,
        session_token=str(identity.get("session_token") or "").strip() or None,
        confirmed=bool(identity.get("confirmed", False)),
        pin=str(identity.get("pin") or "").strip() or None,
        otp=str(identity.get("otp") or "").strip() or None,
        otp_token=str(identity.get("otp_token") or "").strip() or None,
        require_auth=True,
        meta={"layer": "core_ai", "stage": "knowledge_base"},
    )
    permission = {
        "success": bool(access.get("allowed")),
        "status": "approved" if access.get("allowed") else str(access.get("status") or "blocked"),
        "mode": "real",
        "permission": {
            **dict(access.get("decision") or {}),
            "action_name": str(lookup.get("action_name") or "memory_read"),
            "trust_level": str(access.get("trust_level") or "private"),
            "approval_type": str(access.get("approval_type") or "confirm"),
            "reason": str(access.get("reason") or ""),
        },
        "enforcement": access,
    }
    if not permission["success"]:
        return {
            "intent": "permission",
            "detected_intent": "memory",
            "confidence": 1.0,
            "response": str(permission["permission"].get("reason") or "Permission required."),
            "provider": None,
            "model": None,
            "plan": [],
            "used_agents": ["memory"],
            "agent_capabilities": runtime_core_module.build_runtime_agent_cards(["memory"]),
            "execution_mode": "permission_blocked",
            "decision": runtime_core_module.build_decision_summary("memory", 1.0, AGENT_ROUTER),
            "orchestration": {
                "primary_agent": "memory",
                "execution_order": ["memory"],
                "agent_registry_connected": True,
            },
            "permission_action": str(lookup.get("action_name") or "memory_read"),
            "permission": permission,
            "reasoning_trace": {
                "intent_detected": "memory",
                "confidence_score": 1.0,
                "agents_involved": ["memory"],
                "critical_thinking_result": "permission_required",
                "time_taken_ms": 0.0,
            },
            "context_window": list(_get_session_history(session_id)),
            "mode": current_mode,
        }

    personal_context = build_personal_context(
        "",
        session_id=session_id,
        user_profile=profile,
        history=list(_get_session_history(session_id)),
    )
    user_reference = _build_user_reference(profile)
    field = str(lookup.get("field") or "").strip().lower()
    if field == "name":
        value = get_personal_display_name(profile, session_id=session_id)
        if value:
            reply = f"Your name is {value}."
        else:
            reply = "I don't know your name yet."
    elif field == "age":
        value = str(personal_context.get("age") or "").strip()
        if value:
            reply = f"{user_reference}, your age is {value}." if user_reference else f"Your age is {value}."
        else:
            reply = "I don't know your age yet."
    else:
        value = str(personal_context.get("city") or "").strip()
        if value:
            reply = f"{user_reference}, you're in {value}." if user_reference else f"You're in {value}."
        else:
            reply = "I don't know your city yet."
    context = _build_context(session_id, user_profile=profile, current_mode=current_mode)
    context.activate("memory")
    reasoning_trace = {
        "intent_detected": "memory",
        "confidence_score": 1.0,
        "agents_involved": ["memory"],
        "critical_thinking_result": "local_fact_hit",
        "time_taken_ms": 0.0,
    }
    return {
        "intent": "memory",
        "detected_intent": "memory",
        "confidence": 1.0,
        "response": reply,
        "provider": "local_memory",
        "model": "local",
        "plan": [],
        "used_agents": ["memory"],
        "agent_capabilities": runtime_core_module.build_runtime_agent_cards(["memory"]),
        "execution_mode": "knowledge_base",
        "decision": runtime_core_module.build_decision_summary("memory", 1.0, AGENT_ROUTER),
        "orchestration": {
            "primary_agent": "memory",
            "execution_order": ["memory"],
            "agent_registry_connected": True,
        },
        "permission_action": str(lookup.get("action_name") or "memory_read"),
        "permission": permission,
        "reasoning_trace": reasoning_trace,
        "context_window": context.conversation_history[-MAX_SESSION_EXCHANGES * 2 :],
        "mode": current_mode,
    }


def _enrich_result(
    command: str,
    result: dict[str, Any],
    *,
    session_id: str,
    user_profile: Optional[dict[str, Any]],
    current_mode: str,
    elapsed_ms: float,
    personal_context: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    enriched = dict(result)
    execution_mode = str(result.get("execution_mode") or "chat")
    if execution_mode == "document_generation":
        enriched["response"] = clean_response(str(result.get("response") or "")) or "Your document is ready."
    else:
        enriched["response"] = _jarvisize_response(
            str(result.get("response") or ""),
            intent=str(result.get("detected_intent") or result.get("intent") or "general"),
            execution_mode=execution_mode,
            user_profile=user_profile,
            session_id=session_id,
            command=command,
            personal_context=personal_context,
        )
    enriched["mode"] = current_mode
    enriched["reasoning_trace"] = _build_reasoning_trace(enriched, elapsed_ms)
    orchestration = dict(enriched.get("orchestration") or {})
    orchestration["agent_registry_connected"] = True
    orchestration["agent_bus_connected"] = True
    orchestration["active_agents"] = list(enriched.get("used_agents") or [])
    enriched["orchestration"] = orchestration
    enriched["provider"] = enriched.get("provider") or None
    enriched["model"] = enriched.get("model") or None
    enriched["providers_tried"] = list(enriched.get("providers_tried") or [])
    enriched["context_window"] = list(_get_session_history(session_id))
    enriched["personal_context"] = {
        "display_name": (personal_context or {}).get("display_name"),
        "preferences": list((personal_context or {}).get("preferences") or [])[:3],
        "suggestion": (personal_context or {}).get("suggestion"),
    }
    agent_bus.publish(
        "brain.response.completed",
        {
            "intent": enriched.get("detected_intent") or enriched.get("intent") or "general",
            "session_id": session_id,
            "used_agents": list(enriched.get("used_agents") or []),
        },
    )
    return enriched


def process_single_command_detailed(
    command: str,
    *,
    session_id: str = "default",
    user_profile: Optional[dict[str, Any]] = None,
    current_mode: str = "hybrid",
    security_context: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    normalized_session = _normalize_session_id(session_id)
    kb_result = _knowledge_base_result(command, normalized_session, user_profile, current_mode, security_context)
    if kb_result is not None:
        _record_exchange(normalized_session, command, kb_result["response"])
        return kb_result

    profile = dict(user_profile or {})
    history = list(_get_session_history(normalized_session))
    personal_context = build_personal_context(
        command,
        session_id=normalized_session,
        user_profile=profile,
        history=history,
    )
    runtime_security_context = _security_context_with_personal_context(security_context, personal_context)
    remember_profile_identity(profile)
    remember_explicit_personal_signals(command, session_id=normalized_session, user_profile=profile)

    _sync_context_into_response_engine(normalized_session, user_profile=profile, personal_context=personal_context)
    started = time.perf_counter()
    try:
        result = runtime_core_module.process_single_command_detailed(
            command,
            session_id=normalized_session,
            security_context=runtime_security_context,
        )
    except Exception as error:
        print(f"[BRAIN ERROR] Runtime pipeline failed: {error}")
        raise
    elapsed_ms = (time.perf_counter() - started) * 1000
    enriched = _enrich_result(
        command,
        result,
        session_id=normalized_session,
        user_profile=user_profile,
        current_mode=current_mode,
        elapsed_ms=elapsed_ms,
        personal_context=personal_context,
    )
    enriched = _ensure_meaningful_brain_response(
        enriched,
        command=command,
        session_id=normalized_session,
        user_profile=profile,
        personal_context=personal_context,
    )
    _record_exchange(normalized_session, command, enriched["response"])
    return enriched


def process_command_detailed(
    command: str,
    *,
    session_id: str = "default",
    user_profile: Optional[dict[str, Any]] = None,
    current_mode: str = "hybrid",
    security_context: Optional[dict[str, Any]] = None,
) -> dict[str, Any]:
    normalized_session = _normalize_session_id(session_id)
    kb_result = _knowledge_base_result(command, normalized_session, user_profile, current_mode, security_context)
    if kb_result is not None:
        _record_exchange(normalized_session, command, kb_result["response"])
        return kb_result

    profile = dict(user_profile or {})
    history = list(_get_session_history(normalized_session))
    personal_context = build_personal_context(
        command,
        session_id=normalized_session,
        user_profile=profile,
        history=history,
    )
    runtime_security_context = _security_context_with_personal_context(security_context, personal_context)
    remember_profile_identity(profile)
    remember_explicit_personal_signals(command, session_id=normalized_session, user_profile=profile)

    _sync_context_into_response_engine(normalized_session, user_profile=profile, personal_context=personal_context)
    started = time.perf_counter()
    try:
        result = runtime_core_module.process_command_detailed(
            command,
            session_id=normalized_session,
            security_context=runtime_security_context,
        )
    except Exception as error:
        print(f"[BRAIN ERROR] Runtime pipeline failed: {error}")
        raise
    elapsed_ms = (time.perf_counter() - started) * 1000
    enriched = _enrich_result(
        command,
        result,
        session_id=normalized_session,
        user_profile=user_profile,
        current_mode=current_mode,
        elapsed_ms=elapsed_ms,
        personal_context=personal_context,
    )
    enriched = _ensure_meaningful_brain_response(
        enriched,
        command=command,
        session_id=normalized_session,
        user_profile=profile,
        personal_context=personal_context,
    )
    _record_exchange(normalized_session, command, enriched["response"])
    return enriched


def process_single_command(command: str, **kwargs: Any) -> tuple[str, str]:
    result = process_single_command_detailed(command, **kwargs)
    return str(result.get("intent") or "general"), str(result.get("response") or "")


def process_command(command: str, **kwargs: Any) -> tuple[str, str]:
    result = process_command_detailed(command, **kwargs)
    return str(result.get("intent") or "general"), str(result.get("response") or "")
