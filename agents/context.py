from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, List, Optional


@dataclass(slots=True)
class VORISContext:
    user_id: str = "guest"
    session_id: str = "default"
    current_mode: str = "hybrid"
    language: str = "en"
    memory: Any = None
    trust_level: str = "safe"
    conversation_history: List[dict[str, Any]] = field(default_factory=list)
    active_agents: List[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def activate(self, agent_name: str) -> None:
        normalized = str(agent_name or "").strip()
        if normalized and normalized not in self.active_agents:
            self.active_agents.append(normalized)

    def remember_turn(self, *, role: str, content: str, agent: Optional[str] = None) -> None:
        text = str(content or "").strip()
        if not text:
            return
        self.conversation_history.append(
            {
                "role": str(role or "system").strip(),
                "content": text,
                "agent": str(agent or "").strip() or None,
            }
        )
        if len(self.conversation_history) > 20:
            del self.conversation_history[:-20]


# Backward-compatible alias kept for pre-rename importers.
AURAContext = VORISContext
