CAPABILITY_MODE = "hybrid"

import re
import requests
from groq import Groq
from config.settings import GROQ_API_KEY, MODEL_NAME
from memory.vector_memory import store_memory


client = Groq(api_key=GROQ_API_KEY)


def clean(text):
    if not text:
        return "Couldn't fetch a joke right now."

    text = str(text)
    text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def get_joke(category="general"):
    try:
        # 😂 Official Joke API (real source)
        url = "https://official-joke-api.appspot.com/random_joke"
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        data = response.json()
        setup = data.get("setup", "")
        punchline = data.get("punchline", "")

        if setup and punchline:
            result = (
                "JOKE\n\n"
                f"{setup}\n\n"
                f"{punchline}"
            )

            store_memory(
                f"Joke told: {setup}",
                {"type": "joke", "source": "api"}
            )

            return result

    except Exception:
        pass

    # 🔥 AI fallback (still smart)
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are VORIS Joke Agent, a witty comedian. "
                        "Tell a clean, funny joke in plain text.\n\n"
                        "Structure:\n"
                        "JOKE\n"
                        "[Setup]\n\n"
                        "[Punchline]\n\n"
                        "Keep it short and natural. No markdown symbols."
                    )
                },
                {
                    "role": "user",
                    "content": f"Tell me a {category} joke"
                }
            ],
            max_tokens=200,
            temperature=0.8
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            f"Joke generated: {category}",
            {"type": "joke", "source": "ai"}
        )

        return cleaned

    except Exception as e:
        return f"Joke Agent error: {str(e)}"


def get_programming_joke():
    return get_joke("programming")


def get_urdu_joke():
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "آپ VORIS Joke Agent ہیں۔ "
                        "صاف اور مزاحیہ اردو لطیفہ سنائیں۔\n\n"
                        "فارمیٹ:\n"
                        "لطیفہ:\n"
                        "[لطیفہ]\n\n"
                        "مزاح:\n"
                        "[مزاحیہ نکتہ]"
                    )
                },
                {
                    "role": "user",
                    "content": "ایک مزاحیہ لطیفہ سنائیں"
                }
            ],
            max_tokens=200,
            temperature=0.9
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            "Urdu joke generated",
            {"type": "joke", "language": "urdu"}
        )

        return cleaned

    except Exception as e:
        return f"Urdu Joke error: {str(e)}"