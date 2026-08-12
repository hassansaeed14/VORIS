import re
from groq import Groq
from config.settings import GROQ_API_KEY, MODEL_NAME
from memory.vector_memory import store_memory


client = Groq(api_key=GROQ_API_KEY)


def clean(text):
    if not text:
        return "Could not generate code."

    text = str(text)
    text = re.sub(r"^```[\w]*\n?", "", text.strip())
    text = re.sub(r"\n```$", "", text.strip())
    return text.strip()


def detect_code_type(task):
    task_lower = task.lower()

    if "python" in task_lower:
        return "python"
    if "javascript" in task_lower or "js" in task_lower:
        return "javascript"
    if "html" in task_lower:
        return "html"
    if "css" in task_lower:
        return "css"
    if "sql" in task_lower:
        return "sql"

    return "python"


def build_prompt(task, language):
    return f"""
You are VORIS Autonomous Coding Agent.

Write clean, working {language} code for the task.

Rules:
- Return code first
- After the code, add a short explanation section
- Keep the code practical and complete
- Include comments only when useful
- Do not use markdown code fences

Format:

CODE:
[working code]

EXPLANATION:
[short explanation]

Task:
{task}
"""


def write_code(task):
    try:
        if not task or len(str(task).strip()) < 3:
            return "Please provide a valid coding task."

        language = detect_code_type(task)

        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "user",
                    "content": build_prompt(task, language)
                }
            ],
            temperature=0.2,
            max_tokens=4096
        )

        result = completion.choices[0].message.content if completion.choices else ""
        cleaned = clean(result)

        store_memory(
            f"Autonomous code generated: {task[:120]}",
            {
                "type": "autonomous_code",
                "language": language
            }
        )

        return cleaned

    except Exception as e:
        return f"Autonomous Coding Agent error: {str(e)}"


def quick_code(task):
    try:
        language = detect_code_type(task)

        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Write only clean working {language} code for this task. "
                        f"Do not add markdown fences.\n\nTask:\n{task}"
                    )
                }
            ],
            temperature=0.1,
            max_tokens=1000
        )

        result = completion.choices[0].message.content if completion.choices else ""
        return clean(result)

    except Exception as e:
        return f"Quick code generation error: {str(e)}"