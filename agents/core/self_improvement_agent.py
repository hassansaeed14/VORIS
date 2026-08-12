import json
import os
import datetime
from collections import Counter

IMPROVEMENT_FILE = "memory/aura_improvement_log.json"


def initialize_data():
    return {
        "failures": [],
        "low_confidence_commands": [],
        "agent_errors": [],
        "user_corrections": [],
        "improvement_suggestions": [],
        "last_reviewed": None
    }


def load_data():
    if not os.path.exists(IMPROVEMENT_FILE):
        return initialize_data()

    try:
        with open(IMPROVEMENT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return initialize_data()

    default = initialize_data()
    for key, value in default.items():
        if key not in data:
            data[key] = value

    return data


def save_data(data):
    os.makedirs(os.path.dirname(IMPROVEMENT_FILE), exist_ok=True)
    with open(IMPROVEMENT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)


def log_failure(command, reason):
    data = load_data()
    data["failures"].append({
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "command": str(command)[:300],
        "reason": str(reason)[:300]
    })
    data["failures"] = data["failures"][-200:]
    save_data(data)


def log_low_confidence(command, confidence):
    data = load_data()
    data["low_confidence_commands"].append({
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "command": str(command)[:300],
        "confidence": float(confidence)
    })
    data["low_confidence_commands"] = data["low_confidence_commands"][-200:]
    save_data(data)


def log_agent_error(agent_name, error_text):
    data = load_data()
    data["agent_errors"].append({
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "agent": str(agent_name),
        "error": str(error_text)[:300]
    })
    data["agent_errors"] = data["agent_errors"][-200:]
    save_data(data)


def log_user_correction(original_command, correction):
    data = load_data()
    data["user_corrections"].append({
        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "original": str(original_command)[:300],
        "correction": str(correction)[:300]
    })
    data["user_corrections"] = data["user_corrections"][-200:]
    save_data(data)


def generate_improvement_report():
    data = load_data()

    if not data["failures"] and not data["agent_errors"] and not data["low_confidence_commands"]:
        return "No major improvement issues detected yet."

    report = "VORIS IMPROVEMENT REPORT\n\n"

    if data["failures"]:
        report += f"Recent failures: {len(data['failures'])}\n"

    if data["low_confidence_commands"]:
        report += f"Low-confidence commands: {len(data['low_confidence_commands'])}\n"

    if data["agent_errors"]:
        report += f"Agent errors: {len(data['agent_errors'])}\n"

    common_agents = Counter(item["agent"] for item in data["agent_errors"]).most_common(3)
    if common_agents:
        report += "\nMost error-prone agents:\n"
        for agent, count in common_agents:
            report += f"- {agent}: {count}\n"

    report += "\nSuggested focus:\n"
    report += "- improve intent detection for ambiguous commands\n"
    report += "- improve multi-command parsing\n"
    report += "- strengthen agents with repeated errors\n"
    report += "- review user correction patterns\n"

    return report