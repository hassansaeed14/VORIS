from __future__ import annotations

from typing import Any, Dict, List


class RepairEngine:
    """Turn Forge audit findings into safe, explicit repair plans."""

    def build_repair_plan(self, audit_report: dict[str, Any]) -> List[dict[str, Any]]:
        findings = list(audit_report.get("findings") or [])
        plans: List[dict[str, Any]] = []

        for finding in findings:
            finding_id = str(finding.get("id") or "").strip().lower()
            severity = str(finding.get("severity") or "medium").strip().lower()

            if finding_id == "provider-routing":
                plans.append(
                    {
                        "id": "repair-provider-routing",
                        "priority": severity,
                        "title": "Re-verify preferred providers and preserve truthful fallback routing",
                        "owner": "AURA Forge",
                        "safe_to_auto_apply": False,
                        "files": ["brain/provider_hub.py", "config/settings.py", "tests/test_provider_hub.py"],
                    }
                )
            elif finding_id in {"providers-down", "primary-not-configured"}:
                plans.append(
                    {
                        "id": "repair-provider-credentials",
                        "priority": severity,
                        "title": "Restore at least one healthy live provider",
                        "owner": "AURA Forge",
                        "safe_to_auto_apply": False,
                        "files": ["config/settings.py", ".env", "brain/provider_hub.py"],
                    }
                )
            elif finding_id == "vector-memory":
                plans.append(
                    {
                        "id": "repair-vector-memory",
                        "priority": severity,
                        "title": "Restore the primary vector memory backend",
                        "owner": "AURA Forge",
                        "safe_to_auto_apply": False,
                        "files": ["memory/vector_memory.py", "memory/memory_controller.py"],
                    }
                )
            elif finding_id == "voice-stt":
                plans.append(
                    {
                        "id": "repair-voice-input",
                        "priority": severity,
                        "title": "Stabilize microphone capture and voice answer flow",
                        "owner": "AURA Forge",
                        "safe_to_auto_apply": False,
                        "files": ["voice/voice_pipeline.py", "interface/web/app.js"],
                    }
                )

        return plans
