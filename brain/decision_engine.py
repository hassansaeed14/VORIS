# brain/decision_engine.py

"""
Decision Engine

Responsible ONLY for:
- routing decisions
- confidence thresholds
- planning decisions
- multi-command handling

DOES NOT:
- call agents
- call LLM
- handle permissions
- modify state
"""

from typing import Dict, Any, Optional


# -----------------------------
# Threshold Config
# -----------------------------

AGENT_THRESHOLD = 0.55
FALLBACK_THRESHOLD = 0.35
LOW_CONFIDENCE_MIN = 0.35
LOW_CONFIDENCE_MAX = 0.55
PLANNING_THRESHOLD = 0.60

PLANNING_INTENTS = {"research", "study", "task"}


# -----------------------------
# Helpers
# -----------------------------

def normalize_confidence(confidence: Optional[float]) -> float:
    """
    Normalize confidence into safe 0.0 - 1.0 range.
    Defensive against bad upstream values.
    """
    if confidence is None:
        return 0.0

    try:
        value = float(confidence)
    except (TypeError, ValueError):
        return 0.0

    if value < 0.0:
        return 0.0

    if value > 1.0:
        return 1.0

    return value


def is_meaningful_command(part: Optional[str]) -> bool:
    """
    Reject empty, whitespace-only, or punctuation-only fragments.
    """
    if not part or not isinstance(part, str):
        return False

    stripped = part.strip()
    if not stripped:
        return False

    cleaned = stripped.strip(" ,.;:!?-_")
    return bool(cleaned)


# -----------------------------
# Core Decision Functions
# -----------------------------

def should_fallback_to_general(confidence: Optional[float]) -> bool:
    """
    Only fallback when confidence is very low.
    Prevents unnecessary general-mode routing.
    """
    normalized_confidence = normalize_confidence(confidence)
    return normalized_confidence < FALLBACK_THRESHOLD


def should_use_agent(intent: str, confidence: Optional[float], agent_router: dict) -> bool:
    """
    Use agent ONLY if:
    - intent exists in router
    - confidence is strong enough
    - confidence is not in fallback zone
    """
    if not intent:
        return False

    if intent not in agent_router:
        return False

    normalized_confidence = normalize_confidence(confidence)

    if normalized_confidence < FALLBACK_THRESHOLD:
        return False

    return normalized_confidence >= AGENT_THRESHOLD


def should_plan(intent: str, confidence: Optional[float]) -> bool:
    """
    Trigger planning only for strong planning-oriented intents.
    """
    if not intent:
        return False

    normalized_confidence = normalize_confidence(confidence)
    return intent in PLANNING_INTENTS and normalized_confidence >= PLANNING_THRESHOLD


def should_add_low_confidence_note(confidence: Optional[float]) -> bool:
    """
    Add note when confidence is uncertain but not fully weak.
    """
    normalized_confidence = normalize_confidence(confidence)
    return LOW_CONFIDENCE_MIN <= normalized_confidence < LOW_CONFIDENCE_MAX


# -----------------------------
# Decision Summary
# -----------------------------

def build_decision_summary(intent: str, confidence: Optional[float], agent_router: dict) -> Dict[str, Any]:
    """
    Returns structured decision metadata.
    Useful for:
    - logs
    - debugging
    - future intelligence panel
    """
    normalized_confidence = normalize_confidence(confidence)
    intent_in_router = bool(intent and intent in agent_router)

    fallback = should_fallback_to_general(normalized_confidence)
    use_agent = should_use_agent(intent, normalized_confidence, agent_router)
    plan = should_plan(intent, normalized_confidence)
    low_confidence = should_add_low_confidence_note(normalized_confidence)

    if fallback:
        final_route = "general"
        decision_reason = "confidence_below_fallback_threshold"
    elif use_agent:
        final_route = "agent"
        decision_reason = "intent_in_router_and_confidence_sufficient"
    else:
        final_route = "general"
        if low_confidence:
            decision_reason = "low_confidence_caution_zone"
        else:
            decision_reason = "no_agent_match_or_non_planning_intent"

    return {
        "intent": intent,
        "confidence": normalized_confidence,
        "intent_in_router": intent_in_router,
        "fallback": fallback,
        "use_agent": use_agent,
        "plan": plan,
        "low_confidence": low_confidence,
        "final_route": final_route,
        "decision_reason": decision_reason,
        "thresholds": {
            "agent_threshold": AGENT_THRESHOLD,
            "fallback_threshold": FALLBACK_THRESHOLD,
            "low_confidence_min": LOW_CONFIDENCE_MIN,
            "low_confidence_max": LOW_CONFIDENCE_MAX,
            "planning_threshold": PLANNING_THRESHOLD,
        },
    }


# -----------------------------
# Multi Command Handling
# -----------------------------

def should_treat_as_multi_command(parts: list) -> bool:
    """
    Treat as multi-command only if:
    - there is more than one meaningful command
    """
    if not parts or not isinstance(parts, list):
        return False

    meaningful = [p.strip() for p in parts if is_meaningful_command(p)]
    return len(meaningful) > 1


def format_multi_response(results: list) -> str:
    """
    Clean formatting for multiple responses.
    """
    if not results:
        return "I couldn't understand the request clearly."

    meaningful_results = [str(r).strip() for r in results if is_meaningful_command(str(r))]

    if not meaningful_results:
        return "I couldn't understand the request clearly."

    if len(meaningful_results) == 1:
        return meaningful_results[0]

    formatted = []
    for i, result in enumerate(meaningful_results, 1):
        formatted.append(f"{i}. {result}")

    return "\n\n".join(formatted)