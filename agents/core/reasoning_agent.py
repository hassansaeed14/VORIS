import re
from groq import Groq
from config.settings import GROQ_API_KEY, MODEL_NAME, VORIS_PERSONALITY
from memory.vector_memory import store_memory


client = Groq(api_key=GROQ_API_KEY)


def clean(text):
    if not text:
        return "I couldn't complete the reasoning task right now."

    text = str(text)
    text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"`{3}[\w]*\n?", "", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def reason(problem, context=None):
    try:
        system = (
            f"{VORIS_PERSONALITY} "
            "You are VORIS Reasoning Agent. "
            "Think carefully and explain reasoning in plain text.\n\n"
            "Structure:\n"
            "PROBLEM ANALYSIS\n"
            "UNDERSTANDING\n"
            "REASONING STEPS\n"
            "CONCLUSION\n"
            "CONFIDENCE\n\n"
            "Be logical, balanced, and useful. "
            "Do not use markdown symbols like *, #, or backticks."
        )

        messages = [{"role": "system", "content": system}]

        if context:
            messages.append({
                "role": "user",
                "content": f"Context: {context}"
            })

        messages.append({
            "role": "user",
            "content": f"Reason through this: {problem}"
        })

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=messages,
            max_tokens=1000,
            temperature=0.2
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            f"Reasoned problem: {problem[:120]}",
            {
                "type": "reasoning"
            }
        )

        return cleaned

    except Exception as e:
        return f"Reasoning Agent error: {str(e)}"


def analyze_pros_cons(topic):
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are VORIS Reasoning Agent. "
                        "Analyze pros and cons objectively in plain text.\n\n"
                        "Structure:\n"
                        "PROS AND CONS ANALYSIS\n"
                        "PROS\n"
                        "CONS\n"
                        "VERDICT\n"
                        "RECOMMENDATION\n\n"
                        "Be balanced and practical. "
                        "Do not use markdown symbols like *, #, or backticks."
                    )
                },
                {
                    "role": "user",
                    "content": f"Analyze pros and cons of: {topic}"
                }
            ],
            max_tokens=800,
            temperature=0.3
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            f"Pros/cons analyzed: {topic[:120]}",
            {
                "type": "pros_cons"
            }
        )

        return cleaned

    except Exception as e:
        return f"Pros/Cons analysis error: {str(e)}"


def compare(item1, item2=None):
    try:
        if item2 is None:
            text = str(item1)

            if " vs " in text.lower():
                parts = re.split(r"\s+vs\s+", text, flags=re.IGNORECASE, maxsplit=1)
                if len(parts) == 2:
                    item1, item2 = parts[0].strip(), parts[1].strip()
            elif " versus " in text.lower():
                parts = re.split(r"\s+versus\s+", text, flags=re.IGNORECASE, maxsplit=1)
                if len(parts) == 2:
                    item1, item2 = parts[0].strip(), parts[1].strip()
            elif "compare" in text.lower():
                cleaned_text = re.sub(r"(?i)compare", "", text).strip()
                if " and " in cleaned_text.lower():
                    parts = re.split(r"\s+and\s+", cleaned_text, flags=re.IGNORECASE, maxsplit=1)
                    if len(parts) == 2:
                        item1, item2 = parts[0].strip(), parts[1].strip()

        if not item1 or not item2:
            return "Please provide two items to compare."

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are VORIS Reasoning Agent. "
                        "Compare two items objectively in plain text.\n\n"
                        "Structure:\n"
                        "COMPARISON\n"
                        "ITEM 1\n"
                        "ITEM 2\n"
                        "KEY DIFFERENCES\n"
                        "WINNER OR BEST FIT\n"
                        "USE CASE\n\n"
                        "Be balanced, practical, and clear. "
                        "Do not use markdown symbols like *, #, or backticks."
                    )
                },
                {
                    "role": "user",
                    "content": f"Compare {item1} vs {item2}"
                }
            ],
            max_tokens=850,
            temperature=0.3
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            f"Compared: {item1} vs {item2}",
            {
                "type": "comparison"
            }
        )

        return cleaned

    except Exception as e:
        return f"Comparison error: {str(e)}"