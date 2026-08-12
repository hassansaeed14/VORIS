from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from brain.provider_hub import (
    STATUS_DEGRADED,
    STATUS_HEALTHY,
    STATUS_NOT_CONFIGURED,
    get_runtime_provider_summary,
    summarize_provider_statuses,
)
from brain.telemetry_engine import get_last_telemetry
from memory import vector_memory
from memory.memory_stats import get_memory_stats
from voice.voice_controller import get_voice_status


PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = PROJECT_ROOT / "memory" / "aura_forge_reports.json"


class AuditEngine:
    """Collect real backend evidence about AURA's current health."""

    def __init__(self, report_path: Path | None = None) -> None:
        self.report_path = report_path or REPORT_PATH
        self.report_path.parent.mkdir(parents=True, exist_ok=True)

    def _read_reports(self) -> List[dict[str, Any]]:
        if not self.report_path.exists():
            return []
        try:
            payload = json.loads(self.report_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return payload if isinstance(payload, list) else []

    def _write_reports(self, items: List[dict[str, Any]]) -> None:
        self.report_path.write_text(json.dumps(items, indent=2), encoding="utf-8")

    def _vector_memory_summary(self) -> dict[str, Any]:
        try:
            status = vector_memory.get_status()
        except Exception as error:
            return {"status": "down", "reason": str(error)}

        if status.get("vector_store_ready"):
            return {"status": "working", "reason": "Vector store is available.", "details": status}
        if str(status.get("backend") or "").strip().lower() == "fallback":
            return {"status": "fallback", "reason": "Vector memory is running on its fallback backend.", "details": status}
        return {"status": "down", "reason": status.get("last_error") or "Vector memory is unavailable.", "details": status}

    def _memory_summary(self) -> dict[str, Any]:
        try:
            stats = get_memory_stats()
            return {"status": "working", "details": stats}
        except Exception as error:
            return {"status": "down", "reason": str(error)}

    def _build_findings(
        self,
        provider_summary: dict[str, Any],
        runtime_summary: dict[str, Any],
        memory_summary: dict[str, Any],
        vector_summary: dict[str, Any],
        voice_summary: dict[str, Any],
        telemetry: dict[str, Any],
    ) -> List[dict[str, Any]]:
        findings: List[dict[str, Any]] = []

        preferred_provider = runtime_summary.get("preferred_provider")
        preferred_status = runtime_summary.get("preferred_status")
        active_provider = runtime_summary.get("active_provider")

        if runtime_summary.get("status") != STATUS_HEALTHY:
            severity = "critical" if not active_provider else "high"
            findings.append(
                {
                    "id": "provider-routing",
                    "severity": severity,
                    "title": "Preferred reasoning path is not fully healthy",
                    "details": runtime_summary.get("message") or "AURA is not serving from its preferred provider path.",
                }
            )

        if not provider_summary.get("healthy"):
            findings.append(
                {
                    "id": "providers-down",
                    "severity": "critical",
                    "title": "No healthy live providers",
                    "details": "AURA cannot provide dependable live answers until at least one provider passes runtime health.",
                }
            )

        if preferred_provider and preferred_status == STATUS_NOT_CONFIGURED:
            findings.append(
                {
                    "id": "primary-not-configured",
                    "severity": "high",
                    "title": f"{str(preferred_provider).upper()} is not configured",
                    "details": "The preferred provider cannot serve until its credentials and SDK path are in place.",
                }
            )

        if vector_summary.get("status") != "working":
            findings.append(
                {
                    "id": "vector-memory",
                    "severity": "high" if vector_summary.get("status") == "down" else "medium",
                    "title": "Vector memory is not fully healthy",
                    "details": vector_summary.get("reason") or "Semantic search is not on the primary backend.",
                }
            )

        if memory_summary.get("status") != "working":
            findings.append(
                {
                    "id": "memory-system",
                    "severity": "high",
                    "title": "Memory stats are unavailable",
                    "details": memory_summary.get("reason") or "AURA could not read memory diagnostics.",
                }
            )

        if not voice_summary.get("stt", {}).get("available"):
            findings.append(
                {
                    "id": "voice-stt",
                    "severity": "medium",
                    "title": "Voice input is not fully available",
                    "details": "Speech-to-text is currently unavailable or missing backend support.",
                }
            )

        provider_stage = ((telemetry.get("stages") or {}).get("provider") or {})
        if provider_stage.get("status") == "failed":
            findings.append(
                {
                    "id": "last-provider-failure",
                    "severity": "medium",
                    "title": "The last provider stage failed",
                    "details": provider_stage.get("error") or "The latest response required a provider recovery path.",
                }
            )

        return findings

    def run_audit(self, *, fresh: bool = False) -> dict[str, Any]:
        provider_summary = summarize_provider_statuses(fresh=fresh)
        runtime_summary = get_runtime_provider_summary(fresh=fresh)
        memory_summary = self._memory_summary()
        vector_summary = self._vector_memory_summary()
        voice_summary = get_voice_status()
        telemetry = get_last_telemetry() or {}
        findings = self._build_findings(
            provider_summary,
            runtime_summary,
            memory_summary,
            vector_summary,
            voice_summary,
            telemetry,
        )

        report = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "providers": provider_summary,
            "assistant_runtime": runtime_summary,
            "memory": memory_summary,
            "vector_memory": vector_summary,
            "voice": voice_summary,
            "telemetry": telemetry,
            "findings": findings,
            "status": "ok",
        }

        reports = self._read_reports()
        reports.append(report)
        self._write_reports(reports[-25:])
        return report
