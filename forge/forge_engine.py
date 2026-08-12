from __future__ import annotations

from typing import Any, Dict

from .audit_engine import AuditEngine
from .patch_manager import PatchManager
from .repair_engine import RepairEngine
from .safety_guard import SafetyGuard


class ForgeEngine:
    """Internal audit-and-repair planner for AURA upgrades."""

    def __init__(
        self,
        *,
        audit_engine: AuditEngine | None = None,
        repair_engine: RepairEngine | None = None,
        patch_manager: PatchManager | None = None,
        safety_guard: SafetyGuard | None = None,
    ) -> None:
        self.audit_engine = audit_engine or AuditEngine()
        self.repair_engine = repair_engine or RepairEngine()
        self.patch_manager = patch_manager or PatchManager()
        self.safety_guard = safety_guard or SafetyGuard()

    def run_audit_cycle(self, *, fresh: bool = False) -> Dict[str, Any]:
        safety = self.safety_guard.evaluate("audit")
        if not safety.allowed:
            return {
                "status": "blocked",
                "reason": safety.reason,
                "safety": safety.to_dict(),
            }

        audit_report = self.audit_engine.run_audit(fresh=fresh)
        repair_plan = self.repair_engine.build_repair_plan(audit_report)
        if repair_plan:
            self.patch_manager.record_patch(
                summary="AURA Forge generated a repair plan",
                files=[path for item in repair_plan for path in item.get("files", [])],
                status="planned",
                metadata={"plan_count": len(repair_plan)},
            )

        return {
            "status": "ok",
            "audit": audit_report,
            "repair_plan": repair_plan,
            "safety": safety.to_dict(),
            "recent_patch_records": self.patch_manager.list_patches()[-5:],
        }


forge_engine = ForgeEngine()
