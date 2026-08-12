import re
from groq import Groq
from config.settings import GROQ_API_KEY, MODEL_NAME
from memory.vector_memory import store_memory


client = Groq(api_key=GROQ_API_KEY)


def clean(text):
    if not text:
        return "I couldn't generate the cover letter right now."

    text = str(text)
    text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"`{3}[\w]*\n?", "", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def write_cover_letter(name, position, company, experience, skills):
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are VORIS Cover Letter Agent, an expert career coach. "
                        "Write a strong, professional and personalized cover letter in plain text.\n\n"
                        "Structure:\n"
                        "NAME\n"
                        "DATE\n\n"
                        "Hiring Manager\n"
                        "Company\n\n"
                        "Dear Hiring Manager\n\n"
                        "OPENING PARAGRAPH\n"
                        "BODY PARAGRAPH 1\n"
                        "BODY PARAGRAPH 2\n"
                        "BODY PARAGRAPH 3\n"
                        "CLOSING PARAGRAPH\n\n"
                        "Sincerely\n"
                        "NAME\n\n"
                        "Make it compelling, realistic, and tailored to the company. "
                        "Do not use markdown symbols like *, #, or backticks."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Write a cover letter:\n"
                        f"Name: {name}\n"
                        f"Position: {position}\n"
                        f"Company: {company}\n"
                        f"Experience: {experience}\n"
                        f"Skills: {skills}"
                    )
                }
            ],
            max_tokens=1000,
            temperature=0.5
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            f"Cover letter created for {position} at {company}",
            {
                "type": "cover_letter",
                "position": position,
                "company": company
            }
        )

        return cleaned

    except Exception as e:
        return f"Cover Letter error: {str(e)}"