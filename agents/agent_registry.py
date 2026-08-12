from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from agents.context import VORISContext
from agents.agent_bus import agent_bus
from agents.registry import get_agent_descriptor, list_agents


AgentHandler = Callable[[str, VORISContext], Any]


@dataclass(slots=True)
class RegisteredAgent:
    name: str
    handler: AgentHandler
    metadata: dict[str, Any] = field(default_factory=dict)

    def handle(self, task: str, context: VORISContext) -> Any:
        return self.handler(task, context)


class AgentRegistry:
    _instance: "AgentRegistry | None" = None

    def __new__(cls) -> "AgentRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._agents = {}
            cls._instance._bootstrapped = False
        return cls._instance

    def register(self, agent_name: str, agent_instance: RegisteredAgent | Any) -> Any:
        normalized = str(agent_name or "").strip().lower()
        if not normalized:
            raise ValueError("agent_name is required")
        self._agents[normalized] = agent_instance
        return agent_instance

    def get(self, agent_name: str) -> Any:
        self._ensure_bootstrap()
        return self._agents.get(str(agent_name or "").strip().lower())

    def list_all(self) -> List[str]:
        self._ensure_bootstrap()
        return sorted(self._agents.keys())

    def call(self, agent_name: str, task: str, context: VORISContext | dict[str, Any] | None = None) -> Any:
        self._ensure_bootstrap()
        agent = self.get(agent_name)
        if agent is None:
            raise KeyError(f"Unknown agent: {agent_name}")

        if isinstance(context, VORISContext):
            aura_context = context
        else:
            aura_context = VORISContext(**dict(context or {}))

        aura_context.activate(str(agent_name or ""))
        if hasattr(agent, "handle"):
            result = agent.handle(task, aura_context)
        elif callable(agent):
            result = agent(task, aura_context)
        else:
            raise TypeError(f"Agent {agent_name} is not callable.")

        agent_bus.publish(
            "agent.completed",
            {
                "agent": str(agent_name or "").strip().lower(),
                "task": task,
                "session_id": aura_context.session_id,
            },
        )
        return result

    def _ensure_bootstrap(self) -> None:
        if self._bootstrapped:
            return
        self._bootstrapped = True
        self._bootstrap_from_descriptors()

    def _bootstrap_from_descriptors(self) -> None:
        for descriptor in list_agents():
            agent_name = str(descriptor.get("id") or "").strip().lower()
            if not agent_name or agent_name in self._agents:
                continue
            self.register(
                agent_name,
                RegisteredAgent(
                    name=agent_name,
                    metadata=dict(descriptor),
                    handler=_build_agent_handler(agent_name),
                ),
            )


def _call_runtime_agent(agent_name: str, task: str) -> Any:
    from brain.runtime_core import AGENT_ROUTER

    handler = AGENT_ROUTER.get(agent_name)
    if handler is None:
        raise KeyError(f"Runtime agent {agent_name} is not connected.")
    return handler(task)


def _call_generated_agent(agent_name: str, task: str, context: VORISContext) -> Any:
    from agents.agent_fabric import run_generated_agent

    result = run_generated_agent(
        agent_name,
        task,
        username=context.metadata.get("username", context.user_id or "guest"),
        session_id=context.session_id,
        confirmed=bool(context.metadata.get("confirmed", False)),
        pin=context.metadata.get("pin"),
        save_artifact=bool(context.metadata.get("save_artifact", False)),
    )
    if isinstance(result, dict):
        return result.get("message") or result.get("result") or result
    return result


def _dynamic_module_callable(agent_name: str) -> Optional[Callable[[str, VORISContext], Any]]:
    project_root = Path(__file__).resolve().parent
    for path in project_root.rglob(f"{agent_name}.py"):
        if path.name == "agent_registry.py":
            continue
        module_name = ".".join(path.relative_to(project_root.parent).with_suffix("").parts)
        try:
            module = importlib.import_module(module_name)
        except Exception:
            continue

        for attr_name in ("handle", "run", "execute", "process"):
            attr = getattr(module, attr_name, None)
            if callable(attr):
                return lambda task, context, fn=attr: fn(task)

        stem_name = path.stem.replace("-", "_")
        attr = getattr(module, stem_name, None)
        if callable(attr):
            return lambda task, context, fn=attr: fn(task)
    return None


def _build_agent_handler(agent_name: str) -> AgentHandler:
    dynamic_handler = _dynamic_module_callable(agent_name)
    if dynamic_handler is not None:
        return dynamic_handler

    descriptor = get_agent_descriptor(agent_name)
    if descriptor and descriptor.category in {
        "advanced",
        "aura_core",
        "business",
        "creative",
        "data",
        "design",
        "documents",
        "elite",
        "experimental",
        "integration",
        "intelligence",
        "media",
        "memory",
        "productivity",
        "security",
        "system",
        "web",
    }:
        return lambda task, context: _call_generated_agent(agent_name, task, context)

    return lambda task, context: _call_runtime_agent(agent_name, task)


agent_registry = AgentRegistry()
