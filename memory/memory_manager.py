import json
import os

MEMORY_FILE = "memory/user_memory.json"

def load_memory():
    if not os.path.exists(MEMORY_FILE):
        return {}
    with open(MEMORY_FILE, "r") as f:
        return json.load(f)

def save_memory(data):
    with open(MEMORY_FILE, "w") as f:
        json.dump(data, f, indent=4)

def remember(key, value):
    memory = load_memory()
    memory[key] = value
    save_memory(memory)

def recall(key):
    memory = load_memory()
    return memory.get(key, None)

import datetime

CHAT_HISTORY_FILE = "memory/chat_history.json"

def save_chat(user_message, aura_response):
    history = load_chat_history()
    history.append({
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "user": user_message,
        "aura": aura_response
    })
    with open(CHAT_HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=4)

def load_chat_history():
    if not os.path.exists(CHAT_HISTORY_FILE):
        return []
    with open(CHAT_HISTORY_FILE, "r") as f:
        return json.load(f)