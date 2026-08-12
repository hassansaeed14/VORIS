CAPABILITY_MODE = "placeholder"

import json
import os
import datetime

MEMORY_PATH = "memory/cognitive/aura_memory.json"


def load_memory():

    if not os.path.exists(MEMORY_PATH):
        return {
            "interactions": [],
            "strategies": [],
            "failures": [],
            "agent_scores": {}
        }

    with open(MEMORY_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_memory(memory):

    with open(MEMORY_PATH, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=4)


def store_interaction(user_input, response):

    memory = load_memory()

    memory["interactions"].append({
        "time": str(datetime.datetime.now()),
        "input": user_input,
        "response": response
    })

    save_memory(memory)


def store_failure(error):

    memory = load_memory()

    memory["failures"].append({
        "time": str(datetime.datetime.now()),
        "error": error
    })

    save_memory(memory)