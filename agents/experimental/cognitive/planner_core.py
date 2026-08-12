CAPABILITY_MODE = "placeholder"

from groq import Groq
from config.settings import GROQ_API_KEY, MODEL_NAME

client = Groq(api_key=GROQ_API_KEY)


def generate_plan(goal):

    prompt = f"""
You are an advanced AI planner.

Break the following goal into logical steps.

Goal:
{goal}

Return numbered steps only.
"""

    completion = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.3
    )

    return completion.choices[0].message.content