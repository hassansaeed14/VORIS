from brain.intent_engine import detect_intent_with_confidence
from memory.vector_memory import store_memory, search_memory
from agents.memory.learning_agent import learn_from_interaction


class Orchestrator:
    def __init__(self):
        self.conversation_history = []
        self.active_agent = None
        self.last_intent = None
        self.last_confidence = 0.0
        self.context = {}

    def add_to_history(self, role, content, intent=None):
        if not content:
            return

        self.conversation_history.append({
            "role": role,
            "content": str(content).strip(),
            "intent": intent
        })

        if len(self.conversation_history) > 50:
            self.conversation_history = self.conversation_history[-50:]

    def get_history(self):
        return self.conversation_history

    def get_recent_history(self, limit=10):
        return self.conversation_history[-limit:]

    def clear_history(self):
        self.conversation_history = []

    def set_context(self, key, value):
        self.context[key] = value

    def get_context(self, key, default=None):
        return self.context.get(key, default)

    def get_all_context(self):
        return self.context

    def clear_context(self):
        self.context = {}

    def store_user_turn(self, command, intent, confidence=0.0):
        store_memory(
            command,
            {
                "type": "user_input",
                "intent": intent,
                "confidence": confidence
            }
        )

    def fetch_relevant_memories(self, command, limit=3):
        try:
            return search_memory(command, n_results=limit)
        except Exception as e:
            print(f"[Orchestrator Memory Error] {e}")
            return []

    def build_memory_context(self, command, limit=3):
        memories = self.fetch_relevant_memories(command, limit=limit)

        if not memories:
            return ""

        lines = []
        for memory in memories:
            text = memory.get("text", "").strip()
            if text:
                lines.append(f"- {text}")

        return "\n".join(lines)

    def route(self, command):
        intent, confidence = detect_intent_with_confidence(command)

        if confidence < 0.25:
            intent = "general"

        self.active_agent = intent
        self.last_intent = intent
        self.last_confidence = confidence

        self.add_to_history("user", command, intent=intent)
        self.store_user_turn(command, intent, confidence)

        memory_context = self.build_memory_context(command)
        if memory_context:
            self.set_context("memory_context", memory_context)

        self.set_context("last_user_command", command)
        self.set_context("last_intent", intent)
        self.set_context("last_confidence", confidence)

        return intent, confidence

    def process_response(self, response, intent, learn=False):
        self.add_to_history("assistant", response, intent=intent)

        if learn:
            user_input = self.get_last_user_message()
            try:
                learn_from_interaction(user_input, response, intent)
            except Exception as e:
                print(f"[Orchestrator Learning Error] {e}")

        self.set_context("last_assistant_response", response)
        self.active_agent = intent

        return response

    def get_last_user_message(self):
        for item in reversed(self.conversation_history):
            if item["role"] == "user":
                return item["content"]
        return ""

    def get_last_assistant_message(self):
        for item in reversed(self.conversation_history):
            if item["role"] == "assistant":
                return item["content"]
        return ""

    def get_state_summary(self):
        return {
            "active_agent": self.active_agent,
            "last_intent": self.last_intent,
            "last_confidence": self.last_confidence,
            "history_count": len(self.conversation_history),
            "context_keys": list(self.context.keys())
        }

    def reset_session(self):
        self.clear_history()
        self.clear_context()
        self.active_agent = None
        self.last_intent = None
        self.last_confidence = 0.0


orchestrator = Orchestrator()