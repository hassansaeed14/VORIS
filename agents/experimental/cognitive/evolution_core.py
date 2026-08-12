CAPABILITY_MODE = "placeholder"

from agents.cognitive.memory_core import load_memory, save_memory
from groq import Groq
from config.settings import GROQ_API_KEY, MODEL_NAME

client = Groq(api_key=GROQ_API_KEY)


def evolve_system():

    memory = load_memory()

    failures = memory["failures"][-5:]

    if not failures:
        return "No evolution needed."

    prompt = f"""
Analyze these AI failures and suggest improvements.

Failures:
{failures}

Return strategies to improve system reasoning.
"""

    completion = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2
    )

    strategy = completion.choices[0].message.content

    memory["strategies"].append(strategy)

    save_memory(memory)

    return strategy