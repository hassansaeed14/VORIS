import unittest
from unittest.mock import patch

from forge.audit_engine import AuditEngine
from forge.forge_engine import ForgeEngine
from forge.patch_manager import PatchManager
from forge.repair_engine import RepairEngine
from forge.safety_guard import SafetyGuard


class ForgeEngineTests(unittest.TestCase):
    def test_safety_guard_blocks_self_modification(self):
        decision = SafetyGuard().evaluate("self_modify", targets=["brain/core_ai.py"])
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.risk_level, "high")

    def test_repair_engine_generates_plan_for_provider_failure(self):
        plan = RepairEngine().build_repair_plan(
            {
                "findings": [
                    {
                        "id": "provider-routing",
                        "severity": "high",
                        "title": "Preferred reasoning path is not fully healthy",
                    }
                ]
            }
        )
        self.assertTrue(plan)
        self.assertEqual(plan[0]["id"], "repair-provider-routing")

    def test_forge_engine_runs_safe_audit_cycle(self):
        fake_report = {
            "status": "ok",
            "findings": [{"id": "vector-memory", "severity": "medium"}],
        }
        with patch.object(AuditEngine, "run_audit", return_value=fake_report), patch.object(
            PatchManager,
            "record_patch",
            return_value={"id": "patch-1"},
        ), patch.object(
            PatchManager,
            "list_patches",
            return_value=[{"id": "patch-1"}],
        ):
            result = ForgeEngine().run_audit_cycle()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["audit"], fake_report)
        self.assertTrue(result["repair_plan"])
        self.assertTrue(result["safety"]["allowed"])


if __name__ == "__main__":
    unittest.main()
