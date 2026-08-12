import re


def _has_any(text, phrases):
    return any(phrase in text for phrase in phrases)


def _starts_with_any(text, prefixes):
    return any(text.startswith(prefix) for prefix in prefixes)


def _has_math_expression(text):
    math_pattern = r"^\s*[\d\.\+\-\*\/\(\)\s%]+$"
    return bool(re.match(math_pattern, text))


def _has_number(text):
    return any(char.isdigit() for char in text)


def _has_currency_code(text):
    codes = re.findall(r"\b[A-Z]{3}\b", text.upper())
    return len(codes) >= 2


def _score_match(text, phrases, starts_with=False, whole_match=False):
    score = 0

    for phrase in phrases:
        if whole_match and text == phrase:
            score += 3
        elif starts_with and text.startswith(phrase):
            score += 2
        elif phrase in text:
            score += 1

    return score


def detect_intent_with_confidence(command):
    command_lower = command.lower().strip()
    words = command_lower.split()

    if not command_lower:
        return "general", 0.0

    scores = {}

    def add_score(intent, value):
        scores[intent] = scores.get(intent, 0) + value

    greeting_phrases = [
        "hi", "hello", "hey", "hey aura", "hi aura",
        "hello aura", "good morning", "good evening",
        "good afternoon", "salam", "السلام علیکم", "ہیلو"
    ]
    add_score("greeting", _score_match(command_lower, greeting_phrases, whole_match=True))

    shutdown_phrases = ["bye", "goodbye", "exit", "quit", "shutdown", "bye bye", "bye-bye", "good bye", "see you"]
    add_score("shutdown", _score_match(command_lower, shutdown_phrases))

    identity_phrases = [
        "who are you", "what are you", "your name",
        "who made you", "who created you", "who built you",
        "introduce yourself", "about yourself"
    ]
    add_score("identity", _score_match(command_lower, identity_phrases))

    dictionary_starts = ["define ", "meaning of ", "synonym of ", "antonym of "]
    dictionary_phrases = [
        "definition of", "word meaning", "dictionary meaning",
        "what does", "mean in english", "synonym", "antonym"
    ]
    add_score("dictionary", _score_match(command_lower, dictionary_starts, starts_with=True))
    add_score("dictionary", _score_match(command_lower, dictionary_phrases))

    translation_phrases = [
        "translate", "translation of", "translate this",
        "in urdu", "in english", "in arabic", "in french",
        "in spanish", "in hindi", "in punjabi",
        "ترجمہ", "how to say"
    ]
    add_score("translation", _score_match(command_lower, translation_phrases))

    weather_phrases = [
        "weather", "temperature", "forecast", "rain today",
        "sunny today", "cloudy today", "how hot", "how cold",
        "what is the weather", "موسم", "بارش"
    ]
    add_score("weather", _score_match(command_lower, weather_phrases))

    news_phrases = [
        "news", "latest news", "headlines", "what happened today",
        "breaking news", "خبریں", "آج کی خبر"
    ]
    add_score("news", _score_match(command_lower, news_phrases))

    currency_phrases = [
        "convert currency", "exchange rate", "currency convert",
        "usd to", "pkr to", "dollar to", "rupee to",
        "bitcoin price", "crypto price", "ethereum price",
        "btc price", "eth price"
    ]
    add_score("currency", _score_match(command_lower, currency_phrases))
    if _has_currency_code(command_lower):
        add_score("currency", 3)

    math_phrases = [
        "calculate", "solve", "how much is",
        "percentage of", "square root", "factorial",
        "multiply", "divide", "plus", "minus"
    ]
    if _has_math_expression(command_lower):
        add_score("math", 4)
    if _has_any(command_lower, math_phrases) and _has_number(command_lower):
        add_score("math", 3)

    add_score("email", _score_match(command_lower, [
        "write email", "draft email", "compose email",
        "write a mail", "email to", "write me an email"
    ]))

    add_score("content", _score_match(command_lower, [
        "write a blog", "write an article", "write a post",
        "write an essay", "write content", "instagram post",
        "facebook post", "social media post"
    ]))

    add_score("grammar", _score_match(command_lower, [
        "check grammar", "fix grammar", "correct my",
        "improve my writing", "paraphrase", "rewrite this",
        "proofread", "grammar check"
    ]))

    add_score("summarize", _score_match(command_lower, [
        "summarize", "summary of", "brief overview",
        "tldr", "shorten this", "condense"
    ]))

    add_score("quiz", _score_match(command_lower, [
        "quiz", "test me on", "make a quiz", "flashcard",
        "flashcards", "practice questions", "mcqs about", "generate questions"
    ]))

    add_score("joke", _score_match(command_lower, [
        "tell me a joke", "joke", "make me laugh",
        "funny joke", "لطیفہ", "مزاحیہ"
    ]))

    add_score("quote", _score_match(command_lower, [
        "give me a quote", "motivational quote", "inspire me",
        "islamic quote", "daily quote", "quote about"
    ]))

    add_score("password", _score_match(command_lower, [
        "generate password", "create password", "strong password",
        "check password strength", "password generator"
    ]))

    add_score("reminder", _score_match(command_lower, [
        "remind me", "set reminder", "add reminder",
        "my reminders", "show reminders", "delete reminder"
    ]))

    add_score("task", _score_match(command_lower, [
        "add task", "my tasks", "show tasks", "complete task",
        "delete task", "task list", "to do list", "todo",
        "plan my", "task plan for", "project plan", "steps to"
    ]))

    add_score("fitness", _score_match(command_lower, [
        "workout", "fitness", "exercise", "gym", "training",
        "workout plan", "fitness plan", "exercise routine",
        "gym routine", "muscle gain", "weight loss"
    ]))

    add_score("resume", _score_match(command_lower, [
        "create resume", "write resume", "make resume",
        "resume tips", "improve resume", "build my cv"
    ]))

    add_score("cover_letter", _score_match(command_lower, [
        "cover letter", "write cover letter", "job application letter"
    ]))

    add_score("web_search", _score_match(command_lower, [
        "search for", "search the web", "google",
        "find information about", "look up"
    ]))

    add_score("youtube", _score_match(command_lower, [
        "youtube", "youtu.be", "summarize video",
        "youtube video about"
    ]))

    add_score("list_files", _score_match(command_lower, [
        "list files", "show files", "my files", "list of my files"
    ]))
    add_score("file", _score_match(command_lower, [
        "read file", "open file", "analyze file",
        "read pdf", "read document"
    ]))

    add_score("screenshot", _score_match(command_lower, [
        "take screenshot", "screenshot", "capture screen"
    ]))

    add_score("insights", _score_match(command_lower, [
        "what do i use", "my usage", "my insights",
        "how often do i", "my statistics", "usage report"
    ]))

    add_score("compare", _score_match(command_lower, [
        "compare", "versus", " vs ", "pros and cons",
        "difference between", "which is better"
    ]))

    add_score("code", _score_match(command_lower, [
        "write code", "debug", "fix my code", "code for",
        "write a program", "write a function", "write a script",
        "help me code", "programming help"
    ]))

    add_score("study", _score_match(command_lower, [
        "explain in detail", "tell me everything about",
        "study guide", "teach me about", "assignment on",
        "essay on", "detailed explanation",
        "in depth explanation", "comprehensive guide",
        "elaborate on", "full explanation of"
    ]))

    add_score("research", _score_match(command_lower, [
        "research on", "research about",
        "investigation on", "research report", "findings about",
        "analyze this topic", "analyze this subject"
    ]))

    if len(words) <= 6 and _has_any(command_lower, [
        "what time is it", "current time", "time now"
    ]):
        add_score("time", 3)

    if len(words) <= 6 and _has_any(command_lower, [
        "what is the date", "today date", "current date", "what day is today"
    ]):
        add_score("date", 3)

    if not scores:
        return "general", 0.0

    best_intent = max(scores, key=scores.get)
    best_score = scores[best_intent]
    confidence = min(best_score / 4.0, 1.0)

    if best_score <= 0:
        return "general", 0.0

    return best_intent, confidence


def detect_intent(command):
    intent, confidence = detect_intent_with_confidence(command)

    if confidence < 0.25:
        return "general"

    return intent