import re
from groq import Groq
from config.settings import GROQ_API_KEY, MODEL_NAME


client = Groq(api_key=GROQ_API_KEY)


# -------------------------------
# FAST LOCAL LANGUAGE DETECTION (REAL)
# -------------------------------

def detect_language_fast(text):
    text = str(text)

    urdu_chars = set("ابتثجحخدذرزسشصضطظعغفقکگلمنوہیئاآ")
    arabic_chars = set("ابتثجحخدذرزسشصضطظعغفقكلمنهوية")

    urdu_count = sum(1 for c in text if c in urdu_chars)
    arabic_count = sum(1 for c in text if c in arabic_chars)

    if urdu_count > 2:
        return "urdu"
    if arabic_count > 2:
        return "arabic"

    # Simple English detection fallback
    if re.search(r"[a-zA-Z]", text):
        return "english"

    return "unknown"


# -------------------------------
# AI LANGUAGE DETECTION (FALLBACK)
# -------------------------------

def detect_language_ai(text):
    try:
        prompt = f"""
Detect the language of this text.

Return ONLY one word (like: english, urdu, arabic, french).

Text:
{text}
"""

        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )

        return completion.choices[0].message.content.strip().lower()

    except Exception:
        return "english"


# -------------------------------
# FINAL LANGUAGE DETECTION (HYBRID)
# -------------------------------

def detect_language(text):
    fast = detect_language_fast(text)

    # If confident → return immediately (REAL path)
    if fast in ["english", "urdu", "arabic"]:
        return fast

    # Otherwise use AI fallback
    return detect_language_ai(text)


# -------------------------------
# RESPONSE TRANSLATION (HYBRID)
# -------------------------------

def respond_in_language(response, language):
    if not response:
        return response

    language = str(language).lower().strip()

    # No translation needed
    if language in ["english", "en", "unknown"]:
        return response

    try:
        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a translation engine. "
                        "Translate clearly and naturally. "
                        "Do not add explanations. Only translate."
                    )
                },
                {
                    "role": "user",
                    "content": f"Translate to {language}:\n{response}"
                }
            ],
            temperature=0.2,
            max_tokens=1000
        )

        return completion.choices[0].message.content.strip()

    except Exception:
        return response


# -------------------------------
# SMART RESPONSE PIPELINE
# -------------------------------

def process_multilingual_response(user_input, response):
    """
    Detect user language and translate response automatically
    """

    language = detect_language(user_input)

    translated = respond_in_language(response, language)

    return translated, language