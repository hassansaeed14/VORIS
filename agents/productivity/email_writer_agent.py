import re
from groq import Groq
from config.settings import GROQ_API_KEY, MODEL_NAME
from memory.vector_memory import store_memory


client = Groq(api_key=GROQ_API_KEY)


def clean(text):
    if not text:
        return "I couldn't generate the email right now."

    text = str(text)
    text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"`{3}[\w]*\n?", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def detect_email_type(text):
    text = text.lower()

    if any(word in text for word in ["apply", "job", "position", "cv", "resume"]):
        return "job"

    if any(word in text for word in ["complaint", "issue", "problem", "bad service"]):
        return "complaint"

    if any(word in text for word in ["follow up", "following up", "update"]):
        return "follow_up"

    if any(word in text for word in ["sorry", "apologize", "apology"]):
        return "apology"

    return "general"


def build_email_prompt(email_type, tone):
    return (
        "You are VORIS Email Writer Agent, an expert business communicator. "
        f"Write a {tone} {email_type} email in plain text.\n\n"
        "Structure:\n\n"
        "Subject: [Clear subject]\n\n"
        "Dear [Recipient],\n\n"
        "[Opening paragraph]\n\n"
        "[Main body]\n\n"
        "[Closing paragraph]\n\n"
        "[Sign-off]\n\n"
        "Make it natural, clear, and realistic. "
        "Do not use markdown symbols like *, #, or backticks."
    )


def write_email(subject, context="", tone="professional", email_type=None):
    try:
        if not email_type:
            email_type = detect_email_type(subject + " " + context)

        system_prompt = build_email_prompt(email_type, tone)

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": f"Write an email about: {subject}. Context: {context}"
                }
            ],
            max_tokens=1000,
            temperature=0.5
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            f"Email written: {subject}",
            {
                "type": "email",
                "email_type": email_type,
                "tone": tone
            }
        )

        return cleaned

    except Exception as e:
        return f"Email Agent error: {str(e)}"