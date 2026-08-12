import re
from groq import Groq
from config.settings import GROQ_API_KEY, MODEL_NAME
from memory.vector_memory import store_memory


client = Groq(api_key=GROQ_API_KEY)


def clean(text):
    if not text:
        return "I couldn't generate a coding response right now."

    text = str(text)
    text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def detect_coding_mode(request):
    request_lower = request.lower()

    if any(word in request_lower for word in ["debug", "fix", "error", "bug", "not working", "issue"]):
        return "debug"

    if any(word in request_lower for word in ["explain", "understand", "how does this work"]):
        return "explain"

    return "build"


def build_coding_prompt(request):
    mode = detect_coding_mode(request)

    if mode == "debug":
        return (
            "You are VORIS Coding Agent, an expert software engineer and debugger. "
            "Help the user debug code clearly in plain text using this structure:\n\n"
            "DEBUGGING HELP: [Problem]\n\n"
            "1. PROBLEM ANALYSIS\n"
            "2. LIKELY CAUSE\n"
            "3. FIXED SOLUTION\n"
            "4. EXPLANATION OF THE FIX\n"
            "5. HOW TO TEST IT\n"
            "6. IMPROVEMENTS\n\n"
            "Be practical, clear, and educational. "
            "If code is needed, provide complete corrected code. "
            "Do not use markdown symbols like ** or ##."
        )

    if mode == "explain":
        return (
            "You are VORIS Coding Agent, an expert software engineer and teacher. "
            "Explain programming clearly in plain text using this structure:\n\n"
            "CODING EXPLANATION: [Topic]\n\n"
            "1. WHAT IT IS\n"
            "2. HOW IT WORKS\n"
            "3. SIMPLE EXAMPLE\n"
            "4. LINE BY LINE EXPLANATION\n"
            "5. COMMON MISTAKES\n"
            "6. BEST PRACTICES\n\n"
            "Keep it educational and easy to understand. "
            "Do not use markdown symbols like ** or ##."
        )

    return (
        "You are VORIS Coding Agent, an expert software engineer. "
        "Help with programming in plain text using this structure:\n\n"
        "CODING SOLUTION: [Problem]\n\n"
        "1. UNDERSTANDING THE PROBLEM\n"
        "2. APPROACH\n"
        "3. CODE SOLUTION\n"
        "4. CODE EXPLANATION\n"
        "5. HOW TO RUN\n"
        "6. EXAMPLE OUTPUT\n"
        "7. POSSIBLE IMPROVEMENTS\n\n"
        "Be detailed and educational. "
        "Write complete usable code when needed. "
        "Do not use markdown symbols like ** or ##."
    )


def code_help(request):
    try:
        system_prompt = build_coding_prompt(request)

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": f"Help me with this coding request: {request}"
                }
            ],
            max_tokens=2400,
            temperature=0.2
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            f"Code request: {request}",
            {
                "type": "code",
                "mode": detect_coding_mode(request)
            }
        )

        return cleaned

    except Exception as e:
        return f"Coding Agent error: {str(e)}"