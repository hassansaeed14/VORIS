from groq import Groq
from config.settings import GROQ_API_KEY, MODEL_NAME

client = Groq(api_key=GROQ_API_KEY)


# -------------------------------
# RULE-BASED TOOL SELECTION (FAST)
# -------------------------------

def rule_based_tool(task):
    task = task.lower()

    if any(k in task for k in ["code", "program", "build function", "write script"]):
        return "coding_agent"

    if any(k in task for k in ["fix", "debug", "error", "bug"]):
        return "debug_agent"

    if any(k in task for k in ["search", "research", "find info", "look up"]):
        return "web_agent"

    if any(k in task for k in ["file", "save", "read file", "open file"]):
        return "file_agent"

    if any(k in task for k in ["calculate", "math", "solve"]):
        return "math_agent"

    return None


# -------------------------------
# AI TOOL SELECTION (SMART)
# -------------------------------

def ai_tool_selection(task):
    try:
        prompt = f"""
You are VORIS Tool Selector.

Choose the BEST tool for this task.

Available tools:
- coding_agent
- debug_agent
- web_agent
- file_agent
- math_agent
- general_agent

Rules:
- Return ONLY the tool name
- No explanation

Task:
{task}
"""

        completion = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
            temperature=0
        )

        tool = completion.choices[0].message.content.strip().lower()

        return tool

    except:
        return "general_agent"


# -------------------------------
# HYBRID SELECTOR (MAIN)
# -------------------------------

def choose_tool(task):
    print(f"[Tool Selector] Task: {task}")

    # 1. Try fast rule-based
    tool = rule_based_tool(task)

    if tool:
        print(f"[Tool Selector] Rule-based → {tool}")
        return tool

    # 2. Fallback to AI
    tool = ai_tool_selection(task)

    print(f"[Tool Selector] AI → {tool}")

    return tool


# -------------------------------
# TOOL CONFIDENCE (OPTIONAL FUTURE)
# -------------------------------

def choose_tool_with_confidence(task):
    tool = rule_based_tool(task)

    if tool:
        return tool, 0.9

    ai_tool = ai_tool_selection(task)
    return ai_tool, 0.6