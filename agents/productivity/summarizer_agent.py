import re
from groq import Groq
from config.settings import GROQ_API_KEY, MODEL_NAME
from memory.vector_memory import store_memory


client = Groq(api_key=GROQ_API_KEY)


def clean(text):
    if not text:
        return "I couldn't generate a summary right now."

    text = str(text)
    text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"`{3}[\w]*\n?", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def detect_summary_type(text):
    text = text.lower()

    if any(word in text for word in ["bullet", "points", "list"]):
        return "bullet"

    if any(word in text for word in ["detailed", "full", "in depth"]):
        return "detailed"

    return "brief"


def build_summary_prompt(summary_type):
    if summary_type == "detailed":
        return (
            "You are VORIS Summarizer Agent. "
            "Summarize clearly in plain text using this structure:\n\n"
            "DETAILED SUMMARY\n\n"
            "OVERVIEW\n"
            "MAIN TOPICS\n"
            "KEY INSIGHTS\n"
            "CONCLUSION\n\n"
            "Do not use markdown symbols like *, #, or backticks."
        )

    if summary_type == "bullet":
        return (
            "You are VORIS Summarizer Agent. "
            "Summarize clearly in bullet-style plain text:\n\n"
            "Main Idea\n"
            "Key Points\n"
            "Action Items\n\n"
            "Keep it concise. No markdown symbols."
        )

    return (
        "You are VORIS Summarizer Agent. "
        "Summarize clearly in plain text using this structure:\n\n"
        "BRIEF SUMMARY\n"
        "MAIN POINT\n"
        "KEY POINTS\n"
        "CONCLUSION\n\n"
        "Keep it short and clear. No markdown symbols."
    )


def summarize_text(text, summary_type=None):
    try:
        if not summary_type:
            summary_type = detect_summary_type(text)

        system_prompt = build_summary_prompt(summary_type)

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": f"Summarize this:\n{text}"
                }
            ],
            max_tokens=1000,
            temperature=0.3
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            f"Summarized text",
            {
                "type": "summary",
                "mode": summary_type
            }
        )

        return cleaned

    except Exception as e:
        return f"Summarizer error: {str(e)}"


def summarize_topic(topic):
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are VORIS Summarizer Agent. "
                        "Explain and summarize a topic clearly in plain text:\n\n"
                        "TOPIC SUMMARY\n"
                        "WHAT IT IS\n"
                        "KEY FACTS\n"
                        "WHY IT MATTERS\n"
                        "QUICK TAKEAWAY\n\n"
                        "No markdown symbols."
                    )
                },
                {
                    "role": "user",
                    "content": f"Summarize this topic: {topic}"
                }
            ],
            max_tokens=900,
            temperature=0.3
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            f"Summarized topic: {topic}",
            {
                "type": "topic_summary"
            }
        )

        return cleaned

    except Exception as e:
        return f"Topic summarizer error: {str(e)}"