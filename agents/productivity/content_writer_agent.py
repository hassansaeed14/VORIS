import re
from groq import Groq
from config.settings import GROQ_API_KEY, MODEL_NAME
from memory.vector_memory import store_memory


client = Groq(api_key=GROQ_API_KEY)


def clean(text):
    if not text:
        return "I couldn't generate the content right now."

    text = str(text)
    text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"`{3}[\w]*\n?", "", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def detect_content_type(text):
    text = text.lower()

    if any(word in text for word in ["blog", "blog post"]):
        return "blog"
    if any(word in text for word in ["article"]):
        return "article"
    if any(word in text for word in ["social post", "instagram post", "facebook post", "linkedin post", "tweet", "x post"]):
        return "social"
    if any(word in text for word in ["essay"]):
        return "essay"

    return "blog"


def build_content_prompt(content_type, tone, word_count):
    if content_type == "article":
        return (
            "You are VORIS Content Writer Agent, an expert writer and editor. "
            f"Write a {tone} article in plain text of about {word_count} words.\n\n"
            "Structure:\n"
            "ARTICLE TITLE\n"
            "ABSTRACT\n"
            "1. INTRODUCTION\n"
            "2. MAIN CONTENT\n"
            "3. ANALYSIS\n"
            "4. CONCLUSION\n\n"
            "Make it clear, polished, and realistic. "
            "Do not use markdown symbols like *, #, or backticks."
        )

    if content_type == "social":
        return (
            "You are VORIS Content Writer Agent, an expert social media writer. "
            f"Write a {tone} social media post in plain text.\n\n"
            "Structure:\n"
            "POST CAPTION\n"
            "HASHTAGS\n"
            "CALL TO ACTION\n\n"
            "Make it engaging, short, platform-friendly, and realistic. "
            "Do not use markdown symbols like *, #, or backticks."
        )

    if content_type == "essay":
        return (
            "You are VORIS Content Writer Agent, an expert academic writer. "
            f"Write a {tone} essay in plain text of about {word_count} words.\n\n"
            "Structure:\n"
            "ESSAY TITLE\n"
            "THESIS STATEMENT\n"
            "INTRODUCTION\n"
            "BODY PARAGRAPH 1\n"
            "BODY PARAGRAPH 2\n"
            "BODY PARAGRAPH 3\n"
            "CONCLUSION\n\n"
            "Make it coherent, formal, and clear. "
            "Do not use markdown symbols like *, #, or backticks."
        )

    return (
        "You are VORIS Content Writer Agent, an expert blog writer. "
        f"Write a {tone} blog post in plain text of about {word_count} words.\n\n"
        "Structure:\n"
        "BLOG POST TITLE\n"
        "INTRODUCTION\n"
        "SECTION 1\n"
        "SECTION 2\n"
        "SECTION 3\n"
        "CONCLUSION\n"
        "TAGS\n\n"
        "Make it engaging, readable, and useful. "
        "Do not use markdown symbols like *, #, or backticks."
    )


def write_content(topic, content_type="blog", tone="professional", word_count=500):
    try:
        if not content_type:
            content_type = detect_content_type(topic)

        system_prompt = build_content_prompt(content_type, tone, word_count)

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": f"Write {content_type} content about: {topic}"
                }
            ],
            max_tokens=2000,
            temperature=0.6
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            f"Content written: {topic}",
            {
                "type": "content",
                "content_type": content_type,
                "tone": tone,
                "word_count": word_count
            }
        )

        return cleaned

    except Exception as e:
        return f"Content Writer error: {str(e)}"


def write_social_post(topic, platform="instagram", tone="engaging"):
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are VORIS Social Media Expert. "
                        f"Write an engaging {tone} {platform} post in plain text.\n\n"
                        "Structure:\n"
                        "POST CAPTION\n"
                        "HASHTAGS\n"
                        "BEST TIME TO POST\n"
                        "ENGAGEMENT TIP\n\n"
                        "Do not use markdown symbols like *, #, or backticks."
                    )
                },
                {
                    "role": "user",
                    "content": f"Write a {platform} post about: {topic}"
                }
            ],
            max_tokens=900,
            temperature=0.7
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            f"Social post written: {topic}",
            {
                "type": "social_content",
                "platform": platform,
                "tone": tone
            }
        )

        return cleaned

    except Exception as e:
        return f"Social Content error: {str(e)}"