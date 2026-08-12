import re
from groq import Groq
from config.settings import GROQ_API_KEY, MODEL_NAME
from memory.vector_memory import store_memory
from agents.memory.learning_agent import learn_preference, get_preference


client = Groq(api_key=GROQ_API_KEY)


def clean(text):
    if not text:
        return "I couldn't build a workout plan right now."

    text = str(text)
    text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"`{3}[\w]*\n?", "", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def detect_fitness_goal(text):
    text = text.lower()

    goal_map = {
        "weight loss": ["weight loss", "lose weight", "fat loss", "burn fat", "slim down"],
        "muscle gain": ["muscle gain", "gain muscle", "build muscle", "bulk", "hypertrophy"],
        "strength": ["strength", "get stronger", "powerlifting", "stronger"],
        "fitness": ["fitness", "exercise", "workout", "routine", "stay fit"],
        "home workout": ["home workout", "at home", "without gym", "no equipment"],
    }

    for goal, phrases in goal_map.items():
        if any(p in text for p in phrases):
            return goal

    return None


def detect_experience_level(text):
    text = text.lower()

    if any(x in text for x in ["beginner", "new to gym", "starting out", "just starting"]):
        return "beginner"
    if any(x in text for x in ["intermediate", "some experience"]):
        return "intermediate"
    if any(x in text for x in ["advanced", "experienced", "athlete"]):
        return "advanced"

    return None


def detect_days_per_week(text):
    match = re.search(r"(\d+)\s*(days|day)", text.lower())
    if match:
        days = int(match.group(1))
        if 1 <= days <= 7:
            return days
    return None


def build_quick_template(goal, level, days):
    level = level or "beginner"
    days = days or 4
    goal = goal or "fitness"

    if goal == "weight loss":
        return (
            f"FITNESS PLAN\n\n"
            f"Goal: Weight Loss\n"
            f"Level: {level.capitalize()}\n"
            f"Days Per Week: {days}\n\n"
            f"SCHEDULE:\n"
            f"Day 1: Full body workout + 20 min cardio\n"
            f"Day 2: Walking or light cardio\n"
            f"Day 3: Lower body + core\n"
            f"Day 4: Upper body + 15 min cardio\n"
            f"Day 5: Active recovery\n"
            f"Day 6: Full body circuit\n"
            f"Day 7: Rest\n\n"
            f"NOTES:\n"
            f"- Focus on calorie control\n"
            f"- Sleep 7 to 8 hours\n"
            f"- Stay consistent\n"
        )

    if goal == "muscle gain":
        return (
            f"FITNESS PLAN\n\n"
            f"Goal: Muscle Gain\n"
            f"Level: {level.capitalize()}\n"
            f"Days Per Week: {days}\n\n"
            f"SCHEDULE:\n"
            f"Day 1: Chest + triceps\n"
            f"Day 2: Back + biceps\n"
            f"Day 3: Rest or light cardio\n"
            f"Day 4: Legs\n"
            f"Day 5: Shoulders + abs\n"
            f"Day 6: Optional weak-point training\n"
            f"Day 7: Rest\n\n"
            f"NOTES:\n"
            f"- Eat enough protein\n"
            f"- Progressively increase weights\n"
            f"- Prioritize recovery\n"
        )

    if goal == "home workout":
        return (
            f"FITNESS PLAN\n\n"
            f"Goal: Home Workout\n"
            f"Level: {level.capitalize()}\n"
            f"Days Per Week: {days}\n\n"
            f"SCHEDULE:\n"
            f"Day 1: Push-ups, squats, plank\n"
            f"Day 2: Walking or stretching\n"
            f"Day 3: Lunges, glute bridge, mountain climbers\n"
            f"Day 4: Rest\n"
            f"Day 5: Full body circuit\n"
            f"Day 6: Core + mobility\n"
            f"Day 7: Rest\n\n"
            f"NOTES:\n"
            f"- Focus on form first\n"
            f"- Increase reps gradually\n"
            f"- Stay consistent\n"
        )

    return (
        f"FITNESS PLAN\n\n"
        f"Goal: General Fitness\n"
        f"Level: {level.capitalize()}\n"
        f"Days Per Week: {days}\n\n"
        f"SCHEDULE:\n"
        f"Day 1: Full body strength\n"
        f"Day 2: Cardio\n"
        f"Day 3: Upper body\n"
        f"Day 4: Lower body + core\n"
        f"Day 5: Light cardio or mobility\n"
        f"Day 6: Full body circuit\n"
        f"Day 7: Rest\n\n"
        f"NOTES:\n"
        f"- Warm up before training\n"
        f"- Progress gradually\n"
        f"- Prioritize consistency\n"
    )


def build_ai_prompt(goal, level, days, user_request):
    return (
        "You are VORIS Fitness Agent, part of a JARVIS-style assistant system. "
        "Create a realistic, practical fitness plan in plain text.\n\n"
        "Requirements:\n"
        "- Keep it structured and actionable\n"
        "- Adapt to the user's goal and experience level\n"
        "- Include warm-up, workout split, recovery, and basic nutrition guidance\n"
        "- Keep it safe and beginner-aware if uncertain\n"
        "- Do not use markdown symbols like *, #, or backticks\n\n"
        "Structure:\n"
        "FITNESS PLAN\n"
        "GOAL\n"
        "LEVEL\n"
        "DAYS PER WEEK\n"
        "WEEKLY SCHEDULE\n"
        "KEY EXERCISES\n"
        "RECOVERY NOTES\n"
        "NUTRITION BASICS\n"
        "IMPORTANT SAFETY NOTE\n\n"
        f"Detected goal: {goal or 'unknown'}\n"
        f"Detected level: {level or 'unknown'}\n"
        f"Detected days: {days or 'unknown'}\n"
        f"User request: {user_request}"
    )


def get_workout_plan(goal):
    try:
        detected_goal = detect_fitness_goal(goal)
        detected_level = detect_experience_level(goal) or get_preference("fitness_level", None)
        detected_days = detect_days_per_week(goal) or 4

        if detected_goal:
            learn_preference("fitness_goal", detected_goal)
        if detected_level:
            learn_preference("fitness_level", detected_level)

        quick_plan = build_quick_template(detected_goal, detected_level, detected_days)

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": build_ai_prompt(detected_goal, detected_level, detected_days, goal)
                },
                {
                    "role": "user",
                    "content": f"Create the best workout plan for this request: {goal}"
                }
            ],
            max_tokens=1200,
            temperature=0.3
        )

        ai_result = response.choices[0].message.content if response.choices else ""
        ai_result = clean(ai_result)

        store_memory(
            f"Fitness plan requested: {goal}",
            {
                "type": "fitness",
                "goal": detected_goal or "",
                "level": detected_level or "",
                "days": detected_days
            }
        )

        if ai_result:
            return ai_result

        return quick_plan

    except Exception:
        fallback_goal = detect_fitness_goal(goal)
        fallback_level = detect_experience_level(goal)
        fallback_days = detect_days_per_week(goal) or 4
        return build_quick_template(fallback_goal, fallback_level, fallback_days)