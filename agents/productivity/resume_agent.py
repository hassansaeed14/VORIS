import re
from groq import Groq
from config.settings import GROQ_API_KEY, MODEL_NAME
from memory.vector_memory import store_memory


client = Groq(api_key=GROQ_API_KEY)


def clean(text):
    if not text:
        return "I couldn't generate the resume right now."

    text = str(text)
    text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"`{3}[\w]*\n?", "", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def create_resume(name, field, experience, skills, education):
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are VORIS Resume Agent, an expert career counselor and resume writer. "
                        "Create a professional ATS-friendly resume in plain text.\n\n"
                        "Structure:\n"
                        "RESUME\n\n"
                        "FULL NAME\n"
                        "CONTACT LINE\n"
                        "PROFESSIONAL SUMMARY\n"
                        "SKILLS\n"
                        "WORK EXPERIENCE\n"
                        "EDUCATION\n"
                        "PROJECTS\n"
                        "CERTIFICATIONS\n\n"
                        "Make it realistic, polished, and suitable for hiring. "
                        "Do not use markdown symbols like *, #, or backticks."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Create a resume for:\n"
                        f"Name: {name}\n"
                        f"Field: {field}\n"
                        f"Experience: {experience}\n"
                        f"Skills: {skills}\n"
                        f"Education: {education}"
                    )
                }
            ],
            max_tokens=1500,
            temperature=0.4
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            f"Resume created for {name}",
            {
                "type": "resume",
                "field": field
            }
        )

        return cleaned

    except Exception as e:
        return f"Resume Agent error: {str(e)}"


def improve_resume(resume_text):
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are VORIS Resume Agent, an expert resume editor. "
                        "Improve and strengthen the given resume in plain text.\n\n"
                        "Structure:\n"
                        "IMPROVED RESUME\n\n"
                        "[Enhanced resume]\n\n"
                        "CHANGES MADE\n"
                        "TIPS\n\n"
                        "Do not use markdown symbols like *, #, or backticks."
                    )
                },
                {
                    "role": "user",
                    "content": f"Improve this resume:\n{resume_text}"
                }
            ],
            max_tokens=1500,
            temperature=0.3
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            "Resume improved",
            {
                "type": "resume_improvement"
            }
        )

        return cleaned

    except Exception as e:
        return f"Resume improvement error: {str(e)}"


def get_resume_tips(field):
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are VORIS Resume Agent, an expert career advisor. "
                        "Give practical resume tips for a specific field in plain text.\n\n"
                        "Structure:\n"
                        "RESUME TIPS FOR [FIELD]\n\n"
                        "TOP TIPS\n"
                        "KEYWORDS TO INCLUDE\n"
                        "COMMON MISTAKES TO AVOID\n\n"
                        "Do not use markdown symbols like *, #, or backticks."
                    )
                },
                {
                    "role": "user",
                    "content": f"Give resume tips for this field: {field}"
                }
            ],
            max_tokens=900,
            temperature=0.3
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            f"Resume tips requested for {field}",
            {
                "type": "resume_tips",
                "field": field
            }
        )

        return cleaned

    except Exception as e:
        return f"Resume tips error: {str(e)}"