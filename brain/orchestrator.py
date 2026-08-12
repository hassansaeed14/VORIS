from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional

from groq import Groq

from config.settings import GROQ_API_KEY, MODEL_NAME


client = Groq(api_key=GROQ_API_KEY)


SUPPORTED_ORCHESTRATION_AGENTS = {
    "general",
    "write",
    "weather",
    "news",
    "math",
    "translation",
    "research",
    "study",
    "code",
    "email",
    "summarize",
    "grammar",
    "quiz",
    "dictionary",
    "synonyms",
    "web_search",
    "youtube",
    "currency",
    "crypto",
    "joke",
    "quote",
    "file",
    "list_files",
    "screenshot",
    "task",
    "reminder",
    "compare",
    "time",
    "date",
    "identity",
    "insights",
    "memory",
    "fitness",
    "purchase",
    "permission",
    "reasoning",
}


AGENT_HINTS = {
    "write": ["write", "draft", "compose", "article", "blog post", "caption"],
    "compare": ["compare", "difference", "better", " vs ", "versus"],
    "research": ["research", "investigate", "find information"],
    "summarize": ["summarize", "summary", "short version"],
    "study": ["study", "learn", "revise", "teach me", "explain"],
    "quiz": ["quiz", "test me", "ask questions", "flashcard"],
    "email": ["email", "mail", "write email", "compose email"],
    "grammar": ["grammar", "fix grammar", "correct grammar", "proofread"],
    "code": ["code", "debug", "python", "program", "script", "bug"],
    "weather": ["weather", "temperature", "forecast"],
    "news": ["news", "headline", "current events"],
    "reasoning": ["why", "logic", "reason"],
    "translation": ["translate", "translation"],
    "web_search": ["search", "look up", "google"],
    "task": ["task", "todo", "to do"],
    "reminder": ["remind", "reminder"],
    "file": ["file", "document", "pdf"],
    "screenshot": ["screenshot", "capture screen"],
}


SECONDARY_SCORE_THRESHOLD = 2
MAX_SECONDARY_AGENTS = 2


@dataclass
class OrchestrationPlan:
    primary_agent: str
    secondary_agents: List[str] = field(default_factory=list)
    execution_order: List[str] = field(default_factory=list)
    requires_multiple: bool = False
    task_description: str = ""
    source: str = "rule_based"
    decision_reason: str = ""
    mode: str = "real"
    primary_selection_source: str = "intent"
    top_score: int = 0
    candidate_agents: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class AgentResult:
    agent: str
    success: bool
    content: str
    confidence: Optional[float] = None
    error: Optional[str] = None


@dataclass
class SynthesisResult:
    success: bool
    response: str
    mode: str
    source: str
    used_ai: bool
    agent_count: int
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MasterOrchestrator:
    def normalize_primary_agent(self, intent: Optional[str]) -> str:
        safe_intent = str(intent or "").strip().lower()
        if safe_intent == "content":
            safe_intent = "write"
        if safe_intent == "document":
            return "write"
        if safe_intent in SUPPORTED_ORCHESTRATION_AGENTS:
            return safe_intent
        return "general"

    def get_context(self) -> Dict[str, Optional[str]]:
        # Legacy knowledge_base values are global and not owner-scoped. Do not
        # inject them into synthesis until scoped context is explicitly passed.
        return {}

    def _is_meaningful_text(self, value: Any) -> bool:
        if value is None:
            return False
        text = str(value).strip()
        if not text:
            return False
        return bool(text.strip(" \n\t.,!?;:-_"))

    def _clean_synthesized_response(self, text: Any) -> str:
        if not self._is_meaningful_text(text):
            return ""

        cleaned = str(text).strip()
        cleaned = cleaned.replace("```", "")
        cleaned = re.sub(r"\*{1,3}(.*?)\*{1,3}", r"\1", cleaned)
        cleaned = re.sub(r"#{1,6}\s*", "", cleaned)
        cleaned = re.sub(r"`(.+?)`", r"\1", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
        return cleaned.strip()

    def _phrase_in_text(self, text: str, phrase: str) -> bool:
        phrase = phrase.lower()
        if phrase.strip() != phrase:
            return phrase in text
        return bool(re.search(rf"\b{re.escape(phrase)}\b", text))

    def _score_agents(self, command: str) -> Dict[str, int]:
        command_lower = command.lower()
        scores = {
            agent: 0
            for agent in SUPPORTED_ORCHESTRATION_AGENTS
            if agent != "general"
        }

        for agent, hints in AGENT_HINTS.items():
            for hint in hints:
                if self._phrase_in_text(command_lower, hint):
                    scores[agent] += 1

        if scores.get("compare", 0) > 0:
            scores["reasoning"] = scores.get("reasoning", 0) + 1

        if scores.get("research", 0) > 0 and scores.get("summarize", 0) > 0:
            scores["summarize"] = scores.get("summarize", 0) + 1

        if scores.get("study", 0) > 0 and scores.get("quiz", 0) > 0:
            scores["quiz"] = scores.get("quiz", 0) + 1

        if scores.get("email", 0) > 0 and scores.get("grammar", 0) > 0:
            scores["grammar"] = scores.get("grammar", 0) + 1

        return scores

    def _pick_primary_agent(
        self,
        intent_agent: str,
        scored_agents: List[tuple[str, int]],
    ) -> tuple[str, str, int]:
        if intent_agent != "general":
            top_score = scored_agents[0][1] if scored_agents else 0
            return intent_agent, "intent", top_score

        if scored_agents:
            return scored_agents[0][0], "keyword_scoring", scored_agents[0][1]

        return "general", "general_fallback", 0

    def _build_secondary_agents(
        self,
        command_lower: str,
        primary_agent: str,
        scored_agents: List[tuple[str, int]],
    ) -> tuple[List[str], str]:
        secondary: List[str] = []
        decision_reason = "direct_primary_routing"

        if primary_agent == "compare" and ("compare" in command_lower or "difference between" in command_lower):
            secondary.append("reasoning")
            decision_reason = "compare_with_reasoning_support"

        if primary_agent == "research" and "summarize" in command_lower:
            secondary.append("summarize")
            decision_reason = "research_with_summary_support"

        if primary_agent == "study" and ("quiz" in command_lower or "flashcard" in command_lower):
            secondary.append("quiz")
            decision_reason = "study_with_quiz_support"

        if primary_agent == "email" and ("grammar" in command_lower or "proofread" in command_lower):
            secondary.append("grammar")
            decision_reason = "email_with_grammar_support"

        for agent, score in scored_agents:
            if agent == primary_agent:
                continue
            if score < SECONDARY_SCORE_THRESHOLD:
                continue
            if agent not in SUPPORTED_ORCHESTRATION_AGENTS:
                continue
            if agent not in secondary:
                secondary.append(agent)

        secondary = secondary[:MAX_SECONDARY_AGENTS]
        return secondary, decision_reason

    def analyze_task(self, command: str, intent: Optional[str] = None) -> Dict[str, Any]:
        safe_command = str(command or "").strip()

        if not self._is_meaningful_text(safe_command):
            return OrchestrationPlan(
                primary_agent="general",
                secondary_agents=[],
                execution_order=["general"],
                requires_multiple=False,
                task_description="",
                source="rule_based",
                decision_reason="empty_command",
                mode="real",
                primary_selection_source="general_fallback",
                top_score=0,
                candidate_agents=[],
            ).to_dict()

        intent_agent = self.normalize_primary_agent(intent)
        scores = self._score_agents(safe_command)

        scored_agents = sorted(
            [(agent, score) for agent, score in scores.items() if score > 0],
            key=lambda x: x[1],
            reverse=True,
        )

        primary_agent, primary_selection_source, top_score = self._pick_primary_agent(
            intent_agent,
            scored_agents,
        )

        secondary_agents, decision_reason = self._build_secondary_agents(
            safe_command.lower(),
            primary_agent,
            scored_agents,
        )

        if primary_selection_source == "keyword_scoring":
            if len(scored_agents) > 1 and scored_agents[0][1] == scored_agents[1][1]:
                decision_reason = "keyword_scoring_ambiguous_primary_selection"
            else:
                decision_reason = "keyword_scoring_primary_selection"
        elif primary_selection_source == "intent" and secondary_agents:
            decision_reason = f"{primary_agent}_with_support_agents"
        elif primary_selection_source == "intent":
            decision_reason = "intent_primary_selection"
        elif primary_selection_source == "general_fallback":
            decision_reason = "general_fallback"

        execution_order = [primary_agent] + [
            agent for agent in secondary_agents if agent != primary_agent
        ]

        candidate_agents = [agent for agent, _ in scored_agents[:5]]

        return OrchestrationPlan(
            primary_agent=primary_agent,
            secondary_agents=secondary_agents,
            execution_order=execution_order,
            requires_multiple=len(execution_order) > 1,
            task_description=safe_command,
            source="rule_based",
            decision_reason=decision_reason,
            mode="real",
            primary_selection_source=primary_selection_source,
            top_score=top_score,
            candidate_agents=candidate_agents,
        ).to_dict()

    def _build_deterministic_synthesis(self, items: List[AgentResult]) -> str:
        return "\n\n".join(
            f"{idx}. {item.content}"
            for idx, item in enumerate(items, 1)
        )

    def synthesize_responses(self, command: str, agent_responses: Dict[str, Any]) -> Dict[str, Any]:
        if not agent_responses:
            return SynthesisResult(
                success=False,
                response="I could not generate a useful combined response.",
                mode="real",
                source="empty_input",
                used_ai=False,
                agent_count=0,
            ).to_dict()

        cleaned_items: List[AgentResult] = []
        for agent, response in agent_responses.items():
            if self._is_meaningful_text(response):
                cleaned_items.append(
                    AgentResult(
                        agent=str(agent).strip(),
                        success=True,
                        content=str(response).strip(),
                    )
                )

        if not cleaned_items:
            return SynthesisResult(
                success=False,
                response="I could not generate a useful combined response.",
                mode="real",
                source="empty_cleaned_items",
                used_ai=False,
                agent_count=0,
            ).to_dict()

        if len(cleaned_items) == 1:
            return SynthesisResult(
                success=True,
                response=cleaned_items[0].content,
                mode="real",
                source="single_agent_passthrough",
                used_ai=False,
                agent_count=1,
            ).to_dict()

        combined = "\n\n".join(
            f"{item.agent.upper()} DATA:\n{item.content}"
            for item in cleaned_items
        )

        context = self.get_context()
        context_lines = []
        if context.get("user_name"):
            context_lines.append(f"User name: {context['user_name']}")
        if context.get("user_city"):
            context_lines.append(f"User city: {context['user_city']}")

        context_block = "\n".join(context_lines).strip()
        context_section = ""
        if context_block:
            context_section = f"Context:\n{context_block}\n\n"
        llm_error = None

        try:
            response = client.chat.completions.create(
                model=MODEL_NAME,
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "You are AURA's response synthesizer. "
                            "Merge agent outputs into one coherent, clear, natural response. "
                            "Do not invent facts. "
                            "Do not override the provided agent data. "
                            "Avoid unnecessary markdown in normal replies."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            f"User request: {command}\n\n"
                            f"{context_section}"
                            f"Agent responses:\n{combined}\n\n"
                            "Create one helpful final response."
                        ),
                    },
                ],
                max_tokens=1200,
                temperature=0.3,
            )

            content = ""
            if response and getattr(response, "choices", None):
                choice = response.choices[0]
                if choice and getattr(choice, "message", None):
                    content = choice.message.content or ""

            content = self._clean_synthesized_response(content)

            if self._is_meaningful_text(content):
                return SynthesisResult(
                    success=True,
                    response=content,
                    mode="hybrid",
                    source="llm_synthesis",
                    used_ai=True,
                    agent_count=len(cleaned_items),
                ).to_dict()

        except Exception as e:
            llm_error = str(e)

        return SynthesisResult(
            success=True,
            response=self._build_deterministic_synthesis(cleaned_items),
            mode="real",
            source="deterministic_fallback_synthesis",
            used_ai=False,
            agent_count=len(cleaned_items),
            error=llm_error,
        ).to_dict()


orchestrator = MasterOrchestrator()
