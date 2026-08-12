import re
from groq import Groq
from config.settings import GROQ_API_KEY, MODEL_NAME
from memory.vector_memory import store_memory


client = Groq(api_key=GROQ_API_KEY)


def clean(text):
    if not text:
        return "I couldn't generate a study response right now."

    text = str(text)
    text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"`{3}[\w]*\n?", "", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"_{2,}", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def is_detailed_request(topic):
    topic_lower = topic.lower()

    detailed_phrases = [
        "in detail",
        "detailed",
        "full explanation",
        "comprehensive",
        "study guide",
        "teach me",
        "everything about",
        "assignment on",
        "essay on",
        "deep explanation",
        "elaborate"
    ]

    return any(phrase in topic_lower for phrase in detailed_phrases)


def build_study_prompt(topic):
    if is_detailed_request(topic):
        return (
            "You are VORIS Study Agent, an expert professor and academic tutor. "
            "Create a detailed university-level study guide in plain text. "
            "Use this structure:\n\n"
            "TITLE: [Topic Name]\n\n"
            "1. INTRODUCTION\n"
            "2. MAIN CONCEPTS\n"
            "3. HOW IT WORKS\n"
            "4. REAL WORLD EXAMPLES\n"
            "5. ADVANTAGES AND DISADVANTAGES\n"
            "6. FUTURE PROSPECTS\n"
            "7. CONCLUSION\n\n"
            "Write clearly, deeply, and in a way a student can learn from. "
            "Minimum 700 words. "
            "Do not use markdown symbols like *, #, or backticks."
        )

    return (
        "You are VORIS Study Agent, an expert professor and academic tutor. "
        "Explain the topic clearly for a student in plain text. "
        "Use this structure:\n\n"
        "TITLE: [Topic Name]\n\n"
        "1. INTRODUCTION\n"
        "2. KEY POINTS\n"
        "3. SIMPLE EXAMPLE\n"
        "4. CONCLUSION\n\n"
        "Keep it educational but not too long. "
        "Around 250 to 400 words. "
        "Do not use markdown symbols like *, #, or backticks."
    )


def study(topic):
    try:
        system_prompt = build_study_prompt(topic)

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": f"Explain this topic for study purposes: {topic}"
                }
            ],
            max_tokens=2200,
            temperature=0.4
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            f"Studied topic: {topic}",
            {
                "type": "study",
                "topic": topic,
                "mode": "detailed" if is_detailed_request(topic) else "standard"
            }
        )

        return cleaned

    except Exception as e:
        return f"Study Agent error: {str(e)}"