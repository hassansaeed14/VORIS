import re
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

from brain.command_splitter import split_commands
from brain.confidence_engine import evaluate_confidence
from brain.context_manager import update_context_from_command
from brain.decision_engine import (
    build_decision_summary,
    format_multi_response,
    should_add_low_confidence_note,
    should_fallback_to_general,
    should_plan,
    should_treat_as_multi_command,
    should_use_agent,
)
from brain.entity_parser import parse_entities
from brain.planner import summarize_execution_plan
from brain.reflection_engine import record_reflection
from brain.orchestrator import orchestrator as master_orchestrator
from brain.response_engine import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_TEMPERATURE,
    FALLBACK_USER_MESSAGE,
    build_messages,
    build_system_prompt,
    build_degraded_reply,
    clean_response,
    generate_response_payload,
    generate_transformation_content_payload,
    generate_web_search_response_payload,
    is_long_form_writing_request,
    is_meaningful_text,
)
from brain.system_trace import build_action_trace, new_request_id
from brain.telemetry_engine import ProcessingTelemetry, set_last_telemetry
from brain.intent_engine import detect_intent_with_confidence, is_conversational_input
from brain.understanding_engine import clean_user_input

from config.settings import DEFAULT_REASONING_PROVIDER
from memory.memory_controller import process_interaction_memory
from memory.personalization import build_personalized_system_prompt, get_personal_display_name, remember_explicit_personal_signals

from agents.autonomous.planner_agent import create_plan, parse_plan_to_steps
from agents.core.language_agent import detect_language, respond_in_language
from agents.core.reasoning_agent import compare, reason
from agents.core.self_improvement_agent import log_failure, log_agent_error, log_low_confidence
from agents.integration.currency_agent import convert_currency, get_crypto_price
from agents.integration.dictionary_agent import define_word, get_synonyms
from agents.integration.joke_agent import get_joke
from agents.integration.math_agent import solve_math
from agents.integration.news_agent import get_news
from agents.integration.quote_agent import get_quote
from agents.integration.reminder_agent import (
    add_reminder,
    complete_reminder,
    delete_reminder,
    get_reminders,
)
from agents.integration.translation_agent import translate
from agents.integration.weather_agent import get_weather
from agents.integration.web_search_agent import web_search
from agents.integration.youtube_agent import search_youtube_topic
from agents.productivity.coding_agent import code_help
from agents.productivity.content_writer_agent import write_content
from agents.productivity.email_writer_agent import write_email
from agents.productivity.fitness_agent import get_workout_plan
from agents.productivity.grammar_agent import check_grammar
from agents.productivity.quiz_agent import generate_flashcards, generate_quiz
from agents.productivity.research_agent import research
from agents.productivity.study_agent import study
from agents.productivity.summarizer_agent import summarize_text, summarize_topic
from agents.productivity.task_agent import add_task, complete_task, delete_task, get_tasks, plan_tasks
from agents.system.file_agent import analyze_file, list_files
from agents.system.screenshot_agent import take_screenshot
from security.enforcement import enforce_action, record_execution_result
from security.permission_engine import check_permission
from security.trust_engine import build_permission_response, get_trust_level
from agents.agent_fabric import match_generated_agent_request, run_generated_agent
from agents.registry import (
    build_runtime_agent_cards,
    filter_chat_routable_agents,
    get_agent_capability_mode,
    is_chat_routable_agent,
)
from tools.document_generator import (
    DocumentRequest,
    generate_document,
    normalize_document_formats,
    normalize_document_style,
    normalize_citation_style,
    remember_document_request,
    remember_generated_document,
    resolve_document_request,
    resolve_document_retrieval_followup,
    secure_generated_document_access,
)
from tools.action_intelligence import build_action_plan, execute_action_plan
from tools.content_extractor import extract_content, is_youtube_url
from tools.desktop_controller import (
    get_application_label,
    normalize_application_name,
    open_application,
)


GREETING_INPUTS = {
    "hi",
    "hello",
    "hey",
    "hey voris",
    "hi voris",
    "hello voris",
    "hey aura",
    "hi aura",
    "hello aura",
}
CONVERSATIONAL_INTENTS = {"greeting", "conversation"}
INTENT_ALIAS_MAP = {
    "content": "write",
}
INTENT_TO_REAL_AGENT_MAP = {
    "write": "writing_runtime",
    "research": "research_runtime",
    "code": "coding_runtime",
    "summarize": "summary_runtime",
    "document": "document_generator",
}
DIRECT_ASSISTANT_STARTERS = (
    "what ",
    "who ",
    "why ",
    "how ",
    "when ",
    "where ",
    "is ",
    "are ",
    "can ",
    "could ",
    "should ",
    "would ",
    "do ",
    "does ",
    "did ",
    "tell me",
    "explain",
    "write",
    "make",
    "create",
    "show me",
    "give me",
    "help me",
)
DIRECT_ASSISTANT_TOOL_MARKERS = (
    "convert ",
    "translate ",
    "search ",
    "google ",
    "weather",
    "forecast",
    "news",
    "remind me",
    "task",
    "todo",
    "youtube",
    "screenshot",
    "open file",
    "read file",
    "list files",
    "compare ",
    "buy ",
    "purchase ",
)

WEB_SEARCH_SIGNAL_PATTERNS = (
    r"\b(latest|current|today|right now|now|recent|recently|newest|breaking|live)\b",
    r"\b(news|headline|headlines)\b",
    r"\b(price|pricing|cost|version|release date|release notes|changelog|stock|market cap)\b",
    r"\b(status|outage|downtime|availability|health)\b",
)

WEB_SEARCH_SUBJECT_MARKERS = (
    "groq",
    "gemini",
    "openai",
    "openrouter",
    "claude",
    "ollama",
    "provider",
    "providers",
    "api",
    "model",
    "tool",
    "tools",
    "software",
    "framework",
    "library",
    "package",
    "product",
    "company",
)

WEB_SEARCH_SKIP_INTENTS = {
    "greeting",
    "conversation",
    "time",
    "date",
    "identity",
    "memory",
    "insights",
    "math",
    "dictionary",
    "synonyms",
    "translation",
    "joke",
    "quote",
    "task",
    "reminder",
    "weather",
    "news",
    "file",
    "list_files",
    "screenshot",
}

_YOUTUBE_URL_RE = re.compile(
    r"(?:https?://)?(?:www\.)?(?:youtube\.com/watch\?v=[\w-]+|youtu\.be/[\w-]+|youtube\.com/shorts/[\w-]+)",
    flags=re.IGNORECASE,
)

_TRANSFORMATION_TRIGGER_RE = re.compile(
    r"\b(?:convert|transform|turn|change)\b.{0,60}\b(?:into|to|as)\b.{0,40}\b(?:notes|assignment|slides|summary|summaries)\b"
    r"|\b(?:make|create|generate)\b.{0,40}\b(?:notes|assignment|summary)\b.{0,60}\b(?:from|out of|based on)\b"
    r"|\b(?:summarize|summarise)\b.{0,40}\b(?:this|the|my|following)\b"
    r"|\b(?:notes|assignment)\b.{0,40}\b(?:from|out of|based on)\b(?:this|the|my|following)"
    r"|\b(?:extract|pull out)\b.{0,40}\b(?:notes|key points|summary)\b"
    r"|\b(?:make|create)\b.{0,30}\b(?:notes|assignment)\b.{0,30}\b(?:from|of)\b",
    flags=re.IGNORECASE,
)

_INLINE_CONTENT_SPLIT_RE = re.compile(
    r"[:\uff1a]\s*\n|[:\uff1a]\s{2,}",
)
_DESKTOP_OPEN_COMMAND_RE = re.compile(
    r"^(?:please\s+)?(?:open|launch|start)\s+(?:the\s+)?(?P<target>[a-z0-9 .-]+?)(?:\s+(?:app|application))?[.!?]*$",
    flags=re.IGNORECASE,
)

try:
    from memory.vector_memory import store_memory
except Exception:
    def store_memory(*args, **kwargs) -> None:
        return None


def _telemetry_excerpt(value: Any, limit: int = 220) -> str:
    if isinstance(value, dict):
        text = clean_response(str({key: value[key] for key in list(value)[:4]}))
    elif isinstance(value, list):
        text = clean_response(", ".join(str(item) for item in value[:4]))
    else:
        text = clean_response(str(value or ""))
    return text[:limit] if len(text) > limit else text


def _with_telemetry(
    payload: Dict[str, Any],
    telemetry: Optional[ProcessingTelemetry],
    *,
    publish: bool = True,
) -> Dict[str, Any]:
    if telemetry is None:
        return payload
    telemetry_payload = telemetry.get_telemetry()
    payload["telemetry"] = telemetry_payload
    if publish:
        set_last_telemetry(telemetry_payload)
    return payload


def _llm_response_with_provider(
    user_input: str,
    language: str,
    personal_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    system_prompt = build_personalized_system_prompt(
        build_system_prompt(language),
        personal_context,
    )
    messages = build_messages(user_input, system_prompt)
    started = time.perf_counter()
    provider_response = generate_response_payload(
        messages,
        system_override=system_prompt,
        max_tokens=DEFAULT_MAX_TOKENS,
        temperature=DEFAULT_TEMPERATURE,
    )
    elapsed_ms = (time.perf_counter() - started) * 1000

    if not provider_response.get("success"):
        attempts = provider_response.get("providers_tried") or []
        return {
            "success": False,
            "text": provider_response.get("degraded_reply") or build_degraded_reply(user_input, attempts),
            "provider_name": None,
            "model": provider_response.get("model") or "unknown",
            "tokens_used": None,
            "time_ms": elapsed_ms,
            "error": str(provider_response.get("error") or "No configured provider produced a response."),
            "providers_tried": attempts,
            "degraded": True,
        }

    raw_result = str(provider_response.get("content", "")).strip()
    cleaned = clean_response(raw_result)
    if not is_meaningful_text(cleaned):
        return {
            "success": False,
            "text": provider_response.get("degraded_reply") or build_degraded_reply(user_input, provider_response.get("providers_tried") or []),
            "provider_name": provider_response.get("provider") or "unknown",
            "model": provider_response.get("model") or "unknown",
            "tokens_used": provider_response.get("tokens_used"),
            "time_ms": elapsed_ms,
            "error": provider_response.get("error") or "Provider returned empty content.",
            "providers_tried": provider_response.get("providers_tried") or [],
            "degraded": True,
        }

    return {
        "success": True,
        "text": cleaned,
        "provider_name": provider_response.get("provider") or "unknown",
        "model": provider_response.get("model") or "unknown",
        "tokens_used": provider_response.get("tokens_used"),
        "time_ms": elapsed_ms,
        "providers_tried": provider_response.get("providers_tried") or [],
    }


def _max_trust_level(levels: List[str]) -> str:
    order = {"safe": 0, "private": 1, "sensitive": 2, "critical": 3}
    normalized = [str(level or "safe").strip().lower() for level in levels if level]
    if not normalized:
        return "safe"
    return max(normalized, key=lambda item: order.get(item, 0))


def extract_currency_request(command: str) -> tuple[float, str, str]:
    amount_match = re.search(r"(\d+(\.\d+)?)", command)
    currency_matches = re.findall(r"\b[A-Z]{3}\b", command.upper())

    amount = float(amount_match.group(1)) if amount_match else 1.0

    if len(currency_matches) >= 2:
        return amount, currency_matches[0], currency_matches[1]

    return amount, "USD", "PKR"


def extract_translation_target(command: str) -> str:
    command_lower = command.lower()

    language_map = {
        "urdu": "urdu",
        "english": "english",
        "arabic": "arabic",
        "french": "french",
        "spanish": "spanish",
        "hindi": "hindi",
        "punjabi": "punjabi",
    }

    for lang, target in language_map.items():
        if f"in {lang}" in command_lower or f"to {lang}" in command_lower:
            return target

    return "english"


def extract_numeric_id(command: str) -> Optional[int]:
    match = re.search(r"\b(\d+)\b", command)
    if not match:
        return None
    return int(match.group(1))


def contains_phrase(command_lower: str, phrases: tuple[str, ...]) -> bool:
    return any(phrase in command_lower for phrase in phrases)


TASK_READ_PHRASES = ("show tasks", "list tasks", "my tasks")
TASK_COMPLETE_PHRASES = ("complete task", "finish task", "done task")
TASK_DELETE_PHRASES = ("delete task", "remove task")
REMINDER_READ_PHRASES = ("show reminders", "list reminders", "my reminders")
REMINDER_COMPLETE_PHRASES = ("complete reminder", "done reminder")
REMINDER_DELETE_PHRASES = ("delete reminder", "remove reminder")


def normalize_agent_output(result: Any) -> str:
    if isinstance(result, dict):
        message = result.get("message")
        if message:
            return str(message).strip()
    if result is None:
        return ""
    return str(result).strip()


def _is_unusable_runtime_response(text: Optional[str]) -> bool:
    normalized = clean_response(text).strip().lower()
    if not normalized:
        return True
    if normalized == FALLBACK_USER_MESSAGE.strip().lower():
        return True
    if "couldn't generate a useful response" in normalized:
        return True
    if " is planned, but it is not available for live chat yet." in normalized:
        return True
    if " agent failed:" in normalized:
        return True
    return False


def _log_runtime_trace(
    *,
    raw_command: str,
    detected_intent: str,
    used_agents: List[str],
    provider_name: Optional[str],
    response_text: str,
    execution_mode: str,
) -> None:
    input_preview = _telemetry_excerpt(raw_command, limit=120)
    output_preview = _telemetry_excerpt(response_text, limit=160)
    agent_name = str((used_agents or [detected_intent or "general"])[0] or "general").strip().lower()
    provider_label = str(provider_name or "none").strip().lower() or "none"
    intent_label = str(detected_intent or "general").strip().lower() or "general"
    _emit_runtime_log(
        (
            f"[RUNTIME TRACE] input={input_preview} -> intent={intent_label} -> "
            f"agent={agent_name} -> provider={provider_label} -> "
            f"output={output_preview} (mode={execution_mode})"
        )
    )


def _log_blocked_placeholder_agent(agent_name: str) -> None:
    normalized = str(agent_name or "").strip().lower()
    if normalized:
        _emit_runtime_log(f"[AGENT ROUTING] blocked placeholder agent: {normalized}")


def _log_intent_agent_mapping(intent_name: str, agent_name: str) -> None:
    normalized_intent = str(intent_name or "").strip().lower()
    normalized_agent = str(agent_name or "").strip().lower()
    if normalized_intent and normalized_agent:
        _emit_runtime_log(
            f"[ROUTING] {normalized_intent} → {normalized_agent}",
            fallback=f"[ROUTING] {normalized_intent} -> {normalized_agent}",
        )


def _emit_runtime_log(message: str, fallback: Optional[str] = None) -> None:
    try:
        print(message)
    except UnicodeEncodeError:
        print(fallback or message.encode("ascii", "replace").decode("ascii"))


def _looks_like_write_request(raw_command: str) -> bool:
    normalized = str(raw_command or "").strip().lower()
    if not normalized:
        return False
    if resolve_document_request(raw_command) is not None:
        return False
    return bool(
        re.match(r"^(?:write|draft|compose)\b", normalized)
        or any(marker in normalized for marker in ("blog post", "article", "caption", "paragraph"))
    )


def _normalize_detected_intent(detected_intent: str, raw_command: str) -> str:
    normalized = str(detected_intent or "general").strip().lower() or "general"
    normalized = INTENT_ALIAS_MAP.get(normalized, normalized)
    if normalized == "document":
        return "document"
    if normalized == "general" and _looks_like_write_request(raw_command):
        return "write"
    return normalized


def _resolve_execution_agent_name(agent_name: str) -> str:
    normalized = str(agent_name or "").strip().lower()
    normalized = INTENT_ALIAS_MAP.get(normalized, normalized)
    return INTENT_TO_REAL_AGENT_MAP.get(normalized, normalized)


def _resolve_desktop_open_request(command: str) -> Optional[Dict[str, str]]:
    match = _DESKTOP_OPEN_COMMAND_RE.match(str(command or "").strip())
    if not match:
        return None
    target = str(match.group("target") or "").strip()
    if not target:
        return None
    # Try hardcoded list first, fall back to raw target for app_scanner
    app_name = normalize_application_name(target) or target.lower()
    return {
        "app_name": app_name,
        "label": get_application_label(app_name) or target.title(),
    }

def _sanitize_chat_orchestration(orchestration: Dict[str, Any]) -> Dict[str, Any]:
    safe_orchestration = dict(orchestration or {})
    primary_alias = str(safe_orchestration.get("primary_agent") or "general").strip().lower() or "general"
    execution_aliases = [
        str(agent or "").strip().lower()
        for agent in safe_orchestration.get("execution_order") or []
        if str(agent or "").strip()
    ]
    if primary_alias not in execution_aliases and primary_alias != "general":
        execution_aliases.insert(0, primary_alias)

    allowed_aliases: List[str] = []
    blocked_placeholders: List[str] = []
    seen_aliases = set()
    for alias in execution_aliases:
        if not alias or alias in seen_aliases:
            continue
        seen_aliases.add(alias)
        resolved_agent = _resolve_execution_agent_name(alias)
        if get_agent_capability_mode(resolved_agent) == "placeholder":
            blocked_placeholders.append(alias)
            _log_blocked_placeholder_agent(alias)
            continue
        if alias == "general" or resolved_agent in AGENT_ROUTER or is_chat_routable_agent(resolved_agent):
            allowed_aliases.append(alias)

    resolved_primary = _resolve_execution_agent_name(primary_alias)
    if get_agent_capability_mode(resolved_primary) == "placeholder":
        primary_agent = allowed_aliases[0] if allowed_aliases else "general"
    else:
        primary_agent = primary_alias

    if primary_agent != "general" and primary_agent not in allowed_aliases:
        resolved_primary = _resolve_execution_agent_name(primary_agent)
        if resolved_primary in AGENT_ROUTER or is_chat_routable_agent(resolved_primary):
            allowed_aliases.insert(0, primary_agent)

    secondary_agents = [agent for agent in allowed_aliases if agent != primary_agent]
    if primary_agent == "general":
        allowed_execution_order = []
    else:
        allowed_execution_order = [primary_agent] + [agent for agent in secondary_agents if agent != primary_agent]

    safe_orchestration["primary_agent"] = primary_agent
    safe_orchestration["secondary_agents"] = secondary_agents
    safe_orchestration["execution_order"] = allowed_execution_order
    safe_orchestration["requires_multiple"] = len(allowed_execution_order) > 1
    if blocked_placeholders:
        safe_orchestration["blocked_placeholders"] = blocked_placeholders
        original_reason = str(
            safe_orchestration.get("reason")
            or safe_orchestration.get("routing_reason")
            or ""
        ).strip()
        blocking_reason = "Placeholder agents are excluded from live chat routing."
        safe_orchestration["reason"] = f"{original_reason} {blocking_reason}".strip()
    return safe_orchestration


def store_and_learn(
    user_input: str,
    response: str,
    intent: str,
    extra_metadata: Optional[Dict[str, Any]] = None,
    session_id: str = "default",
    username: Optional[str] = None,
) -> None:
    scoped_username = str(username or "").strip()
    if scoped_username.lower() in {"", "guest", "public", "anonymous"}:
        # Public/local sessions should remain temporary. Until durable learning
        # stores carry owner metadata, do not persist them to global memory.
        return

    metadata = {"type": "user_input", "intent": intent}
    if extra_metadata:
        metadata.update(extra_metadata)
    metadata["session_id"] = str(session_id or "default")
    metadata["username"] = scoped_username

    try:
        process_interaction_memory(
            user_input,
            response,
            intent,
            float(metadata.get("confidence", 1.0)),
            session_id=str(session_id or "default"),
            username=scoped_username,
        )
    except Exception:
        pass

    store_memory(user_input, metadata)


def route_quiz_command(command: str) -> str:
    if "flashcard" in command.lower():
        return generate_flashcards(command)
    return generate_quiz(command)


def handle_task_command(command: str) -> str:
    command_lower = command.lower()
    task_id = extract_numeric_id(command)

    if any(phrase in command_lower for phrase in ("show tasks", "list tasks", "my tasks")):
        return get_tasks()

    if task_id and any(phrase in command_lower for phrase in ("complete task", "finish task", "done task")):
        return complete_task(task_id)

    if task_id and any(phrase in command_lower for phrase in ("delete task", "remove task")):
        return delete_task(task_id)

    add_match = re.search(r"(?:add task|task)\s+(.+)$", command, flags=re.IGNORECASE)
    if add_match:
        return add_task(add_match.group(1).strip())

    return plan_tasks(command)


def handle_reminder_command(command: str) -> str:
    command_lower = command.lower()
    reminder_id = extract_numeric_id(command)

    if any(phrase in command_lower for phrase in ("show reminders", "list reminders", "my reminders")):
        return normalize_agent_output(get_reminders())

    if reminder_id and any(phrase in command_lower for phrase in ("complete reminder", "done reminder")):
        return normalize_agent_output(complete_reminder(reminder_id))

    if reminder_id and any(phrase in command_lower for phrase in ("delete reminder", "remove reminder")):
        return normalize_agent_output(delete_reminder(reminder_id))

    add_match = re.search(r"remind me to\s+(.+)$", command, flags=re.IGNORECASE)
    if add_match:
        return normalize_agent_output(add_reminder(add_match.group(1).strip()))

    return normalize_agent_output(get_reminders())


def resolve_permission_action(
    command: str,
    detected_intent: str,
    orchestration: Dict[str, Any],
) -> str:
    command_lower = command.lower()
    primary_agent = (orchestration.get("primary_agent") or detected_intent or "general").strip().lower()
    safe_aliases = {
        "code": "coding",
        "coding_runtime": "coding",
        "content": "general",
        "email": "general",
        "fitness": "general",
        "write": "general",
        "writing_runtime": "general",
        "research_runtime": "general",
        "summary_runtime": "general",
        "document_generator": "document_generation",
        "document_retrieval": "document_generation",
        "transformation_engine": "document_generation",
        "desktop_controller": "desktop_launch",
    }

    if primary_agent == "task":
        if contains_phrase(command_lower, TASK_READ_PHRASES):
            return "task_read"
        if extract_numeric_id(command) and contains_phrase(command_lower, TASK_COMPLETE_PHRASES):
            return "task_complete"
        if extract_numeric_id(command) and contains_phrase(command_lower, TASK_DELETE_PHRASES):
            return "task_delete"
        if re.search(r"(?:add task|task)\s+(.+)$", command, flags=re.IGNORECASE):
            return "task_add"
        return "task_plan"

    if primary_agent == "reminder":
        if contains_phrase(command_lower, REMINDER_READ_PHRASES):
            return "reminder_read"
        if extract_numeric_id(command) and contains_phrase(command_lower, REMINDER_COMPLETE_PHRASES):
            return "reminder_complete"
        if extract_numeric_id(command) and contains_phrase(command_lower, REMINDER_DELETE_PHRASES):
            return "reminder_delete"
        if re.search(r"remind me to\s+(.+)$", command, flags=re.IGNORECASE):
            return "reminder_add"
        return "reminder_read"

    if primary_agent == "file":
        return "file_read"

    if primary_agent == "list_files":
        return "file_list"

    if primary_agent in {"insights", "memory"}:
        return "memory_read" if primary_agent == "memory" else "insights"

    return safe_aliases.get(primary_agent, primary_agent)


def build_agent_capability_cards(
    used_agents: List[str],
    detected_intent: str,
    orchestration: Dict[str, Any],
) -> List[Dict[str, Any]]:
    agent_ids = [agent_name for agent_name in used_agents if agent_name]
    if not agent_ids:
        primary_agent = orchestration.get("primary_agent") or detected_intent
        if primary_agent:
            agent_ids = [str(primary_agent)]
    return build_runtime_agent_cards(agent_ids)


AGENT_ROUTER: Dict[str, Callable[[str], str]] = {
    "weather": lambda cmd: normalize_agent_output(get_weather(cmd)),
    "news": lambda cmd: normalize_agent_output(get_news(cmd)),
    "math": lambda cmd: normalize_agent_output(solve_math(cmd)),
    "fitness": lambda cmd: normalize_agent_output(get_workout_plan(cmd)),
    "write": lambda cmd: normalize_agent_output(write_content(cmd, "general")),
    "writing_runtime": lambda cmd: normalize_agent_output(write_content(cmd, "general")),
    "translation": lambda cmd: normalize_agent_output(translate(cmd, extract_translation_target(cmd))),
    "research": lambda cmd: normalize_agent_output(research(cmd)),
    "research_runtime": lambda cmd: normalize_agent_output(research(cmd)),
    "study": lambda cmd: normalize_agent_output(study(cmd)),
    "code": lambda cmd: normalize_agent_output(code_help(cmd)),
    "coding_runtime": lambda cmd: normalize_agent_output(code_help(cmd)),
    "content": lambda cmd: normalize_agent_output(write_content(cmd, "blog")),
    "email": lambda cmd: normalize_agent_output(write_email(cmd, cmd)),
    "summarize": lambda cmd: normalize_agent_output(summarize_topic(cmd)),
    "summary_runtime": lambda cmd: normalize_agent_output(summarize_topic(cmd)),
    "grammar": lambda cmd: normalize_agent_output(check_grammar(cmd)),
    "quiz": route_quiz_command,
    "dictionary": lambda cmd: normalize_agent_output(define_word(cmd)),
    "synonyms": lambda cmd: normalize_agent_output(get_synonyms(cmd)),
    "web_search": lambda cmd: normalize_agent_output(web_search(cmd)),
    "youtube": lambda cmd: normalize_agent_output(search_youtube_topic(cmd)),
    "currency": lambda cmd: normalize_agent_output(convert_currency(*extract_currency_request(cmd))),
    "crypto": lambda cmd: normalize_agent_output(get_crypto_price("bitcoin")),
    "joke": lambda cmd: normalize_agent_output(get_joke()),
    "quote": lambda cmd: normalize_agent_output(get_quote()),
    "file": lambda cmd: normalize_agent_output(analyze_file(cmd)),
    "list_files": lambda cmd: normalize_agent_output(list_files(".")),
    "screenshot": lambda cmd: normalize_agent_output(take_screenshot()),
    "reasoning": lambda cmd: normalize_agent_output(reason(cmd)),
    "compare": lambda cmd: normalize_agent_output(compare(cmd)),
    "task": handle_task_command,
    "reminder": handle_reminder_command,
}


def research_summary_workflow(command: str) -> Dict[str, str]:
    research_result = normalize_agent_output(research(command))
    return {
        "research": research_result,
        "summarize": normalize_agent_output(summarize_text(research_result, summary_type="brief")),
    }


def email_grammar_workflow(command: str) -> Dict[str, str]:
    email_result = normalize_agent_output(write_email(command, command))
    return {
        "email": email_result,
        "grammar": normalize_agent_output(check_grammar(email_result)),
    }


WORKFLOW_HANDLERS: Dict[tuple[str, ...], Callable[[str], Dict[str, str]]] = {
    ("research", "summarize"): research_summary_workflow,
    ("email", "grammar"): email_grammar_workflow,
}


def handle_personal_memory(command: str) -> Optional[Dict[str, Any]]:
    cmd = command.lower().strip()

    normalized = re.sub(r"^(hi|hey|hello)\s+", "", cmd).strip()
    normalized = re.sub(r"^(no\s+i\s+mean\s+|i\s+mean\s+)", "", normalized).strip()

    name_match = re.search(r"\bmy name is\s+([a-zA-Z ]{1,40})$", normalized)
    if name_match:
        name = name_match.group(1).strip().title()
        return {
            "intent": "memory",
            "action_name": "memory_write",
            "operation": "store_name",
            "value": name,
        }

    if "what is my name" in normalized:
        return {
            "intent": "memory",
            "action_name": "memory_read",
            "operation": "read_name",
        }

    return None


def handle_special_intents(intent: str) -> Optional[str]:
    if intent == "time":
        return f"The current time is {datetime.now().strftime('%I:%M %p')}."

    if intent == "date":
        return f"Today's date is {datetime.now().strftime('%A, %d %B %Y')}."

    if intent == "identity":
        return (
        "I am VORIS, your Voice-Oriented Responsive Intelligence System. "
            "I help with research, coding, writing, planning, and agent-based task routing."
        )

    if intent == "insights":
        return "I don't have scoped personal insights for this session yet."

    return None


def handle_document_generation(
    raw_command: str,
    *,
    session_id: Optional[str] = None,
    owner_user_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    request = resolve_document_request(raw_command, session_id=session_id)
    if request is None:
        return None
    generated = generate_document(
        request.document_type,
        request.topic,
        request.export_format,
        formats=request.requested_formats,
        page_target=request.page_target,
        style=request.style,
        include_references=request.include_references,
        citation_style=request.citation_style,
    )
    if generated and generated.get("success"):
        generated = secure_generated_document_access(
            generated,
            owner_session_id=session_id,
            owner_user_id=owner_user_id,
        )
        remember_generated_document(session_id, generated)
    return generated


def handle_document_retrieval_followup(
    raw_command: str,
    *,
    session_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    return resolve_document_retrieval_followup(raw_command, session_id=session_id)


def _find_youtube_url_in_text(text: str) -> Optional[str]:
    match = _YOUTUBE_URL_RE.search(str(text or ""))
    return match.group(0) if match else None


def _detect_transformation_doc_type(command: str) -> str:
    lowered = command.lower()
    if re.search(r"\b(assignment)\b", lowered):
        return "assignment"
    return "notes"


def _extract_transformation_formats(command: str, doc_type: str) -> tuple[str, ...]:
    lowered = command.lower()
    format_map = (
        (r"\b(docx|word)\b", "docx"),
        (r"\b(pdf)\b", "pdf"),
        (r"\b(txt|text file|plain text)\b", "txt"),
        (r"\b(pptx|ppt|slides?|presentation)\b", "pptx"),
    )
    found = []
    for pattern, fmt in format_map:
        if re.search(pattern, lowered, flags=re.IGNORECASE) and fmt not in found:
            found.append(fmt)
    return normalize_document_formats(found or ["txt"])


def _extract_transformation_page_target(command: str) -> Optional[int]:
    match = re.search(r"\b(\d{1,2})\s*(?:page|pages)\b", command.lower())
    if not match:
        return None
    return max(1, min(int(match.group(1)), 20))


def _extract_transformation_style(command: str, doc_type: str) -> str:
    lowered = command.lower()
    for s in ("detailed", "simple", "professional"):
        if re.search(rf"\b{s}\b", lowered):
            return s
    return "simple" if doc_type == "notes" else "professional"


def _extract_transformation_references(command: str) -> bool:
    lowered = command.lower()
    return bool(re.search(r"\b(reference|references|bibliography|works cited|citations?)\b", lowered))


def _extract_transformation_citation_style(command: str) -> Optional[str]:
    lowered = command.lower()
    for style in ("apa", "mla", "chicago", "harvard", "ieee"):
        if re.search(rf"\b{style}\b", lowered):
            return style
    return None


def _extract_transformation_topic(command: str, source_label: str) -> str:
    topic_match = re.search(
        r"\b(?:on|about|for)\s+([^,\n]+?)(?:\s+from\b|\s+using\b|\s+based on\b|[,\n]|$)",
        command,
        flags=re.IGNORECASE,
    )
    if topic_match:
        candidate = topic_match.group(1).strip().rstrip(".,:;")
        if candidate.lower() not in {"this", "the", "my", "following", "it", "that"}:
            return candidate[:80]
    if source_label and source_label not in {"pasted text", "uploaded file", "text"}:
        clean = re.sub(r"\.\w+$", "", source_label).strip()
        if clean:
            return clean[:60]
    return "Source Material"


def _extract_inline_source_content(command: str) -> tuple[str, str]:
    """Split 'make notes from this: [content]' into (command_part, content_part)."""
    parts = _INLINE_CONTENT_SPLIT_RE.split(command, maxsplit=1)
    if len(parts) == 2 and len(parts[1].strip()) > 50:
        return parts[0].strip(), parts[1].strip()
    return command, ""


def handle_transformation(
    raw_command: str,
    *,
    source_content: Optional[str] = None,
    session_id: Optional[str] = None,
    owner_user_id: Optional[str] = None,
) -> Optional[Dict[str, Any]]:
    """
    Handle transformation requests: convert source material into structured documents.
    Supports YouTube URLs in the command, pasted inline content, or explicit source_content.
    Returns the same shape as generate_document(), or None if not a transformation request.
    """
    command = str(raw_command or "").strip()

    clean_command, inline_content = _extract_inline_source_content(command)
    if inline_content and not source_content:
        source_content = inline_content
        command = clean_command

    youtube_url = _find_youtube_url_in_text(command)
    has_source = bool(source_content) or bool(youtube_url)
    is_transform = bool(_TRANSFORMATION_TRIGGER_RE.search(command)) or bool(youtube_url)

    if not is_transform or not has_source:
        return None

    doc_type = _detect_transformation_doc_type(command)
    requested_formats = _extract_transformation_formats(command, doc_type)
    page_target = _extract_transformation_page_target(command)
    style = _extract_transformation_style(command, doc_type)
    include_references = _extract_transformation_references(command)
    citation_style = _extract_transformation_citation_style(command)

    if youtube_url:
        extracted = extract_content(youtube_url, source_type="youtube")
    else:
        extracted = extract_content(str(source_content), source_type="text")

    if not extracted.success or not extracted.text.strip():
        return None

    topic = _extract_transformation_topic(command, extracted.source_label)

    transformation_payload = generate_transformation_content_payload(
        extracted.text,
        doc_type,
        topic,
        page_target=page_target,
        style=style,
        include_references=include_references,
        citation_style=citation_style,
    )

    structured_content = transformation_payload.get("content") or extracted.text

    result = generate_document(
        doc_type,
        topic,
        formats=requested_formats,
        page_target=page_target,
        style=style,
        include_references=include_references,
        citation_style=citation_style,
        prebuilt_content=structured_content,
    )
    if result.get("success"):
        result = secure_generated_document_access(
            result,
            owner_session_id=session_id,
            owner_user_id=owner_user_id,
        )

    if session_id and result.get("success"):
        dr = DocumentRequest(
            document_type=doc_type,
            topic=topic,
            export_format=requested_formats[0],
            requested_formats=requested_formats,
            page_target=page_target,
            style=normalize_document_style(style),
            include_references=include_references,
            citation_style=normalize_citation_style(citation_style),
        )
        remember_document_request(session_id, dr)
        remember_generated_document(session_id, result)

    return result


def build_enhanced_input(raw_command: str, confidence: float) -> str:
    # The previous enhancer pulled from global vector learning memory with no
    # owner metadata. Keep this path identity-safe until scoped recall exists.
    enhanced_input = raw_command

    if should_add_low_confidence_note(confidence):
        enhanced_input += (
            "\n\nIntent confidence is low. "
            "Respond carefully, infer user meaning safely, and handle imperfect wording gracefully."
        )

    return enhanced_input


def should_prefer_conversational_path(raw_command: str, detected_intent: str, confidence: float) -> bool:
    normalized_command = str(raw_command or "").strip()
    if not normalized_command:
        return False

    normalized_intent = str(detected_intent or "general").strip().lower()
    if normalized_intent in CONVERSATIONAL_INTENTS:
        return True

    if normalized_intent == "general" and confidence < 0.55 and is_conversational_input(normalized_command):
        return True

    return False


def looks_like_direct_assistant_request(raw_command: str) -> bool:
    normalized_command = str(raw_command or "").strip().lower()
    if not normalized_command:
        return False
    if any(marker in normalized_command for marker in DIRECT_ASSISTANT_TOOL_MARKERS):
        return False
    if normalized_command.endswith("?"):
        return True
    return normalized_command.startswith(DIRECT_ASSISTANT_STARTERS)


def looks_like_general_comparison_request(raw_command: str) -> bool:
    normalized_command = str(raw_command or "").strip().lower()
    if not normalized_command:
        return False
    non_comparison_tool_markers = tuple(marker for marker in DIRECT_ASSISTANT_TOOL_MARKERS if marker != "compare ")
    if any(marker in normalized_command for marker in non_comparison_tool_markers):
        return False
    comparison_markers = ("compare ", " vs ", " versus ", "difference between")
    return any(marker in normalized_command for marker in comparison_markers)


def select_fast_assistant_route(raw_command: str, detected_intent: str, confidence: float) -> str:
    if should_prefer_conversational_path(raw_command, detected_intent, confidence):
        return "conversation"

    if should_use_live_web_search(raw_command, detected_intent, confidence):
        return ""

    normalized_intent = str(detected_intent or "general").strip().lower()
    if normalized_intent in {"write", "content"} and is_long_form_writing_request(raw_command):
        return "assistant"
    if normalized_intent == "general" and confidence < 0.55 and looks_like_direct_assistant_request(raw_command):
        return "assistant"
    if normalized_intent == "general" and looks_like_general_comparison_request(raw_command):
        return "assistant"

    return ""


def build_general_assistant_orchestration(raw_command: str, route_kind: str) -> Dict[str, Any]:
    reason = (
        f"Human-first conversational routing kept '{raw_command}' on the general assistant path."
        if route_kind == "conversation"
        else f"Direct assistant routing answered '{raw_command}' without unnecessary agent orchestration."
    )
    return {
        "primary_agent": "general",
        "secondary_agents": [],
        "execution_order": [],
        "requires_multiple": False,
        "primary_selection_source": f"{route_kind}_guard",
        "top_score": 0,
        "mode": route_kind,
        "reason": reason,
    }


def should_use_live_web_search(raw_command: str, detected_intent: str, confidence: float) -> bool:
    normalized_command = str(raw_command or "").strip().lower()
    normalized_intent = str(detected_intent or "general").strip().lower()
    if not normalized_command:
        return False

    if normalized_command in GREETING_INPUTS or is_conversational_input(normalized_command):
        return False

    if should_prefer_conversational_path(raw_command, detected_intent, confidence):
        return False

    if normalized_intent in WEB_SEARCH_SKIP_INTENTS:
        return False

    if any(marker in normalized_command for marker in DIRECT_ASSISTANT_TOOL_MARKERS):
        return False

    signal_hit = any(re.search(pattern, normalized_command, flags=re.IGNORECASE) for pattern in WEB_SEARCH_SIGNAL_PATTERNS)
    subject_hit = any(marker in normalized_command for marker in WEB_SEARCH_SUBJECT_MARKERS)

    if "latest" in normalized_command or "current" in normalized_command:
        return True

    if signal_hit and subject_hit:
        return True

    if any(token in normalized_command for token in ("price", "pricing", "version", "release", "status")):
        return True

    return False


def build_live_web_search_query(raw_command: str) -> str:
    query = str(raw_command or "").strip()
    query = re.sub(r"^(can you|could you|would you)\s+", "", query, flags=re.IGNORECASE)
    query = re.sub(r"^(please)\s+", "", query, flags=re.IGNORECASE)
    query = re.sub(r"\s+", " ", query).strip(" ,.?")
    return query


def build_web_search_orchestration(raw_command: str, search_query: str) -> Dict[str, Any]:
    return {
        "primary_agent": "web_search",
        "secondary_agents": [],
        "execution_order": ["web_search"],
        "requires_multiple": False,
        "primary_selection_source": "live_search_guard",
        "top_score": 1,
        "mode": "web_assistant",
        "reason": (
            f"Used live web search for '{raw_command}' because it appears time-sensitive or likely to change. "
            f"Search query: '{search_query}'."
        ),
    }


def run_agent(agent_name: str, raw_command: str) -> str:
    normalized_agent_name = str(agent_name or "").strip().lower()
    execution_agent = _resolve_execution_agent_name(normalized_agent_name)
    if execution_agent != normalized_agent_name:
        _log_intent_agent_mapping(normalized_agent_name, execution_agent)
    if get_agent_capability_mode(execution_agent) == "placeholder":
        _log_blocked_placeholder_agent(execution_agent)
        readable_name = str(execution_agent or "").replace("_", " ").strip().title() or "This agent"
        return f"{readable_name} is planned, but it is not available for live chat yet."
    try:
        return normalize_agent_output(AGENT_ROUTER[execution_agent](raw_command))
    except Exception as error:
        log_agent_error(execution_agent, str(error))
        return f"{execution_agent} agent failed: {str(error)}"


def should_use_orchestrated_agents(
    detected_intent: str,
    confidence: float,
    orchestration: Dict[str, Any],
) -> bool:
    primary_agent = _resolve_execution_agent_name(orchestration.get("primary_agent", "general"))
    selection_source = orchestration.get("primary_selection_source", "intent")

    if get_agent_capability_mode(primary_agent) == "placeholder":
        _log_blocked_placeholder_agent(primary_agent)
        return False

    if primary_agent not in AGENT_ROUTER:
        return False

    if selection_source == "keyword_scoring":
        return bool(orchestration.get("requires_multiple")) or orchestration.get("top_score", 0) >= 2

    return should_use_agent(primary_agent, confidence, AGENT_ROUTER) or should_use_agent(
        detected_intent,
        confidence,
        AGENT_ROUTER,
    )


def execute_orchestrated_agents(
    raw_command: str,
    detected_intent: str,
    confidence: float,
    orchestration: Dict[str, Any],
) -> tuple[str, List[str], str]:
    if not should_use_orchestrated_agents(detected_intent, confidence, orchestration):
        return "", [], "fallback_llm"

    execution_order = []
    for agent_name in orchestration.get("execution_order", []):
        resolved_agent_name = _resolve_execution_agent_name(agent_name)
        if resolved_agent_name != str(agent_name or "").strip().lower():
            _log_intent_agent_mapping(str(agent_name or "").strip().lower(), resolved_agent_name)
        if get_agent_capability_mode(resolved_agent_name) == "placeholder":
            _log_blocked_placeholder_agent(resolved_agent_name)
            continue
        if resolved_agent_name in AGENT_ROUTER and resolved_agent_name not in execution_order:
            execution_order.append(resolved_agent_name)

    if not execution_order:
        primary_agent = _resolve_execution_agent_name(orchestration.get("primary_agent", "general"))
        if get_agent_capability_mode(primary_agent) == "placeholder":
            _log_blocked_placeholder_agent(primary_agent)
            return "", [], "fallback_llm"
        if primary_agent in AGENT_ROUTER:
            execution_order = [primary_agent]

    if not execution_order:
        return "", [], "fallback_llm"

    workflow_key = tuple(execution_order[:2])
    if len(execution_order) > 1 and workflow_key in WORKFLOW_HANDLERS:
        responses = WORKFLOW_HANDLERS[workflow_key](raw_command)
    else:
        responses = {agent_name: run_agent(agent_name, raw_command) for agent_name in execution_order}

    synthesis = master_orchestrator.synthesize_responses(raw_command, responses)
    mode = "multi_agent" if len(responses) > 1 else "single_agent"
    return synthesis.get("response", ""), list(responses.keys()), mode


def build_plan_steps(raw_command: str, intent: str, confidence: float, orchestration: Dict[str, Any]) -> List[str]:
    deterministic_plan = summarize_execution_plan(raw_command)
    if deterministic_plan:
        return deterministic_plan[:8]

    if should_plan(intent, confidence):
        try:
            plan_text = create_plan(raw_command)
            if isinstance(plan_text, str):
                parsed = parse_plan_to_steps(plan_text)
                if parsed:
                    return parsed[:8]
            if isinstance(plan_text, list):
                parsed = [str(step).strip() for step in plan_text if str(step).strip()]
                if parsed:
                    return parsed[:8]
        except Exception as error:
            log_failure(raw_command, f"Planning failed: {str(error)}")

    execution_order = [
        agent_name.replace("_", " ").title()
        for agent_name in orchestration.get("execution_order", [])
        if agent_name and agent_name != "general"
    ]

    if not execution_order:
        return []

    steps = [f"Route request to {execution_order[0]}"]
    steps.extend(f"Support with {agent_name}" for agent_name in execution_order[1:])
    steps.append("Synthesize and deliver the final response")
    return steps


def maybe_execute_web_search_answer(
    *,
    raw_command: str,
    detected_intent: str,
    confidence: float,
    language: str,
    permission_action: str,
    permission: Dict[str, Any],
    session_id: str = "runtime",
    username: Optional[str] = None,
    telemetry: ProcessingTelemetry,
    publish_telemetry: bool,
) -> Optional[Dict[str, Any]]:
    if not should_use_live_web_search(raw_command, detected_intent, confidence):
        return None

    search_query = build_live_web_search_query(raw_command)
    if not search_query:
        return None

    orchestration = build_web_search_orchestration(raw_command, search_query)
    routing_started = time.perf_counter()
    telemetry.record_routing(
        agent_selected="web_search",
        reason=orchestration["reason"],
        trust_level="safe",
        time_ms=(time.perf_counter() - routing_started) * 1000,
    )

    execution_started = time.perf_counter()
    search_result = web_search(search_query)
    if not search_result.get("success"):
        telemetry.record_execution(
            "web_search",
            search_result.get("message") or "Live web search did not return usable results.",
            False,
            (time.perf_counter() - execution_started) * 1000,
        )
        return None

    provider_payload = generate_web_search_response_payload(
        raw_command,
        search_result,
        max_tokens=DEFAULT_MAX_TOKENS,
        temperature=DEFAULT_TEMPERATURE,
    )
    provider_name = str(provider_payload.get("provider") or "").strip() or None
    provider_model = str(provider_payload.get("model") or "").strip() or None
    providers_tried = list(provider_payload.get("providers_tried") or [])

    if provider_name or provider_model or providers_tried:
        telemetry.record_provider(
            provider_name or "web_assistant",
            provider_model or "unknown",
            provider_payload.get("tokens_used"),
            provider_payload.get("latency_ms") or 0.0,
            success=bool(provider_payload.get("success")),
            error=provider_payload.get("error"),
        )

    response_text = str(
        provider_payload.get("content")
        or provider_payload.get("degraded_reply")
        or search_result.get("message")
        or ""
    ).strip()
    execution_mode = "web_assistant" if provider_payload.get("success") else "web_assistant_fallback"
    telemetry.record_execution(
        "web_search",
        response_text or "Live web answer generation returned no content.",
        bool(response_text),
        (time.perf_counter() - execution_started) * 1000,
    )
    if not response_text:
        return None

    result = build_result(
        raw_command=raw_command,
        detected_intent=detected_intent,
        confidence=confidence,
        response=response_text,
        language=language,
        orchestration=orchestration,
        used_agents=["web_search"],
        execution_mode=execution_mode,
        plan_steps=[],
        permission_action=permission_action,
        permission=permission,
        provider_name=provider_name,
        provider_model=provider_model,
        providers_tried=providers_tried,
        session_id=session_id,
        username=username,
        telemetry=telemetry,
        publish_telemetry=publish_telemetry,
    )
    result["web_search"] = {
        "used": True,
        "query": search_query,
        "source": search_result.get("source") or "live_search",
        "live_data": bool(search_result.get("live_data")),
    }
    result["explanation_mode"] = provider_payload.get("explanation_mode")
    return result


def build_result(
    *,
    raw_command: str,
    detected_intent: str,
    confidence: float,
    response: str,
    language: str,
    orchestration: Dict[str, Any],
    used_agents: List[str],
    execution_mode: str,
    plan_steps: Optional[List[str]] = None,
    permission_action: Optional[str] = None,
    permission: Optional[Dict[str, Any]] = None,
    provider_name: Optional[str] = None,
    provider_model: Optional[str] = None,
    providers_tried: Optional[List[str]] = None,
    session_id: str = "runtime",
    username: Optional[str] = None,
    telemetry: Optional[ProcessingTelemetry] = None,
    publish_telemetry: bool = True,
) -> Dict[str, Any]:
    raw_response = clean_response(response)
    effective_execution_mode = execution_mode
    effective_provider_name = provider_name
    effective_provider_model = provider_model
    effective_providers_tried = list(providers_tried or [])

    if execution_mode == "document_generation" and not raw_response:
        raw_response = "Your document is ready."
    elif execution_mode == "permission_blocked" and not raw_response:
        raw_response = str((permission or {}).get("permission", {}).get("reason") or "This action is protected.")

    if _is_unusable_runtime_response(raw_response):
        raw_response = build_degraded_reply(raw_command, effective_providers_tried)
        effective_execution_mode = "degraded_assistant"
        effective_provider_name = None
        effective_provider_model = None

    try:
        translated_response = clean_response(respond_in_language(raw_response, language))
    except Exception:
        translated_response = clean_response(raw_response)

    if _is_unusable_runtime_response(translated_response):
        translated_response = build_degraded_reply(raw_command, effective_providers_tried)
        effective_execution_mode = "degraded_assistant"
        effective_provider_name = None
        effective_provider_model = None

    final_intent = detected_intent if detected_intent != "general" else orchestration.get("primary_agent", "general")
    agent_capabilities = build_agent_capability_cards(used_agents, final_intent, orchestration)
    confidence_detail = evaluate_confidence(raw_command).to_dict()

    store_and_learn(
        raw_command,
        translated_response,
        final_intent,
        extra_metadata={
            "confidence": round(confidence, 4),
            "used_agents": used_agents,
            "execution_mode": effective_execution_mode,
            "plan_steps": plan_steps or [],
        },
        session_id=session_id,
        username=username,
    )
    try:
        update_context_from_command(
            raw_command,
            agent=used_agents[0] if used_agents else final_intent,
        )
        record_reflection(
            requested_action=detected_intent,
            actual_action=final_intent,
            success=effective_execution_mode != "degraded_assistant",
            blocked_by_permission=False,
            retry_possible=effective_execution_mode == "degraded_assistant",
            learning_signal="successful_runtime_path" if effective_execution_mode != "degraded_assistant" else "runtime_response_hardened_to_degraded_reply",
        )
    except Exception:
        pass

    try:
        record_execution_result(
            permission_action or final_intent,
            session_id=session_id,
            username=username,
            success=effective_execution_mode not in {"degraded_assistant", "permission_blocked"},
            trust_level=get_trust_level(permission_action).value if permission_action else "safe",
            reason=effective_execution_mode,
            meta={"layer": "runtime_core", "used_agents": used_agents},
        )
    except Exception:
        pass

    _log_runtime_trace(
        raw_command=raw_command,
        detected_intent=str(final_intent or detected_intent or "general"),
        used_agents=used_agents,
        provider_name=effective_provider_name,
        response_text=translated_response,
        execution_mode=effective_execution_mode,
    )

    payload = {
        "intent": final_intent,
        "detected_intent": detected_intent,
        "confidence": confidence,
        "response": translated_response,
        "plan": plan_steps or [],
        "used_agents": used_agents,
        "agent_capabilities": agent_capabilities,
        "execution_mode": effective_execution_mode,
        "decision": build_decision_summary(detected_intent, confidence, AGENT_ROUTER),
        "orchestration": orchestration,
        "language": language,
        "confidence_detail": confidence_detail,
        "permission_action": permission_action,
        "permission": permission,
        "provider": effective_provider_name,
        "model": effective_provider_model,
        "providers_tried": effective_providers_tried,
        "degraded": effective_execution_mode == "degraded_assistant",
    }
    payload["action_trace"] = build_action_trace(
        request_id=new_request_id("runtime"),
        raw_input=raw_command,
        intent=str(final_intent or detected_intent or "general"),
        provider=effective_provider_name,
        permission=permission,
        execution_mode=effective_execution_mode,
        used_agents=used_agents,
        degraded=effective_execution_mode == "degraded_assistant",
        success=effective_execution_mode not in {"degraded_assistant", "permission_blocked"},
        status=effective_execution_mode,
        source=payload,
    )
    return _with_telemetry(payload, telemetry, publish=publish_telemetry)


def _runtime_identity(security_context: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    context = dict(security_context or {})
    return {
        "username": str(context.get("username") or "").strip() or None,
        "user_id": str(context.get("user_id") or "").strip() or None,
        "session_token": str(context.get("session_token") or "").strip() or None,
        "confirmed": bool(context.get("confirmed", False)),
        "pin": str(context.get("pin") or "").strip() or None,
        "otp": str(context.get("otp") or "").strip() or None,
        "otp_token": str(context.get("otp_token") or "").strip() or None,
        "resource_id": str(context.get("resource_id") or "").strip() or None,
    }


def _permission_status_from_access(status: Optional[str]) -> str:
    normalized = str(status or "").strip().lower()
    status_map = {
        "confirm": "needs_confirmation",
        "session_approval": "needs_session_approval",
        "pin": "needs_pin",
    }
    return status_map.get(normalized, normalized or "approved")


def _permission_payload_from_access(action_name: str, access: Dict[str, Any]) -> Dict[str, Any]:
    decision = dict(access.get("decision") or {})
    trust_level = str(access.get("trust_level") or decision.get("trust_level") or get_trust_level(action_name))
    approval_type = str(
        access.get("approval_type")
        or decision.get("approval_type")
        or build_permission_response(action_name).get("permission", {}).get("approval_type")
        or "none"
    )
    required_action = str(access.get("required_action") or "").strip().lower()
    if not required_action:
        required_action = (
            "allow" if access.get("allowed") else
            _permission_status_from_access(access.get("status")).replace("needs_", "")
        )
    next_step_hint = str(access.get("next_step_hint") or "").strip()
    permission_payload = {
        "action_name": action_name,
        "trust_level": trust_level,
        "approval_type": approval_type,
        "reason": str(access.get("reason") or decision.get("reason") or ""),
        "required_action": required_action,
        "next_step_hint": next_step_hint,
        "requires_approval": approval_type != "none",
    }
    for key, value in decision.items():
        if permission_payload.get(key) is None and value is not None:
            permission_payload[key] = value
    return {
        "success": bool(access.get("allowed")),
        "status": "approved" if access.get("allowed") else _permission_status_from_access(access.get("status")),
        "mode": "real",
        "permission": permission_payload,
        "enforcement": access,
    }


def _enforce_runtime_permission(
    action_name: str,
    *,
    session_id: Optional[str],
    security_context: Optional[Dict[str, Any]],
    require_auth: bool = True,
    resource_id: Optional[str] = None,
) -> Dict[str, Any]:
    identity = _runtime_identity(security_context)
    # Route through the canonical permission_engine entry point so every
    # privileged runtime action lands in the same audit path. The engine
    # delegates to enforce_action for the actual OTP / PIN / lock logic.
    decision = check_permission(
        action_name,
        identity["session_token"],
        {
            "username": identity["username"],
            "user_id": identity["user_id"],
            "session_id": session_id or "runtime",
            "session_token": identity["session_token"],
            "confirmed": identity["confirmed"],
            "pin": identity["pin"],
            "otp": identity["otp"],
            "otp_token": identity["otp_token"],
            "resource_id": resource_id or identity["resource_id"],
            "require_auth": require_auth,
            "meta": {"layer": "runtime_core", "stage": "pre_execution"},
        },
    )
    access = decision.get("enforcement") or {}
    return _permission_payload_from_access(action_name, access)


def process_single_command_detailed(
    command: str,
    telemetry: Optional[ProcessingTelemetry] = None,
    *,
    publish_telemetry: bool = True,
    session_id: Optional[str] = None,
    security_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    active_telemetry = telemetry or ProcessingTelemetry()
    security_context = dict(security_context or {})
    runtime_session_id = session_id or "runtime"
    runtime_identity = _runtime_identity(security_context)
    runtime_username = runtime_identity.get("username")
    runtime_personal_context = (
        security_context.get("personal_context")
        if isinstance(security_context.get("personal_context"), dict)
        else None
    )
    raw_input = str(command or "")
    understanding_started = time.perf_counter()
    raw_command = clean_user_input(command)
    entities = parse_entities(raw_command).to_dict()
    active_telemetry.record_understanding(
        raw_input=raw_input,
        normalized=raw_command,
        entities=entities,
        time_ms=(time.perf_counter() - understanding_started) * 1000,
    )
    command_lower = raw_command.lower()

    if not raw_command:
        permission = _enforce_runtime_permission(
            "general",
            session_id=runtime_session_id,
            security_context=security_context,
            require_auth=False,
        )
        active_telemetry.record_intent("general", 0.0, [], 0.0)
        active_telemetry.record_routing("general", "No message was provided.", "safe", 0.0)
        active_telemetry.record_execution("general", "Please type something.", False, 0.0)
        return _with_telemetry({
            "intent": "general",
            "detected_intent": "general",
            "confidence": 0.0,
            "response": "Please type something.",
            "plan": [],
            "used_agents": [],
            "agent_capabilities": build_runtime_agent_cards(["general"]),
            "execution_mode": "empty",
            "decision": build_decision_summary("general", 0.0, AGENT_ROUTER),
            "orchestration": master_orchestrator.analyze_task("", intent="general"),
            "language": "english",
            "permission_action": "general",
            "permission": permission,
        }, active_telemetry, publish=publish_telemetry)

    if command_lower in GREETING_INPUTS:
        permission = _enforce_runtime_permission(
            "general",
            session_id=runtime_session_id,
            security_context=security_context,
            require_auth=False,
        )
        display_name = ""
        if runtime_personal_context:
            display_name = str(runtime_personal_context.get("display_name") or "").strip()
        response = f"Hey {display_name}. I'm here." if display_name else "Hey. I'm here."
        active_telemetry.record_intent("greeting", 1.0, [], 0.0)
        active_telemetry.record_routing("general", "Greeting shortcut matched a known greeting input.", "safe", 0.0)
        active_telemetry.record_execution("general", response, True, 0.0)
        store_and_learn(raw_command, response, "greeting", session_id=runtime_session_id, username=runtime_username)
        return _with_telemetry({
            "intent": "greeting",
            "detected_intent": "greeting",
            "confidence": 1.0,
            "response": response,
            "plan": [],
            "used_agents": ["general"],
            "agent_capabilities": build_runtime_agent_cards(["general"]),
            "execution_mode": "greeting",
            "decision": build_decision_summary("greeting", 1.0, AGENT_ROUTER),
            "orchestration": master_orchestrator.analyze_task(raw_command, intent="general"),
            "language": "english",
            "permission_action": "general",
            "permission": permission,
        }, active_telemetry, publish=publish_telemetry)

    memory_response = handle_personal_memory(raw_command)
    if memory_response:
        memory_action = str(memory_response.get("action_name") or "memory_read")
        memory_permission = _enforce_runtime_permission(
            memory_action,
            session_id=runtime_session_id,
            security_context=security_context,
            require_auth=True,
        )
        active_telemetry.record_intent(str(memory_response.get("intent") or "memory"), 1.0, [], 0.0)
        active_telemetry.record_routing(
            "memory",
            "Personal memory handler matched the request.",
            str((memory_permission.get("permission") or {}).get("trust_level") or "private"),
            0.0,
        )
        if not memory_permission.get("success"):
            reason = str((memory_permission.get("permission") or {}).get("reason") or "Permission required.")
            active_telemetry.record_execution("memory", reason, False, 0.0)
            return _with_telemetry({
                "intent": "permission",
                "detected_intent": "memory",
                "confidence": 1.0,
                "response": reason,
                "plan": [],
                "used_agents": ["memory"],
                "agent_capabilities": build_runtime_agent_cards(["memory"]),
                "execution_mode": "permission_blocked",
                "decision": build_decision_summary("memory", 1.0, AGENT_ROUTER),
                "orchestration": master_orchestrator.analyze_task(raw_command, intent="memory"),
                "language": "english",
                "permission_action": memory_action,
                "permission": memory_permission,
            }, active_telemetry, publish=publish_telemetry)

        memory_operation = str(memory_response.get("operation") or "")
        memory_profile = {"username": runtime_username} if runtime_username else {}
        if memory_operation == "store_name":
            name = str(memory_response.get("value") or "").strip()
            remember_explicit_personal_signals(
                f"call me {name}",
                session_id=runtime_session_id,
                user_profile=memory_profile,
            )
            final_memory_response = f"Nice to meet you {name}!"
        else:
            name = get_personal_display_name(memory_profile, session_id=runtime_session_id)
            final_memory_response = f"Your name is {name}." if name else "I don't know your name yet."

        active_telemetry.record_execution("memory", final_memory_response, True, 0.0)
        store_and_learn(raw_command, final_memory_response, "memory", session_id=runtime_session_id, username=runtime_username)
        return _with_telemetry({
            "intent": "memory",
            "detected_intent": "memory",
            "confidence": 1.0,
            "response": final_memory_response,
            "plan": [],
            "used_agents": ["memory"],
            "agent_capabilities": build_runtime_agent_cards(["memory"]),
            "execution_mode": "memory",
            "decision": build_decision_summary("general", 1.0, AGENT_ROUTER),
            "orchestration": master_orchestrator.analyze_task(raw_command, intent="general"),
            "language": "english",
            "permission_action": memory_action,
            "permission": memory_permission,
        }, active_telemetry, publish=publish_telemetry)

    retrieval_result = handle_document_retrieval_followup(raw_command, session_id=runtime_session_id)
    if retrieval_result is not None:
        reply = str(retrieval_result.get("message") or "Here is your document.")
        permission = _enforce_runtime_permission(
            "document_generation",
            session_id=runtime_session_id,
            security_context=security_context,
            require_auth=False,
        )
        active_telemetry.record_intent("document", 1.0, [], 0.0)
        active_telemetry.record_routing(
            "document_retrieval",
            "Follow-up retrieval matched a cached document; skipped LLM.",
            "safe",
            0.0,
        )
        active_telemetry.record_execution("document_retrieval", reply, True, 0.0)
        result = build_result(
            raw_command=raw_command,
            detected_intent="document",
            confidence=1.0,
            response=reply,
            language="english",
            orchestration={
                "primary_agent": "document_retrieval",
                "secondary_agents": [],
                "execution_order": ["document_retrieval"],
                "requires_multiple": False,
                "primary_selection_source": "document_retrieval_followup",
                "mode": "real",
                "reason": "Follow-up retrieval served a previously generated document from session memory.",
            },
            used_agents=["document_retrieval"],
            execution_mode="document_retrieval",
            plan_steps=[],
            permission_action="document_generation",
            permission=permission,
            provider_name=retrieval_result.get("provider"),
            provider_model=retrieval_result.get("model"),
            providers_tried=retrieval_result.get("providers_tried") or [],
            session_id=runtime_session_id,
            username=runtime_username,
            telemetry=active_telemetry,
            publish_telemetry=publish_telemetry,
        )
        result["download_url"] = retrieval_result.get("download_url")
        result["file_name"] = retrieval_result.get("file_name")
        result["file_path"] = retrieval_result.get("file_path")
        result["document_type"] = retrieval_result.get("document_type")
        result["document_format"] = retrieval_result.get("format")
        result["page_target"] = retrieval_result.get("page_target")
        result["document_topic"] = retrieval_result.get("topic")
        result["document_source"] = retrieval_result.get("source")
        result["document_delivery"] = retrieval_result.get("document_delivery")
        result["alternate_format_links"] = retrieval_result.get("alternate_format_links") or {}
        result["format_links"] = retrieval_result.get("format_links") or {}
        result["available_formats"] = retrieval_result.get("available_formats") or []
        result["document_files"] = retrieval_result.get("files") or []
        result["requested_formats"] = retrieval_result.get("requested_formats") or []
        result["document_style"] = retrieval_result.get("style")
        result["include_references"] = retrieval_result.get("include_references")
        result["citation_style"] = retrieval_result.get("citation_style")
        result["document_title"] = retrieval_result.get("title")
        result["document_subtitle"] = retrieval_result.get("subtitle")
        result["document_preview"] = retrieval_result.get("preview_text")
        result["retrieval_followup"] = True
        return result

    document_result = handle_document_generation(
        raw_command,
        session_id=runtime_session_id,
        owner_user_id=runtime_identity.get("user_id"),
    )
    if document_result is not None:
        _log_intent_agent_mapping("generate document", "document_generator")
        reply = str(document_result.get("message") or "Your document is ready.")
        execution_time_ms = 0.0
        permission = _enforce_runtime_permission(
            "document_generation",
            session_id=runtime_session_id,
            security_context=security_context,
            require_auth=False,
        )
        active_telemetry.record_intent("document", 1.0, [], 0.0)
        active_telemetry.record_routing(
            "document_generator",
            "Document request matched the notes or assignment generation path.",
            "safe",
            0.0,
        )
        active_telemetry.record_execution("document_generator", reply, True, execution_time_ms)
        result = build_result(
            raw_command=raw_command,
            detected_intent="document",
            confidence=1.0,
            response=reply,
            language="english",
            orchestration={
                "primary_agent": "document_generator",
                "secondary_agents": [],
                "execution_order": ["document_generator"],
                "requires_multiple": False,
                "primary_selection_source": "document_request_guard",
                "mode": "real",
                "reason": "Document generation request was routed directly to the document generator.",
            },
            used_agents=["document_generator"],
            execution_mode="document_generation",
            plan_steps=[],
            permission_action="document_generation",
            permission=permission,
            provider_name=document_result.get("provider"),
            provider_model=document_result.get("model"),
            providers_tried=document_result.get("providers_tried") or [],
            session_id=runtime_session_id,
            username=runtime_username,
            telemetry=active_telemetry,
            publish_telemetry=publish_telemetry,
        )
        result["download_url"] = document_result.get("download_url")
        result["file_name"] = document_result.get("file_name")
        result["file_path"] = document_result.get("file_path")
        result["document_type"] = document_result.get("document_type")
        result["document_format"] = document_result.get("format")
        result["page_target"] = document_result.get("page_target")
        result["document_topic"] = document_result.get("topic")
        result["document_source"] = document_result.get("source")
        result["document_delivery"] = document_result.get("document_delivery")
        result["alternate_format_links"] = document_result.get("alternate_format_links") or {}
        result["format_links"] = document_result.get("format_links") or {}
        result["available_formats"] = document_result.get("available_formats") or []
        result["document_files"] = document_result.get("files") or []
        result["requested_formats"] = document_result.get("requested_formats") or []
        result["document_style"] = document_result.get("style")
        result["include_references"] = document_result.get("include_references")
        result["citation_style"] = document_result.get("citation_style")
        result["document_title"] = document_result.get("title")
        result["document_subtitle"] = document_result.get("subtitle")
        result["document_preview"] = document_result.get("preview_text")
        return result

    transformation_result = handle_transformation(
        raw_command,
        session_id=runtime_session_id,
        owner_user_id=runtime_identity.get("user_id"),
    )
    if transformation_result is not None:
        reply = str(transformation_result.get("message") or "Your transformed document is ready.")
        permission = _enforce_runtime_permission(
            "document_generation",
            session_id=runtime_session_id,
            security_context=security_context,
            require_auth=False,
        )
        active_telemetry.record_intent("transformation", 1.0, [], 0.0)
        active_telemetry.record_routing(
            "transformation_engine",
            "Transformation request routed to content extractor and document generator.",
            "safe",
            0.0,
        )
        active_telemetry.record_execution("transformation_engine", reply, True, 0.0)
        result = build_result(
            raw_command=raw_command,
            detected_intent="transformation",
            confidence=1.0,
            response=reply,
            language="english",
            orchestration={
                "primary_agent": "transformation_engine",
                "secondary_agents": [],
                "execution_order": ["transformation_engine"],
                "requires_multiple": False,
                "primary_selection_source": "transformation_guard",
                "mode": "real",
                "reason": "Source content transformation routed directly to the transformation engine.",
            },
            used_agents=["transformation_engine"],
            execution_mode="document_transformation",
            plan_steps=[],
            permission_action="document_generation",
            permission=permission,
            provider_name=transformation_result.get("provider"),
            provider_model=transformation_result.get("model"),
            providers_tried=transformation_result.get("providers_tried") or [],
            session_id=runtime_session_id,
            username=runtime_username,
            telemetry=active_telemetry,
            publish_telemetry=publish_telemetry,
        )
        result["download_url"] = transformation_result.get("download_url")
        result["file_name"] = transformation_result.get("file_name")
        result["file_path"] = transformation_result.get("file_path")
        result["document_type"] = transformation_result.get("document_type")
        result["document_format"] = transformation_result.get("format")
        result["page_target"] = transformation_result.get("page_target")
        result["document_topic"] = transformation_result.get("topic")
        result["document_source"] = transformation_result.get("source")
        result["document_delivery"] = transformation_result.get("document_delivery")
        result["alternate_format_links"] = transformation_result.get("alternate_format_links") or {}
        result["format_links"] = transformation_result.get("format_links") or {}
        result["available_formats"] = transformation_result.get("available_formats") or []
        result["document_files"] = transformation_result.get("files") or []
        result["requested_formats"] = transformation_result.get("requested_formats") or []
        result["document_style"] = transformation_result.get("style")
        result["include_references"] = transformation_result.get("include_references")
        result["citation_style"] = transformation_result.get("citation_style")
        result["document_title"] = transformation_result.get("title")
        result["document_subtitle"] = transformation_result.get("subtitle")
        result["document_preview"] = transformation_result.get("preview_text")
        return result

    desktop_request = _resolve_desktop_open_request(raw_command)
    if desktop_request is not None:
        _log_intent_agent_mapping("open", "desktop_controller")
        permission = _enforce_runtime_permission(
            "desktop_launch",
            session_id=runtime_session_id,
            security_context=security_context,
            require_auth=False,
        )
        if not permission.get("success"):
            reason = str((permission.get("permission") or {}).get("reason") or "This action is protected.")
            active_telemetry.record_intent("desktop_open", 1.0, [], 0.0)
            active_telemetry.record_routing("desktop_controller", "Desktop launch matched a supported application.", "safe", 0.0)
            active_telemetry.record_execution("desktop_controller", reason, False, 0.0)
            return _with_telemetry({
                "intent": "permission",
                "detected_intent": "desktop_open",
                "confidence": 1.0,
                "response": reason,
                "plan": [],
                "used_agents": ["desktop_controller"],
                "agent_capabilities": build_runtime_agent_cards(["desktop_controller"]),
                "execution_mode": "permission_blocked",
                "decision": build_decision_summary("desktop_open", 1.0, AGENT_ROUTER),
                "orchestration": {
                    "primary_agent": "desktop_controller",
                    "secondary_agents": [],
                    "execution_order": ["desktop_controller"],
                    "requires_multiple": False,
                    "primary_selection_source": "desktop_open_guard",
                    "mode": "real",
                    "reason": "Desktop launch request matched a supported application, but permission was blocked.",
                },
                "language": "english",
                "permission_action": "desktop_launch",
                "permission": permission,
                "desktop_app": desktop_request["app_name"],
            }, active_telemetry, publish=publish_telemetry)

        launch_started = time.perf_counter()
        desktop_result = open_application(desktop_request["app_name"])
        execution_time_ms = (time.perf_counter() - launch_started) * 1000
        reply = str(desktop_result.get("message") or "I can't open that yet.")
        active_telemetry.record_intent("desktop_open", 1.0, [], 0.0)
        active_telemetry.record_routing(
            "desktop_controller",
            f"Desktop launch matched the supported app '{desktop_request['app_name']}'.",
            "safe",
            0.0,
        )
        active_telemetry.record_execution(
            "desktop_controller",
            reply,
            bool(desktop_result.get("success")),
            execution_time_ms,
        )
        result = build_result(
            raw_command=raw_command,
            detected_intent="desktop_open",
            confidence=1.0,
            response=reply,
            language="english",
            orchestration={
                "primary_agent": "desktop_controller",
                "secondary_agents": [],
                "execution_order": ["desktop_controller"],
                "requires_multiple": False,
                "primary_selection_source": "desktop_open_guard",
                "mode": "real",
                "reason": "Desktop launch request was routed directly to the desktop controller.",
            },
            used_agents=["desktop_controller"],
            execution_mode="external_desktop",
            plan_steps=[],
            permission_action="desktop_launch",
            permission=permission,
            session_id=runtime_session_id,
            username=runtime_username,
            telemetry=active_telemetry,
            publish_telemetry=publish_telemetry,
        )
        result["desktop_app"] = desktop_result.get("app_name")
        result["desktop_label"] = desktop_result.get("label")
        result["desktop_launch_status"] = desktop_result.get("status")
        result["desktop_launch_success"] = bool(desktop_result.get("success"))
        result["desktop_launched_with"] = desktop_result.get("launched_with")
        result["desktop_pid"] = desktop_result.get("pid")
        result["error"] = desktop_result.get("error")
        return result

    language = detect_language(raw_command)

    intent_started = time.perf_counter()
    detected_intent, confidence = detect_intent_with_confidence(raw_command)
    detected_intent = _normalize_detected_intent(detected_intent, raw_command)
    confidence_detail = evaluate_confidence(raw_command).to_dict()
    alternatives = [
        {
            "intent": item.get("intent"),
            "score": item.get("score"),
            "matched_rules": item.get("matched_rules", []),
        }
        for item in (confidence_detail.get("candidates") or [])[:3]
    ]
    active_telemetry.record_intent(
        primary_intent=detected_intent,
        confidence=confidence,
        alternatives=alternatives,
        time_ms=(time.perf_counter() - intent_started) * 1000,
    )

    fast_assistant_route = select_fast_assistant_route(raw_command, detected_intent, confidence)
    print(
        "[RUNTIME ROUTE]",
        {
            "intent": detected_intent,
            "confidence": round(confidence, 4),
            "fast_assistant_route": fast_assistant_route or "none",
        },
    )

    if fast_assistant_route:
        routing_started = time.perf_counter()
        orchestration = build_general_assistant_orchestration(raw_command, fast_assistant_route)
        permission_action = "general"
        permission = _enforce_runtime_permission(
            permission_action,
            session_id=runtime_session_id,
            security_context=security_context,
            require_auth=False,
        )
        active_telemetry.record_routing(
            agent_selected="general",
            reason=orchestration["reason"],
            trust_level="safe",
            time_ms=(time.perf_counter() - routing_started) * 1000,
        )

        execution_started = time.perf_counter()
        provider_result = _llm_response_with_provider(
            raw_command,
            language,
            personal_context=runtime_personal_context,
        )
        execution_time_ms = (time.perf_counter() - execution_started) * 1000
        provider_name = str(provider_result.get("provider_name") or "").strip() or None
        provider_model = str(provider_result.get("model") or "").strip() or None
        providers_tried = list(provider_result.get("providers_tried") or [])

        active_telemetry.record_provider(
            provider_result.get("provider_name") or "unknown",
            provider_result.get("model") or "unknown",
            provider_result.get("tokens_used"),
            provider_result.get("time_ms") or 0.0,
            success=bool(provider_result.get("success")),
            error=provider_result.get("error"),
        )

        response_text = str(provider_result.get("text") or "").strip()
        execution_mode = "conversation_llm" if fast_assistant_route == "conversation" else "assistant_llm"
        if not provider_result.get("success"):
            execution_mode = "degraded_assistant"

        active_telemetry.record_execution(
            "general",
            response_text or provider_result.get("error") or "No response content.",
            bool(provider_result.get("success") and response_text),
            execution_time_ms,
        )

        return build_result(
            raw_command=raw_command,
            detected_intent=detected_intent,
            confidence=confidence,
            response=response_text,
            language=language,
            orchestration=orchestration,
            used_agents=["general"],
            execution_mode=execution_mode,
            plan_steps=[],
            permission_action=permission_action,
            permission=permission,
            provider_name=provider_name,
            provider_model=provider_model,
            providers_tried=providers_tried,
            session_id=runtime_session_id,
            username=runtime_username,
            telemetry=active_telemetry,
            publish_telemetry=publish_telemetry,
        )

    web_result = maybe_execute_web_search_answer(
        raw_command=raw_command,
        detected_intent=detected_intent,
        confidence=confidence,
        language=language,
        permission_action="general",
        permission=_enforce_runtime_permission(
            "general",
            session_id=runtime_session_id,
            security_context=security_context,
            require_auth=False,
        ),
        session_id=runtime_session_id,
        username=runtime_username,
        telemetry=active_telemetry,
        publish_telemetry=publish_telemetry,
    )
    if web_result is not None:
        return web_result

    routing_started = time.perf_counter()
    orchestration = _sanitize_chat_orchestration(
        master_orchestrator.analyze_task(raw_command, intent=detected_intent)
    )
    mapped_primary_agent = _resolve_execution_agent_name(orchestration.get("primary_agent", "general"))
    if mapped_primary_agent != str(orchestration.get("primary_agent", "general")).strip().lower():
        _log_intent_agent_mapping(orchestration.get("primary_agent", "general"), mapped_primary_agent)
    permission_action = resolve_permission_action(raw_command, detected_intent, orchestration)
    permission = _enforce_runtime_permission(
        permission_action,
        session_id=runtime_session_id,
        security_context=security_context,
        require_auth=True,
    )
    selected_agent = mapped_primary_agent or detected_intent or "general"
    routing_reason = (
        orchestration.get("reason")
        or orchestration.get("routing_reason")
        or f"Detected intent '{detected_intent}' and selected '{selected_agent}'."
    )
    trust_level = get_trust_level(permission_action).value if permission_action else "safe"
    active_telemetry.record_routing(
        agent_selected=selected_agent,
        reason=str(routing_reason),
        trust_level=trust_level,
        time_ms=(time.perf_counter() - routing_started) * 1000,
    )

    if not permission["success"]:
        active_telemetry.record_execution(
            selected_agent,
            permission["permission"]["reason"],
            False,
            0.0,
        )
        try:
            update_context_from_command(raw_command, agent=selected_agent)
            record_reflection(
                requested_action=detected_intent,
                actual_action="permission_blocked",
                success=False,
                blocked_by_permission=True,
                retry_possible=True,
                learning_signal="permission_enforcement_blocked_execution",
            )
        except Exception:
            pass
        return _with_telemetry({
            "intent": "permission",
            "detected_intent": detected_intent,
            "confidence": confidence,
            "response": permission["permission"]["reason"],
            "plan": [],
            "used_agents": [selected_agent] if selected_agent else [],
            "agent_capabilities": build_agent_capability_cards(
                [selected_agent],
                detected_intent,
                orchestration,
            ),
            "execution_mode": "permission_blocked",
            "decision": build_decision_summary(detected_intent, confidence, AGENT_ROUTER),
            "orchestration": orchestration,
            "language": language,
            "confidence_detail": confidence_detail,
            "permission_action": permission_action,
            "permission": permission,
        }, active_telemetry, publish=publish_telemetry)

    if confidence < 0.40:
        log_low_confidence(raw_command, confidence)

    special_response = handle_special_intents(detected_intent)
    if special_response:
        active_telemetry.record_execution(detected_intent, special_response, True, 0.0)
        return build_result(
            raw_command=raw_command,
            detected_intent=detected_intent,
            confidence=confidence,
            response=special_response,
            language=language,
            orchestration=orchestration,
            used_agents=[detected_intent],
            execution_mode="special_intent",
            plan_steps=[],
            permission_action=permission_action,
            permission=permission,
            session_id=runtime_session_id,
            username=runtime_username,
            telemetry=active_telemetry,
            publish_telemetry=publish_telemetry,
        )

    resolved_intent = detected_intent
    if should_fallback_to_general(confidence):
        resolved_intent = "general"

    response = ""
    used_agents: List[str] = []
    execution_mode = "fallback_llm"
    provider_name: Optional[str] = None
    provider_model: Optional[str] = None
    providers_tried: List[str] = []
    execution_started = time.perf_counter()

    try:
        orchestrated_response, orchestrated_agents, execution_mode = execute_orchestrated_agents(
            raw_command,
            detected_intent,
            confidence,
            orchestration,
        )

        if orchestrated_response:
            response = orchestrated_response
            used_agents = orchestrated_agents
        elif should_use_agent(resolved_intent, confidence, AGENT_ROUTER):
            execution_agent = _resolve_execution_agent_name(resolved_intent)
            if execution_agent != resolved_intent:
                _log_intent_agent_mapping(resolved_intent, execution_agent)
            response = run_agent(execution_agent, raw_command)
            used_agents = [execution_agent]
            execution_mode = "single_agent"
        else:
            generated_match = match_generated_agent_request(raw_command, exclude_ids=AGENT_ROUTER.keys())
            if generated_match:
                generated_result = run_generated_agent(
                    generated_match.id,
                    raw_command,
                    username=runtime_username,
                    user_id=runtime_identity.get("user_id"),
                    session_id=runtime_session_id,
                    session_token=runtime_identity.get("session_token"),
                    confirmed=runtime_identity.get("confirmed", False),
                    pin=runtime_identity.get("pin"),
                    otp=runtime_identity.get("otp"),
                    otp_token=runtime_identity.get("otp_token"),
                )
                response = normalize_agent_output(generated_result)
                used_agents = [generated_match.id]
                execution_mode = "generated_agent"
            else:
                enhanced_input = build_enhanced_input(raw_command, confidence)
                provider_result = _llm_response_with_provider(
                    enhanced_input,
                    language,
                    personal_context=runtime_personal_context,
                )
                if provider_result.get("success"):
                    response = str(provider_result.get("text") or "")
                    provider_name = str(provider_result.get("provider_name") or "").strip() or None
                    provider_model = str(provider_result.get("model") or "").strip() or None
                    providers_tried = list(provider_result.get("providers_tried") or [])
                    active_telemetry.record_provider(
                        provider_result.get("provider_name") or "unknown",
                        provider_result.get("model") or "unknown",
                        provider_result.get("tokens_used"),
                        provider_result.get("time_ms") or 0.0,
                    )
                else:
                    response = str(provider_result.get("text") or "").strip()
                    providers_tried = list(provider_result.get("providers_tried") or [])
                    execution_mode = "degraded_assistant"
                    active_telemetry.record_provider(
                        provider_result.get("provider_name") or "unavailable",
                        provider_result.get("model") or "unknown",
                        provider_result.get("tokens_used"),
                        provider_result.get("time_ms") or 0.0,
                        success=False,
                        error=provider_result.get("error"),
                    )
                    log_failure(raw_command, str(provider_result.get("error") or "Provider response failed"))
        normalized_response = clean_response(response)
        success = bool(normalized_response) and execution_mode != "degraded_assistant" and not _is_unusable_runtime_response(normalized_response)
    except Exception as error:
        execution_time_ms = (time.perf_counter() - execution_started) * 1000
        active_telemetry.record_execution(
            used_agents[0] if used_agents else (orchestration.get("primary_agent") or resolved_intent or "general"),
            str(error),
            False,
            execution_time_ms,
        )
        raise

    execution_time_ms = (time.perf_counter() - execution_started) * 1000
    active_telemetry.record_execution(
        used_agents[0] if used_agents else (orchestration.get("primary_agent") or resolved_intent or "general"),
        _telemetry_excerpt(response),
        success,
        execution_time_ms,
    )

    plan_steps = build_plan_steps(raw_command, resolved_intent, confidence, orchestration)

    return build_result(
        raw_command=raw_command,
        detected_intent=resolved_intent,
        confidence=confidence,
        response=response,
        language=language,
        orchestration=orchestration,
        used_agents=used_agents,
        execution_mode=execution_mode,
        plan_steps=plan_steps,
        permission_action=permission_action,
        permission=permission,
        provider_name=provider_name,
        provider_model=provider_model,
        providers_tried=providers_tried,
        session_id=runtime_session_id,
        username=runtime_username,
        telemetry=active_telemetry,
        publish_telemetry=publish_telemetry,
    )


def process_single_command(command: str) -> tuple[str, str]:
    result = process_single_command_detailed(command)
    return result["intent"], result["response"]


def _process_action_plan_command(
    raw_command: str,
    action_plan: Any,
    *,
    session_id: Optional[str],
    security_context: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    active_telemetry = ProcessingTelemetry()
    runtime_session_id = session_id or "runtime"
    runtime_identity = _runtime_identity(security_context)
    runtime_username = runtime_identity.get("username")
    active_telemetry.record_understanding(
        raw_input=raw_command,
        normalized=raw_command,
        entities=parse_entities(raw_command).to_dict(),
        time_ms=0.0,
    )

    permission = _enforce_runtime_permission(
        "desktop_launch",
        session_id=runtime_session_id,
        security_context=security_context,
        require_auth=False,
    )
    if not permission.get("success"):
        reason = str((permission.get("permission") or {}).get("reason") or "This action is protected.")
        active_telemetry.record_intent("action_plan", 1.0, [], 0.0)
        active_telemetry.record_routing("action_planner", "Safe action plan matched, but permission blocked execution.", "safe", 0.0)
        active_telemetry.record_execution("action_planner", reason, False, 0.0)
        return _with_telemetry({
            "intent": "permission",
            "detected_intent": "action_plan",
            "confidence": 1.0,
            "response": reason,
            "plan": [step.get("label") for step in action_plan.to_dict().get("steps", [])],
            "used_agents": ["action_planner"],
            "agent_capabilities": build_runtime_agent_cards(["action_planner"]),
            "execution_mode": "permission_blocked",
            "decision": {"action_plan": True, "command_count": len(action_plan.steps)},
            "orchestration": {
                "primary_agent": "action_planner",
                "execution_order": ["action_planner"],
                "requires_multiple": True,
                "mode": "real",
                "reason": "Action plan was blocked by permission enforcement.",
            },
            "language": "english",
            "permission_action": "desktop_launch",
            "permission": permission,
            "action_plan": action_plan.to_dict(),
        }, active_telemetry, publish=True)

    started = time.perf_counter()
    execution = execute_action_plan(
        action_plan,
        session_id=runtime_session_id,
        username=runtime_username,
        automation_confirmed=bool((security_context or {}).get("confirmed")),
    )
    execution_time_ms = (time.perf_counter() - started) * 1000
    feedback = [str(item).strip() for item in execution.get("feedback", []) if str(item).strip()]
    response = "\n".join(feedback) or (
        "Action plan completed." if execution.get("success") else "I couldn't complete that action plan."
    )
    step_types = {str(step.get("action_type") or "") for step in execution.get("plan", {}).get("steps", [])}
    used_agents = ["action_planner"]
    if "desktop_open" in step_types:
        used_agents.append("desktop_controller")
    if any(step_type.startswith("browser_") for step_type in step_types):
        used_agents.append("browser_action")
    if any(step_type.startswith("automation_") for step_type in step_types):
        used_agents.append("os_automation")

    active_telemetry.record_intent("action_plan", 1.0, [], 0.0)
    active_telemetry.record_routing(
        "action_planner",
        "Command decomposed into safe whitelisted desktop/browser actions.",
        "safe",
        0.0,
    )
    active_telemetry.record_execution(
        "action_planner",
        response,
        bool(execution.get("success")),
        execution_time_ms,
    )

    result = build_result(
        raw_command=raw_command,
        detected_intent="action_plan",
        confidence=1.0,
        response=response,
        language="english",
        orchestration={
            "primary_agent": "action_planner",
            "secondary_agents": used_agents[1:],
            "execution_order": used_agents,
            "requires_multiple": True,
            "primary_selection_source": "safe_action_plan",
            "mode": "real",
            "reason": "VORIS decomposed the request into safe whitelisted actions and executed them sequentially.",
        },
        used_agents=used_agents,
        execution_mode="action_plan" if execution.get("success") else "action_plan_failed",
        plan_steps=[step.get("label") for step in execution.get("plan", {}).get("steps", [])],
        permission_action="desktop_launch",
        permission=permission,
        session_id=runtime_session_id,
        username=runtime_username,
        telemetry=active_telemetry,
        publish_telemetry=True,
    )
    result["action_plan"] = execution.get("plan")
    result["action_steps"] = execution.get("plan", {}).get("steps", [])
    result["action_success"] = bool(execution.get("success"))
    result["action_status"] = execution.get("status")
    result["failed_action_step"] = execution.get("failed_step")
    result["action_suggestions"] = execution.get("suggestions", [])
    result["action_memory"] = execution.get("action_memory", {})
    result["automation_confirmation_required"] = bool(execution.get("automation_confirmation_required"))
    result["automation_control"] = bool(execution.get("automation_control"))
    result["action_trace"] = build_action_trace(
        request_id=new_request_id("runtime"),
        raw_input=raw_command,
        intent="action_plan",
        provider=result.get("provider"),
        permission=permission,
        action_plan=result.get("action_plan"),
        execution_mode=result.get("execution_mode"),
        used_agents=used_agents,
        degraded=bool(result.get("degraded")),
        success=bool(result.get("action_success")),
        status=result.get("action_status"),
        source=result,
    )
    return result


def process_command_detailed(
    command: str,
    *,
    session_id: Optional[str] = None,
    security_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    raw_input = str(command or "")
    raw_command = clean_user_input(command)

    if not raw_command:
        return process_single_command_detailed(
            raw_command,
            session_id=session_id,
            security_context=security_context,
        )

    if resolve_document_request(raw_input, session_id=session_id) is not None or resolve_document_request(raw_command, session_id=session_id) is not None:
        return process_single_command_detailed(
            raw_command,
            session_id=session_id,
            security_context=security_context,
        )

    action_plan = build_action_plan(raw_command)
    if action_plan is not None:
        return _process_action_plan_command(
            raw_command,
            action_plan,
            session_id=session_id,
            security_context=security_context,
        )

    sub_commands = split_commands(raw_command)

    if not should_treat_as_multi_command(sub_commands):
        return process_single_command_detailed(
            raw_command,
            session_id=session_id,
            security_context=security_context,
        )

    aggregate_telemetry = ProcessingTelemetry()
    understanding_started = time.perf_counter()
    aggregate_telemetry.record_understanding(
        raw_input=raw_input,
        normalized=raw_command,
        entities=parse_entities(raw_command).to_dict(),
        time_ms=(time.perf_counter() - understanding_started) * 1000,
    )

    results = [
        process_single_command_detailed(
            sub_command,
            publish_telemetry=False,
            session_id=session_id,
            security_context=security_context,
        )
        for sub_command in sub_commands
    ]
    responses = [item["response"] for item in results]

    used_agents: List[str] = []
    for item in results:
        for agent_name in item.get("used_agents", []):
            if agent_name not in used_agents:
                used_agents.append(agent_name)

    plan_steps = []
    for index, item in enumerate(results, start=1):
        routed_agents = ", ".join(item.get("used_agents") or [item.get("intent", "general")])
        plan_steps.append(f"Command {index}: handle with {routed_agents}")

    blocked_permissions = [
        {
            "command": sub_command,
            "permission_action": item.get("permission_action"),
            "permission": item.get("permission"),
        }
        for sub_command, item in zip(sub_commands, results)
        if not bool(item.get("permission", {}).get("success", False))
    ]

    aggregated_permission = {
        "success": not blocked_permissions,
        "status": "aggregated_blocked" if blocked_permissions else "aggregated",
        "mode": "real",
        "blocked_commands": blocked_permissions,
    }
    intent_alternatives = []
    routing_levels = []
    execution_success = True
    execution_time_ms = 0.0
    last_provider_stage: Optional[Dict[str, Any]] = None

    for sub_command, item in zip(sub_commands, results):
        telemetry = item.get("telemetry") or {}
        stages = telemetry.get("stages") or {}
        intent_stage = stages.get("intent") or {}
        routing_stage = stages.get("routing") or {}
        execution_stage = stages.get("execution") or {}
        provider_stage = stages.get("provider") or {}

        if intent_stage:
            intent_alternatives.append(
                {
                    "intent": intent_stage.get("primary_intent") or item.get("detected_intent"),
                    "score": intent_stage.get("confidence"),
                    "matched_rules": [],
                    "command": sub_command,
                }
            )
        if routing_stage.get("trust_level"):
            routing_levels.append(routing_stage.get("trust_level"))
        if execution_stage.get("status") == "failed":
            execution_success = False
        execution_time_ms += float(execution_stage.get("time_ms") or 0.0)
        if provider_stage.get("status") and provider_stage.get("status") != "idle":
            last_provider_stage = provider_stage

    aggregate_telemetry.record_intent(
        primary_intent="multi_command",
        confidence=max((item.get("confidence", 0.0) for item in results), default=0.0),
        alternatives=intent_alternatives[:3],
        time_ms=sum(
            float(((item.get("telemetry") or {}).get("stages", {}).get("intent", {}) or {}).get("time_ms") or 0.0)
            for item in results
        ),
    )
    aggregate_telemetry.record_routing(
        agent_selected=", ".join(used_agents) if used_agents else "multi_command",
        reason=f"Split the request into {len(sub_commands)} actionable commands.",
        trust_level=_max_trust_level(routing_levels),
        time_ms=sum(
            float(((item.get("telemetry") or {}).get("stages", {}).get("routing", {}) or {}).get("time_ms") or 0.0)
            for item in results
        ),
    )
    aggregate_telemetry.record_execution(
        "multi_command",
        f"Processed {len(results)} commands.",
        execution_success,
        execution_time_ms,
    )
    if last_provider_stage:
        aggregate_telemetry.record_provider(
            last_provider_stage.get("provider_name") or "unknown",
            last_provider_stage.get("model") or "unknown",
            last_provider_stage.get("tokens_used"),
            float(last_provider_stage.get("time_ms") or 0.0),
            success=last_provider_stage.get("status") != "failed",
            error=last_provider_stage.get("error"),
        )

    return _with_telemetry({
        "intent": "multi_command",
        "detected_intent": "multi_command",
        "confidence": max((item.get("confidence", 0.0) for item in results), default=0.0),
        "response": format_multi_response(responses),
        "plan": plan_steps,
        "used_agents": used_agents,
        "agent_capabilities": build_runtime_agent_cards(used_agents),
        "execution_mode": "multi_command",
        "decision": {
            "multi_command": True,
            "command_count": len(results),
        },
        "orchestration": {
            "primary_agent": "multi_command",
            "execution_order": used_agents,
            "requires_multiple": True,
            "mode": "real",
        },
        "language": detect_language(raw_command),
        "permission_action": "multi_command",
        "permission": aggregated_permission,
    }, aggregate_telemetry, publish=True)


def process_command(command: str) -> tuple[str, str]:
    result = process_command_detailed(command)
    return result["intent"], result["response"]
