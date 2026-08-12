CAPABILITY_MODE = "hybrid"

import re
import requests
from groq import Groq
from config.settings import GROQ_API_KEY, MODEL_NAME
from memory.vector_memory import store_memory


client = Groq(api_key=GROQ_API_KEY)


def clean(text):
    if not text:
        return "Couldn't fetch a quote right now."

    text = str(text)
    text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"`{3}[\w]*\n?", "", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def get_quote(category="motivation"):
    try:
        response = requests.get("https://zenquotes.io/api/random", timeout=10)
        response.raise_for_status()
        data = response.json()

        if isinstance(data, list) and data:
            quote = data[0].get("q", "")
            author = data[0].get("a", "Unknown")

            result = (
                "QUOTE\n\n"
                f"{quote}\n\n"
                f"AUTHOR: {author}"
            )

            store_memory(
                f"Quote shown: {quote[:80]}",
                {
                    "type": "quote",
                    "source": "api",
                    "category": category
                }
            )

            return result

    except Exception:
        pass

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are VORIS Quote Agent. "
                        "Share an inspiring and meaningful quote in plain text.\n\n"
                        "Structure:\n"
                        "QUOTE\n"
                        "AUTHOR\n"
                        "MEANING\n"
                        "REFLECTION\n\n"
                        "Do not use markdown symbols like *, #, or backticks."
                    )
                },
                {
                    "role": "user",
                    "content": f"Give me a {category} quote"
                }
            ],
            max_tokens=300,
            temperature=0.7
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            f"Quote generated: {category}",
            {
                "type": "quote",
                "source": "ai",
                "category": category
            }
        )

        return cleaned

    except Exception as e:
        return f"Quote Agent error: {str(e)}"


def get_daily_quote():
    return get_quote("daily inspiration")


def get_islamic_quote():
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are VORIS Quote Agent. "
                        "Share an Islamic quote or hadith in plain text.\n\n"
                        "Structure:\n"
                        "ISLAMIC QUOTE\n"
                        "ARABIC\n"
                        "TRANSLATION\n"
                        "SOURCE\n"
                        "LESSON\n\n"
                        "Be respectful and clear. Do not use markdown symbols."
                    )
                },
                {
                    "role": "user",
                    "content": "Share an Islamic quote or hadith"
                }
            ],
            max_tokens=400,
            temperature=0.5
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            "Islamic quote generated",
            {
                "type": "quote",
                "category": "islamic",
                "source": "ai"
            }
        )

        return cleaned

    except Exception as e:
        return f"Islamic Quote error: {str(e)}"