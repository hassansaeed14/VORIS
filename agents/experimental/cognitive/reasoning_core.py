CAPABILITY_MODE = "placeholder"

from groq import Groq
from config.settings import GROQ_API_KEY, MODEL_NAME

client = Groq(api_key=GROQ_API_KEY)


def reasoning_chain(problem):

    prompt = f"""
Solve this problem step by step.

Problem:
{problem}

Show reasoning before final answer.
"""

    completion = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )

    return completion.choices[0].message.content