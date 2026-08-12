CAPABILITY_MODE = "hybrid"

import math
import re
from groq import Groq
from config.settings import GROQ_API_KEY, MODEL_NAME
from memory.vector_memory import store_memory


client = Groq(api_key=GROQ_API_KEY)


def clean(text):
    if not text:
        return "I couldn't solve the math problem right now."

    text = str(text)
    text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"`{3}[\w]*\n?", "", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_expression(problem):
    expr = problem.lower().strip()

    replacements = {
        "×": "*",
        "x": "*",
        "÷": "/",
        "plus": "+",
        "minus": "-",
        "multiplied by": "*",
        "times": "*",
        "divided by": "/",
        "squared": "**2",
        "cubed": "**3",
        "^": "**",
        "pi": str(math.pi)
    }

    for old, new in replacements.items():
        expr = expr.replace(old, new)

    expr = expr.replace("sqrt", "math.sqrt")
    expr = expr.replace("square root of", "math.sqrt")
    expr = expr.replace("factorial of", "math.factorial")
    expr = expr.replace("%", "/100")

    return expr


def safe_eval_expression(expr):
    allowed_pattern = r"^[0-9\s\+\-\*\/\(\)\.\,]*((math\.sqrt|math\.factorial)[0-9\(\)\.\,\s\+\-\*\/]*)*$"

    if "math" in expr:
        if "math.sqrt" not in expr and "math.factorial" not in expr:
            return None

    compact = expr.replace(",", "")
    if not re.match(r"^[0-9\.\+\-\*\/\(\)\s%a-z_]*$", compact):
        return None

    try:
        result = eval(compact, {"math": math, "__builtins__": {}})
        return result
    except Exception:
        return None


def solve_math(problem):
    try:
        expr = normalize_expression(problem)

        has_digits = any(c.isdigit() for c in expr)
        if has_digits:
            direct_result = safe_eval_expression(expr)
            if direct_result is not None:
                store_memory(
                    f"Math solved directly: {problem}",
                    {
                        "type": "math",
                        "mode": "direct"
                    }
                )

                return (
                    "MATH SOLUTION\n\n"
                    f"Problem: {problem}\n"
                    f"Answer: {direct_result}\n\n"
                    "Calculated directly."
                )

    except Exception:
        pass

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are VORIS Math Agent, an expert mathematician. "
                        "Solve math problems step by step in plain text.\n\n"
                        "Structure:\n"
                        "PROBLEM\n"
                        "SOLUTION\n"
                        "Step 1\n"
                        "Step 2\n"
                        "ANSWER\n"
                        "EXPLANATION\n\n"
                        "Do not use markdown symbols like *, #, or backticks."
                    )
                },
                {
                    "role": "user",
                    "content": f"Solve this math problem: {problem}"
                }
            ],
            max_tokens=1000,
            temperature=0.2
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            f"Math solved with AI: {problem}",
            {
                "type": "math",
                "mode": "ai"
            }
        )

        return cleaned

    except Exception as e:
        return f"Math Agent error: {str(e)}"