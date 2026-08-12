CAPABILITY_MODE = "hybrid"

import re
import requests
from groq import Groq
from config.settings import GROQ_API_KEY, MODEL_NAME
from memory.vector_memory import store_memory


client = Groq(api_key=GROQ_API_KEY)

PROGRAMMING_TERMS = [
    "python", "java", "javascript", "html", "css", "sql",
    "api", "algorithm", "variable", "function", "class",
    "object", "array", "loop", "recursion", "database",
    "framework", "library", "compiler", "debugging", "git",
    "react", "node", "django", "flask", "machine learning",
    "ai", "neural network", "deep learning", "data science"
]


def clean(text):
    if not text:
        return "I couldn't find a definition right now."

    text = str(text)
    text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"`{3}[\w]*\n?", "", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_word_input(word):
    word = str(word).strip()

    prefixes = [
        "define ",
        "meaning of ",
        "definition of ",
        "what does ",
        "synonym of ",
        "antonym of "
    ]

    lowered = word.lower()
    for prefix in prefixes:
        if lowered.startswith(prefix):
            word = word[len(prefix):].strip()
            break

    word = word.replace("mean in english", "").strip(" ?.")
    return word


def define_programming_term(term):
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are VORIS Dictionary Agent specializing in programming and technology. "
                        "Define technical terms clearly in plain text.\n\n"
                        "Structure:\n"
                        "TERM\n"
                        "TYPE\n"
                        "DEFINITION\n"
                        "KEY FEATURES\n"
                        "COMMON USE CASES\n"
                        "EXAMPLE\n\n"
                        "Do not use markdown symbols like *, #, or backticks."
                    )
                },
                {
                    "role": "user",
                    "content": f"Define this programming term: {term}"
                }
            ],
            max_tokens=650,
            temperature=0.3
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            f"Defined programming term: {term}",
            {
                "type": "dictionary",
                "category": "programming"
            }
        )

        return cleaned

    except Exception as e:
        return f"Programming dictionary error: {str(e)}"


def define_word(word):
    word = clean_word_input(word)

    if not word:
        return "Please provide a word to define."

    if word.lower() in PROGRAMMING_TERMS:
        return define_programming_term(word)

    try:
        url = f"https://api.dictionaryapi.dev/api/v2/entries/en/{word}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if isinstance(data, list) and data:
            entry = data[0]
            word_text = entry.get("word", word)
            phonetic = entry.get("phonetic", "")
            meanings = entry.get("meanings", [])

            result = f"WORD: {word_text.upper()}\n"
            if phonetic:
                result += f"PRONUNCIATION: {phonetic}\n"
            result += "\n"

            for i, meaning in enumerate(meanings[:3], 1):
                part = meaning.get("partOfSpeech", "unknown")
                result += f"{i}. {part.upper()}\n"

                definitions = meaning.get("definitions", [])
                for definition in definitions[:2]:
                    result += f"Definition: {definition.get('definition', '')}\n"
                    example = definition.get("example")
                    if example:
                        result += f"Example: {example}\n"
                result += "\n"

            synonyms = meanings[0].get("synonyms", [])[:5] if meanings else []
            if synonyms:
                result += f"Synonyms: {', '.join(synonyms)}\n"

            store_memory(
                f"Defined word: {word_text}",
                {
                    "type": "dictionary",
                    "category": "general"
                }
            )

            return result.strip()

    except requests.exceptions.RequestException:
        pass
    except Exception:
        pass

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are VORIS Dictionary Agent. "
                        "Define words clearly in plain text.\n\n"
                        "Structure:\n"
                        "WORD\n"
                        "PRONUNCIATION\n"
                        "PART OF SPEECH\n"
                        "DEFINITION\n"
                        "EXAMPLE\n"
                        "SYNONYMS\n"
                        "ANTONYMS\n\n"
                        "Do not use markdown symbols like *, #, or backticks."
                    )
                },
                {
                    "role": "user",
                    "content": f"Define this word: {word}"
                }
            ],
            max_tokens=500,
            temperature=0.3
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            f"Defined word with AI fallback: {word}",
            {
                "type": "dictionary",
                "category": "fallback"
            }
        )

        return cleaned

    except Exception as e:
        return f"Dictionary Agent error: {str(e)}"


def get_synonyms(word):
    word = clean_word_input(word)

    if not word:
        return "Please provide a word."

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are VORIS Dictionary Agent. "
                        "Give useful synonyms and antonyms in plain text.\n\n"
                        "Structure:\n"
                        "WORD\n"
                        "SYNONYMS\n"
                        "ANTONYMS\n"
                        "USAGE NOTE\n\n"
                        "Do not use markdown symbols."
                    )
                },
                {
                    "role": "user",
                    "content": f"Give synonyms and antonyms for: {word}"
                }
            ],
            max_tokens=350,
            temperature=0.3
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            f"Synonyms requested for: {word}",
            {
                "type": "synonyms"
            }
        )

        return cleaned

    except Exception as e:
        return f"Synonym Agent error: {str(e)}"