import json
import os
import re
import datetime
from groq import Groq
from config.settings import GROQ_API_KEY, MODEL_NAME
from memory.vector_memory import store_memory


client = Groq(api_key=GROQ_API_KEY)
TASKS_FILE = "memory/tasks.json"


def clean(text):
    if not text:
        return "I couldn't create a task response right now."

    text = str(text)
    text = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"`{3}[\w]*\n?", "", text)
    text = re.sub(r"`(.+?)`", r"\1", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def load_tasks():
    if not os.path.exists(TASKS_FILE):
        return []

    try:
        with open(TASKS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []


def save_tasks(tasks):
    os.makedirs(os.path.dirname(TASKS_FILE), exist_ok=True)
    with open(TASKS_FILE, "w", encoding="utf-8") as f:
        json.dump(tasks, f, indent=4, ensure_ascii=False)


def get_next_task_id(tasks):
    if not tasks:
        return 1
    return max(task.get("id", 0) for task in tasks) + 1


def add_task(task, priority="medium", due_date=None):
    try:
        tasks = load_tasks()

        new_task = {
            "id": get_next_task_id(tasks),
            "task": task.strip(),
            "priority": priority.lower(),
            "due_date": due_date,
            "status": "pending",
            "created": datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
        }

        tasks.append(new_task)
        save_tasks(tasks)

        store_memory(
            f"Task added: {task}",
            {
                "type": "task",
                "action": "add",
                "priority": priority.lower()
            }
        )

        return (
            "TASK ADDED\n\n"
            f"Task: {new_task['task']}\n"
            f"Priority: {new_task['priority'].upper()}\n"
            f"Due Date: {due_date or 'Not set'}\n"
            "Status: PENDING\n"
            f"Task ID: {new_task['id']}"
        )

    except Exception as e:
        return f"Task Agent error while adding task: {str(e)}"


def get_tasks(status=None):
    try:
        tasks = load_tasks()

        if not tasks:
            return "No tasks found. Add a task by saying add task followed by your task."

        if status:
            tasks = [t for t in tasks if t.get("status") == status.lower()]

        if not tasks:
            return f"No {status} tasks found."

        pending = [t for t in tasks if t.get("status") == "pending"]
        completed = [t for t in tasks if t.get("status") == "completed"]

        result = "YOUR TASKS\n\n"

        if pending:
            result += "PENDING TASKS:\n"
            for task in pending:
                result += (
                    f"{task['id']}. {task['task']}\n"
                    f"   Priority: {task.get('priority', 'medium').upper()} | "
                    f"Due: {task.get('due_date') or 'Not set'}\n\n"
                )

        if completed:
            result += "COMPLETED TASKS:\n"
            for task in completed:
                result += (
                    f"{task['id']}. {task['task']}\n"
                    f"   Completed At: {task.get('completed_at', 'Unknown')}\n\n"
                )

        return result.strip()

    except Exception as e:
        return f"Task Agent error while reading tasks: {str(e)}"


def complete_task(task_id):
    try:
        tasks = load_tasks()
        task_id = int(task_id)

        for task in tasks:
            if task.get("id") == task_id:
                task["status"] = "completed"
                task["completed_at"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
                save_tasks(tasks)

                store_memory(
                    f"Task completed: {task['task']}",
                    {
                        "type": "task",
                        "action": "complete"
                    }
                )

                return f"Task {task_id} marked as completed: {task['task']}"

        return f"Task {task_id} not found."

    except ValueError:
        return "Please provide a valid numeric task ID."
    except Exception as e:
        return f"Task Agent error while completing task: {str(e)}"


def delete_task(task_id):
    try:
        tasks = load_tasks()
        task_id = int(task_id)

        task_to_delete = next((t for t in tasks if t.get("id") == task_id), None)
        if not task_to_delete:
            return f"Task {task_id} not found."

        updated_tasks = [t for t in tasks if t.get("id") != task_id]
        save_tasks(updated_tasks)

        store_memory(
            f"Task deleted: {task_to_delete['task']}",
            {
                "type": "task",
                "action": "delete"
            }
        )

        return f"Task {task_id} deleted: {task_to_delete['task']}"

    except ValueError:
        return "Please provide a valid numeric task ID."
    except Exception as e:
        return f"Task Agent error while deleting task: {str(e)}"


def plan_tasks(goal):
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are VORIS Task Agent, an expert planner and project manager. "
                        "Break down goals into realistic actionable tasks in plain text.\n\n"
                        "Structure:\n"
                        "TASK PLAN FOR: [goal]\n\n"
                        "PHASE 1\n"
                        "Task 1\n"
                        "Task 2\n\n"
                        "PHASE 2\n"
                        "Task 1\n"
                        "Task 2\n\n"
                        "TIMELINE\n"
                        "PRIORITY ORDER\n"
                        "SUCCESS METRICS\n\n"
                        "Do not use markdown symbols like *, #, or backticks."
                    )
                },
                {
                    "role": "user",
                    "content": f"Create a task plan for: {goal}"
                }
            ],
            max_tokens=1000,
            temperature=0.4
        )

        result = response.choices[0].message.content if response.choices else ""
        cleaned = clean(result)

        store_memory(
            f"Task plan created for: {goal}",
            {
                "type": "task_plan"
            }
        )

        return cleaned

    except Exception as e:
        return f"Task planning error: {str(e)}"