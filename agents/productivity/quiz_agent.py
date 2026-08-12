import re
from groq import Groq
from config.settings import GROQ_API_KEY, MODEL_NAME
from memory.vector_memory import store_memory


client = Groq(api_key=GROQ_API_KEY)


def clean(text):
    if not text:
        return "I couldn't generate quiz content right now."

    text = str(text)
    text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"`{3}[\w]*\n?", "", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def generate_quiz(topic, num_questions=5, difficulty="medium"):
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are VORIS Quiz Agent, an expert educator. "
                        f"Generate a {difficulty} difficulty quiz in plain text.\n\n"
                        "Structure:\n"
                        "QUIZ TITLE\n"
                        "Difficulty\n\n"
                        "For each question:\n"
                        "Question\n"
                        "A)\nB)\nC)\nD)\n"
                        "Correct Answer\n"
                        "Explanation\n\n"
                        "End with a summary.\n\n"
                        "Do not use markdown symbols like *, #, or backticks."
                    )
                },
                {
                    "role": "user",
                    "content": f"Generate {num_questions} {difficulty} questions about: {topic}"
                }
            ],
            max_tokens=2000,
            temperature=0.4
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            f"Quiz generated: {topic}",
            {
                "type": "quiz",
                "difficulty": difficulty,
                "questions": num_questions
            }
        )

        return cleaned

    except Exception as e:
        return f"Quiz Agent error: {str(e)}"


def check_answer(question, user_answer, correct_answer):
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are VORIS Quiz Agent. "
                        "Check the answer and explain clearly in plain text.\n\n"
                        "Structure:\n"
                        "ANSWER CHECK\n"
                        "Your Answer\n"
                        "Correct Answer\n"
                        "Result\n"
                        "Explanation\n\n"
                        "Do not use markdown symbols."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        f"Question: {question}\n"
                        f"User Answer: {user_answer}\n"
                        f"Correct Answer: {correct_answer}"
                    )
                }
            ],
            max_tokens=500,
            temperature=0.2
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            "Answer checked",
            {
                "type": "quiz_check"
            }
        )

        return cleaned

    except Exception as e:
        return f"Answer check error: {str(e)}"


def generate_flashcards(topic, num_cards=10):
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are VORIS Quiz Agent, an expert teacher. "
                        "Generate clear flashcards in plain text.\n\n"
                        "Structure:\n"
                        "CARD 1\nFRONT\nBACK\n\n"
                        "Repeat for all cards.\n\n"
                        "Do not use markdown symbols."
                    )
                },
                {
                    "role": "user",
                    "content": f"Generate {num_cards} flashcards about: {topic}"
                }
            ],
            max_tokens=1500,
            temperature=0.4
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            f"Flashcards generated: {topic}",
            {
                "type": "flashcards",
                "count": num_cards
            }
        )

        return cleaned

    except Exception as e:
        return f"Flashcard error: {str(e)}"