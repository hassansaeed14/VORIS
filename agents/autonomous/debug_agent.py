from groq import Groq
from config.settings import GROQ_API_KEY, MODEL_NAME
import re

client = Groq(api_key=GROQ_API_KEY)


# -------------------------------
# CLEAN OUTPUT
# -------------------------------

def clean(text):
    if not text:
        return "Could not fix the code."

    text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"`{3}[\w]*\n?", "", text)
    return text.strip()


# -------------------------------
# QUICK ERROR DETECTION (REAL)
# -------------------------------

def detect_basic_issue(code):
    code_lower = code.lower()

    if "syntaxerror" in code_lower:
        return "syntax error"
    if "indent" in code_lower:
        return "indentation issue"
    if "nameerror" in code_lower:
        return "undefined variable"
    if "typeerror" in code_lower:
        return "type mismatch"

    return None


# -------------------------------
# AI DEBUGGING (DEEP FIX)
# -------------------------------

def ai_fix(code):

    prompt = f"""
You are VORIS Debug Agent.

Fix the code properly and explain briefly.

Format:

ISSUE:
[What is wrong]

FIXED CODE:
[Corrected code]

EXPLANATION:
[Why it was wrong and what changed]

IMPROVEMENT:
[Optional improvement]

Rules:
- Keep code clean
- Do not use markdown symbols
- Do not remove logic unless necessary

Code:
{code}
"""

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        max_tokens=1200
    )

    result = response.choices[0].message.content
    return clean(result)


# -------------------------------
# MAIN DEBUG FUNCTION (HYBRID)
# -------------------------------

def fix_code(code):

    print("\nVORIS Debug Agent running...")

    if not code or len(code.strip()) < 5:
        return "Please provide valid code to debug."

    # 1. Try quick detection (REAL)
    issue = detect_basic_issue(code)

    if issue:
        print(f"[Debug Agent] Detected: {issue}")

    # 2. Always use AI for proper fix (hybrid)
    return ai_fix(code)


# -------------------------------
# QUICK FIX MODE (OPTIONAL)
# -------------------------------

def quick_fix(code):
    """
    Faster but less detailed fix
    """

    response = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[
            {
                "role": "user",
                "content": f"Fix this code and return only corrected version:\n{code}"
            }
        ],
        temperature=0,
        max_tokens=800
    )

    return clean(response.choices[0].message.content)