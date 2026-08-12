import re
from groq import Groq
from config.settings import GROQ_API_KEY, MODEL_NAME
from memory.vector_memory import store_memory


client = Groq(api_key=GROQ_API_KEY)


def clean(text):
    if not text:
        return "I couldn't generate a research response right now."

    text = str(text)
    text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"`{3}[\w]*\n?", "", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"_{2,}", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def is_deep_research_request(topic):
    topic_lower = topic.lower()
    deep_phrases = [
        "research on",
        "research about",
        "thoroughly",
        "deep research",
        "research report",
        "investigation on",
        "analyze this topic",
        "detailed research",
        "full report"
    ]
    return any(phrase in topic_lower for phrase in deep_phrases)


def build_research_prompt(topic):
    if is_deep_research_request(topic):
        return (
            "You are VORIS Research Agent, an expert researcher and analyst. "
            "Write a professional research report in plain text using this structure:\n\n"
            "RESEARCH REPORT: [Topic]\n\n"
            "EXECUTIVE SUMMARY\n"
            "1. BACKGROUND AND OVERVIEW\n"
            "2. KEY FINDINGS\n"
            "3. CURRENT DEVELOPMENTS\n"
            "4. STATISTICS AND DATA\n"
            "5. CHALLENGES AND LIMITATIONS\n"
            "6. RECOMMENDATIONS\n"
            "7. CONCLUSION\n\n"
            "Write clearly, analytically, and in plain text. "
            "Minimum 600 words. "
            "Do not use markdown symbols like *, #, or backticks."
        )

    return (
        "You are VORIS Research Agent, an expert researcher and analyst. "
        "Give a concise research-style overview in plain text using this structure:\n\n"
        "TOPIC OVERVIEW\n"
        "1. BACKGROUND\n"
        "2. MAIN POINTS\n"
        "3. CURRENT RELEVANCE\n"
        "4. CONCLUSION\n\n"
        "Keep it clear and informative. "
        "About 250 to 400 words. "
        "Do not use markdown symbols like *, #, or backticks."
    )


def research(topic):
    try:
        system_prompt = build_research_prompt(topic)

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": f"Research this topic: {topic}"
                }
            ],
            max_tokens=2200,
            temperature=0.3
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            f"Research topic: {topic}",
            {
                "type": "research",
                "topic": topic,
                "mode": "deep" if is_deep_research_request(topic) else "standard"
            }
        )

        return cleaned

    except Exception as e:
        return f"Research Agent error: {str(e)}"


def web_search_simulation(query):
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a search-style research assistant. "
                        "Give accurate and useful findings in plain numbered points. "
                        "Do not use markdown symbols."
                    )
                },
                {
                    "role": "user",
                    "content": f"Find useful information about: {query}"
                }
            ],
            max_tokens=1000,
            temperature=0.2
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            f"Search query: {query}",
            {
                "type": "web_search_simulation",
                "query": query
            }
        )

        return cleaned

    except Exception as e:
        return f"Search simulation error: {str(e)}"