import re
from datetime import datetime

from brain.intent_engine import detect_intent_with_confidence
from brain.response_engine import generate_response
from brain.understanding_engine import clean_user_input, split_multi_intent
from brain.decision_engine import (
    should_fallback_to_general,
    should_use_agent,
    should_plan,
    should_add_low_confidence_note,
    should_treat_as_multi_command,
    format_multi_response
)

from memory.vector_memory import store_memory
from memory.knowledge_base import (
    store_user_name, get_user_name,
    store_user_age, get_user_age,
    store_user_city, get_user_city
)

from agents.memory.learning_agent import (
    learn_from_interaction,
    get_user_insights,
    get_personalized_greeting,
    build_context
)

from agents.core.self_improvement_agent import (
    log_failure,
    log_low_confidence,
    log_agent_error
)

from agents.core.reasoning_agent import reason, compare
from agents.core.language_agent import detect_language, respond_in_language

from agents.productivity.fitness_agent import get_workout_plan
from agents.productivity.study_agent import study
from agents.productivity.research_agent import research
from agents.productivity.coding_agent import code_help
from agents.productivity.content_writer_agent import write_content
from agents.productivity.email_writer_agent import write_email
from agents.productivity.summarizer_agent import summarize_topic
from agents.productivity.grammar_agent import check_grammar
from agents.productivity.quiz_agent import generate_quiz, generate_flashcards

from agents.integration.weather_agent import get_weather
from agents.integration.news_agent import get_news
from agents.integration.math_agent import solve_math
from agents.integration.translation_agent import translate
from agents.integration.web_search_agent import web_search
from agents.integration.currency_agent import convert_currency, get_crypto_price
from agents.integration.dictionary_agent import define_word, get_synonyms
from agents.integration.youtube_agent import search_youtube_topic
from agents.integration.joke_agent import get_joke
from agents.integration.quote_agent import get_quote

from agents.system.file_agent import analyze_file, list_files
from agents.system.screenshot_agent import take_screenshot

from agents.autonomous.planner_agent import create_plan
from agents.autonomous.executor import execute_plan

from security.permission_engine import evaluate_permission


PLANNING_INTENTS = {"research", "study", "task"}
GREETING_INPUTS = {"hi", "hello", "hey", "hey aura", "hi aura", "hello aura"}


def extract_currency_request(command: str):
    amount_match = re.search(r"(\d+(\.\d+)?)", command)
    currency_matches = re.findall(r"\b[A-Z]{3}\b", command.upper())

    amount = float(amount_match.group(1)) if amount_match else 1.0

    if len(currency_matches) >= 2:
        return amount, currency_matches[0], currency_matches[1]

    return amount, "USD", "PKR"


def extract_translation_target(command: str):
    command_lower = command.lower()

    language_map = {
        "urdu": "urdu",
        "english": "english",
        "arabic": "arabic",
        "french": "french",
        "spanish": "spanish",
        "hindi": "hindi",
        "punjabi": "punjabi"
    }

    for lang in language_map:
        if f"in {lang}" in command_lower or f"to {lang}" in command_lower:
            return language_map[lang]

    return "english"


def store_and_learn(user_input: str, response: str, intent: str, extra_metadata=None):
    metadata = {"type": "user_input", "intent": intent}
    if extra_metadata:
        metadata.update(extra_metadata)

    store_memory(user_input, metadata)
    learn_from_interaction(user_input, response, intent)


def route_quiz_command(command: str):
    if "flashcard" in command.lower():
        return generate_flashcards(command)
    return generate_quiz(command)


AGENT_ROUTER = {
    "weather": lambda cmd: get_weather(cmd),
    "news": lambda cmd: get_news(cmd),
    "math": lambda cmd: solve_math(
        cmd.replace("calculate", "").replace("solve", "").strip()
    ),
    "fitness": lambda cmd: get_workout_plan(cmd),
    "translation": lambda cmd: translate(cmd, extract_translation_target(cmd)),
    "research": lambda cmd: research(cmd),
    "study": lambda cmd: study(cmd),
    "code": lambda cmd: code_help(cmd),
    "content": lambda cmd: write_content(cmd, "blog"),
    "email": lambda cmd: write_email(cmd, cmd),
    "summarize": lambda cmd: summarize_topic(cmd),
    "grammar": lambda cmd: check_grammar(cmd),
    "quiz": route_quiz_command,
    "dictionary": lambda cmd: define_word(cmd),
    "synonyms": lambda cmd: get_synonyms(cmd),
    "web_search": lambda cmd: web_search(cmd),
    "youtube": lambda cmd: search_youtube_topic(cmd),
    "currency": lambda cmd: convert_currency(*extract_currency_request(cmd)),
    "crypto": lambda cmd: get_crypto_price("bitcoin"),
    "joke": lambda cmd: get_joke(),
    "quote": lambda cmd: get_quote(),
    "file": lambda cmd: analyze_file(cmd),
    "list_files": lambda cmd: list_files("."),
    "screenshot": lambda cmd: take_screenshot(),
}


def handle_personal_memory(command: str):
    cmd = command.lower().strip()

    if "my name is" in cmd:
        name = cmd.replace("my name is", "").strip()
        store_user_name(name)
        return "memory", f"Nice to meet you {name}! I will remember your name."

    if "what is my name" in cmd:
        name = get_user_name()
        if name:
            return "memory", f"Your name is {name}."
        return "memory", "I don't know your name yet."

    if "my age is" in cmd:
        age = cmd.replace("my age is", "").strip()
        store_user_age(age)
        return "memory", f"I will remember that you are {age} years old."

    if "how old am i" in cmd:
        age = get_user_age()
        if age:
            return "memory", f"You are {age} years old."
        return "memory", "I don't know your age yet."

    if "i live in" in cmd:
        city = cmd.replace("i live in", "").strip()
        store_user_city(city)
        return "memory", f"I will remember that you live in {city}."

    if "where do i live" in cmd:
        city = get_user_city()
        if city:
            return "memory", f"You live in {city}."
        return "memory", "I don't know where you live."

    return None


def handle_special_intents(intent: str, raw_command: str):
    if intent == "insights":
        return "insights", get_user_insights()

    if intent == "compare":
        return "compare", compare(raw_command)

    if intent == "time":
        return "time", f"The current time is {datetime.now().strftime('%I:%M %p')}."

    if intent == "date":
        return "date", f"Today's date is {datetime.now().strftime('%A, %d %B %Y')}."

    if intent == "identity":
        return (
            "identity",
            "I am AURA — Autonomous Universal Responsive Assistant. "
            "I am your AI assistant for productivity, learning, coding, research, and more."
        )

    return None


def preprocess_command(command: str):
    raw_command = clean_user_input(command)
    command_lower = raw_command.lower()
    return raw_command, command_lower


def build_enhanced_input(raw_command: str, confidence: float):
    try:
        enhanced_input = build_context(raw_command)
    except Exception:
        enhanced_input = raw_command

    try:
        reasoning = reason(raw_command)
        if reasoning:
            enhanced_input += f"\n\nReasoning:\n{reasoning}"
    except Exception:
        pass

    if should_add_low_confidence_note(confidence):
        enhanced_input += (
            "\n\nIntent confidence is low. "
            "Respond carefully, infer user meaning safely, and handle imperfect wording gracefully."
        )

    return enhanced_input


def run_agent_or_fallback(intent: str, raw_command: str, enhanced_input: str, confidence: float):
    if should_use_agent(intent, confidence, AGENT_ROUTER):
        try:
            return str(AGENT_ROUTER[intent](raw_command))
        except Exception as e:
            log_agent_error(intent, str(e))
            return f"Agent error: {str(e)}"

    try:
        return generate_response(enhanced_input)
    except Exception as e:
        log_failure(raw_command, str(e))
        return "I ran into a problem while processing that request."


def append_plan_if_needed(response: str, intent: str, raw_command: str, confidence: float):
    if not should_plan(intent, confidence):
        return response

    try:
        plan = create_plan(raw_command)

        if isinstance(plan, str):
            response += f"\n\nPlan:\n{plan}"
        elif isinstance(plan, list) and len(plan) > 1:
            results = execute_plan(plan)
            if results:
                response += "\n\nPlan:\n" + "\n".join(str(r) for r in results)
    except Exception:
        pass

    return response


def finalize_response(raw_command: str, response: str, intent: str, language: str):
    store_and_learn(raw_command, response, intent)
    return respond_in_language(response, language)


def requires_permission_check(intent: str):
    protected_intents = {
        "file",
        "screenshot",
        "web_search",
        "task",
        "reminder",
        "email"
    }
    return intent in protected_intents


def process_single_command(command: str):
    raw_command, command_lower = preprocess_command(command)

    if not raw_command:
        return "general", "Please type something."

    if command_lower in GREETING_INPUTS:
        response = get_personalized_greeting()
        store_and_learn(raw_command, response, "greeting")
        return "greeting", response

    memory_response = handle_personal_memory(raw_command)
    if memory_response:
        store_and_learn(raw_command, memory_response[1], memory_response[0])
        return memory_response

    language = detect_language(raw_command)

    intent, confidence = detect_intent_with_confidence(raw_command)

    if confidence < 0.40:
        log_low_confidence(raw_command, confidence)

    if should_fallback_to_general(confidence):
        intent = "general"

    special_response = handle_special_intents(intent, raw_command)
    if special_response:
        final_response = finalize_response(
            raw_command,
            special_response[1],
            special_response[0],
            language
        )
        return special_response[0], final_response

    if requires_permission_check(intent):
        permission = evaluate_permission(raw_command)

        if not permission["allowed"]:
            response = (
                f"Permission required.\n\n"
                f"Action level: {permission['action_level']}\n"
                f"Policy: {permission['rule']}\n"
                f"Reason: {permission['reason']}\n\n"
                f"Please confirm or unlock this action in settings."
            )
            final_response = finalize_response(raw_command, response, "permission", language)
            return "permission", final_response

    enhanced_input = build_enhanced_input(raw_command, confidence)
    response = run_agent_or_fallback(intent, raw_command, enhanced_input, confidence)
    response = append_plan_if_needed(response, intent, raw_command, confidence)
    final_response = finalize_response(raw_command, response, intent, language)

    return intent, final_response


def process_command(command: str):
    raw_command, _ = preprocess_command(command)

    if not raw_command:
        return "general", "Please type something."

    sub_commands = split_multi_intent(raw_command)

    if not should_treat_as_multi_command(sub_commands):
        return process_single_command(raw_command)

    results = []

    for sub_command in sub_commands:
        _, response = process_single_command(sub_command)
        results.append(response)

    return "multi_command", format_multi_response(results)