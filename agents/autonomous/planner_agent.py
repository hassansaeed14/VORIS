from groq import Groq
from config.settings import GROQ_API_KEY, MODEL_NAME
import re

client = Groq(api_key=GROQ_API_KEY)


# -------------------------------
# BASIC TASK PARSER (REAL)
# -------------------------------

def simple_plan(user_request):
    text = user_request.lower()

    plans = []

    if "build" in text or "create" in text:
        plans = [
            "Understand requirements",
            "Design structure",
            "Write implementation",
            "Test functionality",
            "Fix issues",
            "Deploy or finalize"
        ]

    elif "learn" in text or "study" in text:
        plans = [
            "Understand fundamentals",
            "Study core concepts",
            "Practice with examples",
            "Build small projects",
            "Review mistakes",
            "Advance to complex topics"
        ]

    elif "project" in text:
        plans = [
            "Define project scope",
            "Break into modules",
            "Assign tasks",
            "Develop step by step",
            "Test each module",
            "Finalize and deploy"
        ]

    return plans


# -------------------------------
# AI PLANNER (ADVANCED)
# -------------------------------

def ai_plan(user_request):

    prompt = f"""
You are VORIS Planner Agent (advanced).

Break the request into structured steps.

Rules:
- Be practical and actionable
- Keep steps clear and short
- Add phases if needed

Format:

PLAN FOR: [goal]

PHASE 1:
1. ...
2. ...

PHASE 2:
1. ...
2. ...

FINAL STEP:
[completion step]

User request:
{user_request}
"""

    completion = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3,
        max_tokens=800
    )

    return completion.choices[0].message.content


# -------------------------------
# HYBRID PLANNER (MAIN)
# -------------------------------

def create_plan(user_request):

    print(f"\nVORIS Planner Agent: {user_request}")

    # 1. Try REAL fast plan
    basic = simple_plan(user_request)

    # If simple plan is enough → return instantly
    if basic:
        result = "QUICK PLAN\n\n"
        for i, step in enumerate(basic, 1):
            result += f"{i}. {step}\n"
        return result

    # 2. Otherwise use AI planner
    return ai_plan(user_request)


# -------------------------------
# PLAN TO STRUCTURED DATA
# -------------------------------

def parse_plan_to_steps(plan_text):
    """
    Convert plan text → list of steps
    """

    lines = plan_text.split("\n")
    steps = []

    for line in lines:
        match = re.match(r"\d+\.\s+(.*)", line.strip())
        if match:
            steps.append(match.group(1))

    return steps


# -------------------------------
# NEXT STEP SUGGESTION
# -------------------------------

def get_next_step(plan_text, completed_steps_count):
    steps = parse_plan_to_steps(plan_text)

    if completed_steps_count < len(steps):
        return f"NEXT STEP:\n{steps[completed_steps_count]}"
    else:
        return "All steps completed."