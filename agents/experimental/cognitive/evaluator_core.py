CAPABILITY_MODE = "placeholder"

from groq import Groq
from config.settings import GROQ_API_KEY, MODEL_NAME

client = Groq(api_key=GROQ_API_KEY)


def evaluate_response(user_input, response):

    prompt = f"""
Evaluate the AI response quality from 1-10.

User:
{user_input}

Response:
{response}

Return only a number.
"""

    completion = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0
    )

    try:
        score = int(completion.choices[0].message.content.strip())
    except:
        score = 5

    return score