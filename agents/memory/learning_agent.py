import json
import os
import datetime
from collections import Counter
from memory.vector_memory import store_memory, search_memory


LEARNING_FILE = "memory/aura_learning.json"


def initialize_learning_data():
    return {
        "user_profile": {
            "name": None,
            "interests": [],
            "preferences": {}
        },
        "topic_frequency": {},
        "interaction_history": [],
        "behavior_stats": {
            "short_queries": 0,
            "medium_queries": 0,
            "long_queries": 0
        },
        "learned_facts": [],
        "intent_sequences": [],
        "intent_weights": {},
        "last_seen": None
    }


def load_data():
    if not os.path.exists(LEARNING_FILE):
        return initialize_learning_data()

    try:
        with open(LEARNING_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return initialize_learning_data()

    default = initialize_learning_data()

    def merge(current, template):
        for key, value in template.items():
            if key not in current:
                current[key] = value
            elif isinstance(value, dict) and isinstance(current.get(key), dict):
                merge(current[key], value)

    merge(data, default)
    return data


def save_data(data):
    os.makedirs(os.path.dirname(LEARNING_FILE), exist_ok=True)
    with open(LEARNING_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def analyze_query_length(text):
    words = len(str(text).split())

    if words < 5:
        return "short"
    if words < 15:
        return "medium"
    return "long"


def extract_fact(user_input):
    text = str(user_input).lower()

    patterns = [
        "my favorite",
        "i like",
        "i love",
        "i prefer",
        "my name is",
        "i usually",
        "i hate",
        "i want",
        "i study",
        "i am learning"
    ]

    for pattern in patterns:
        if pattern in text:
            return str(user_input).strip()

    return None


def extract_interest(user_input):
    text = str(user_input).lower().strip()

    starters = [
        "i like ",
        "i love ",
        "i enjoy ",
        "i am interested in ",
        "my favorite is ",
        "my favorite subject is ",
        "i study "
    ]

    for starter in starters:
        if text.startswith(starter):
            return text.replace(starter, "", 1).strip(" .!?,")

    return None


def learn_from_interaction(user_input, response, intent):
    data = load_data()
    now = datetime.datetime.now()

    data["last_seen"] = now.strftime("%Y-%m-%d %H:%M")

    data.setdefault("topic_frequency", {})
    data.setdefault("intent_weights", {})
    data.setdefault("behavior_stats", {
        "short_queries": 0,
        "medium_queries": 0,
        "long_queries": 0
    })
    data.setdefault("interaction_history", [])
    data.setdefault("intent_sequences", [])
    data.setdefault("learned_facts", [])
    data.setdefault("user_profile", {
        "name": None,
        "interests": [],
        "preferences": {}
    })

    data["topic_frequency"][intent] = data["topic_frequency"].get(intent, 0) + 1
    data["intent_weights"][intent] = data["intent_weights"].get(intent, 0) + 2

    length_type = analyze_query_length(user_input)
    data["behavior_stats"][f"{length_type}_queries"] += 1

    interaction = {
        "time": now.strftime("%Y-%m-%d %H:%M"),
        "intent": intent,
        "input": str(user_input)[:200],
        "response": str(response)[:200],
        "length_type": length_type
    }

    data["interaction_history"].append(interaction)

    if len(data["interaction_history"]) > 300:
        data["interaction_history"] = data["interaction_history"][-300:]

    if len(data["interaction_history"]) >= 2:
        prev_intent = data["interaction_history"][-2]["intent"]
        data["intent_sequences"].append((prev_intent, intent))

    if len(data["intent_sequences"]) > 300:
        data["intent_sequences"] = data["intent_sequences"][-300:]

    fact = extract_fact(user_input)
    if fact and fact not in data["learned_facts"]:
        data["learned_facts"].append(fact)

    if len(data["learned_facts"]) > 100:
        data["learned_facts"] = data["learned_facts"][-100:]

    interest = extract_interest(user_input)
    if interest and interest not in data["user_profile"]["interests"]:
        data["user_profile"]["interests"].append(interest)

    if len(data["user_profile"]["interests"]) > 30:
        data["user_profile"]["interests"] = data["user_profile"]["interests"][-30:]

    store_memory(
        f"User asked: {user_input}",
        {
            "intent": intent,
            "source": "learning_agent"
        }
    )

    save_data(data)


def get_user_insights():
    data = load_data()

    if not data["interaction_history"]:
        return "Still learning about you..."

    top_intents = Counter(data["topic_frequency"]).most_common(5)
    interests = data["user_profile"].get("interests", [])[:5]
    stats = data["behavior_stats"]

    result = "USER PROFILE\n\n"

    result += "Top Intents:\n"
    for i, (intent, count) in enumerate(top_intents, 1):
        result += f"{i}. {intent} -> {count} times\n"

    if interests:
        result += "\nInterests:\n"
        for i, item in enumerate(interests, 1):
            result += f"{i}. {item}\n"

    result += "\nBehavior:\n"
    result += f"Short queries: {stats['short_queries']}\n"
    result += f"Medium queries: {stats['medium_queries']}\n"
    result += f"Long queries: {stats['long_queries']}\n"

    result += f"\nLast seen: {data['last_seen']}\n"
    result += f"Total interactions: {len(data['interaction_history'])}\n"

    return result


def predict_next_intent():
    data = load_data()

    if not data["intent_sequences"]:
        return None

    sequences = Counter(tuple(pair) for pair in data["intent_sequences"])
    most_common = sequences.most_common(1)

    if not most_common:
        return None

    return most_common[0][0][1]


def get_personalized_greeting():
    data = load_data()

    if not data["topic_frequency"]:
        return "Hey! I'm still getting to know you."

    favorite_intent = max(data["topic_frequency"], key=data["topic_frequency"].get)
    interests = data["user_profile"].get("interests", [])

    if interests:
        return f"Welcome back! Ready to continue with {favorite_intent} or talk about {interests[0]}?"

    return f"Welcome back! Want to continue with {favorite_intent}?"


def build_context(user_input):
    memories = search_memory(user_input)

    if not memories:
        return f"User:\n{user_input}"

    context_lines = []
    for memory in memories[:3]:
        text = memory.get("text", "").strip()
        if text:
            context_lines.append(f"- {text}")

    context = "\n".join(context_lines)

    return f"""Relevant memory:
{context}

User:
{user_input}"""


def learn_preference(key, value):
    data = load_data()
    data["user_profile"]["preferences"][key] = value
    save_data(data)

    return f"Got it. I'll remember {key} = {value}"


def get_preference(key, default=None):
    data = load_data()
    return data["user_profile"]["preferences"].get(key, default)


def self_reflection():
    data = load_data()

    if len(data["interaction_history"]) < 30:
        return "Not enough data yet."

    top_topics = Counter(data["topic_frequency"]).most_common(3)

    report = "SELF REPORT\n\n"
    report += "Top skills:\n"

    for topic, count in top_topics:
        report += f"- {topic} ({count})\n"

    report += "\nLearning active and adapting."

    return report