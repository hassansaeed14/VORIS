import re
from groq import Groq
from config.settings import GROQ_API_KEY, MODEL_NAME
from memory.vector_memory import store_memory


client = Groq(api_key=GROQ_API_KEY)


def clean(text):
    if not text:
        return "I couldn't process the writing request right now."

    text = str(text)
    text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"`{3}[\w]*\n?", "", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def check_grammar(text):
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are VORIS Grammar Agent, an expert English teacher and editor. "
                        "Check grammar, spelling, punctuation, and clarity in plain text.\n\n"
                        "Use this structure:\n"
                        "GRAMMAR CHECK REPORT\n\n"
                        "ORIGINAL TEXT\n"
                        "CORRECTED TEXT\n"
                        "ERRORS FOUND\n"
                        "STYLE SUGGESTIONS\n"
                        "OVERALL SCORE\n"
                        "FEEDBACK\n\n"
                        "Do not use markdown symbols like *, #, or backticks."
                    )
                },
                {
                    "role": "user",
                    "content": f"Check grammar of this text: {text}"
                }
            ],
            max_tokens=1000,
            temperature=0.2
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            f"Grammar checked: {text[:120]}",
            {
                "type": "grammar_check"
            }
        )

        return cleaned

    except Exception as e:
        return f"Grammar Agent error: {str(e)}"


def improve_writing(text, style="professional"):
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are VORIS Grammar Agent, an expert writing editor. "
                        f"Improve the writing to be more {style} in plain text.\n\n"
                        "Use this structure:\n"
                        "WRITING IMPROVEMENT\n\n"
                        "ORIGINAL\n"
                        f"IMPROVED ({style})\n"
                        "CHANGES MADE\n"
                        "TIPS FOR BETTER WRITING\n\n"
                        "Do not use markdown symbols like *, #, or backticks."
                    )
                },
                {
                    "role": "user",
                    "content": f"Improve this text in {style} style: {text}"
                }
            ],
            max_tokens=1000,
            temperature=0.3
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            f"Writing improved: {text[:120]}",
            {
                "type": "writing_improvement",
                "style": style
            }
        )

        return cleaned

    except Exception as e:
        return f"Writing Improvement error: {str(e)}"


def paraphrase(text):
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are VORIS Grammar Agent, an expert paraphrasing assistant. "
                        "Paraphrase the text in 3 different ways in plain text.\n\n"
                        "Use this structure:\n"
                        "PARAPHRASE OPTIONS\n\n"
                        "ORIGINAL\n"
                        "VERSION 1 (Formal)\n"
                        "VERSION 2 (Simple)\n"
                        "VERSION 3 (Creative)\n\n"
                        "Do not use markdown symbols like *, #, or backticks."
                    )
                },
                {
                    "role": "user",
                    "content": f"Paraphrase this text: {text}"
                }
            ],
            max_tokens=850,
            temperature=0.5
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            f"Paraphrased: {text[:120]}",
            {
                "type": "paraphrase"
            }
        )

        return cleaned

    except Exception as e:
        return f"Paraphrase error: {str(e)}"