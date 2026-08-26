import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fastapi.testclient import TestClient

import api.api_server as api_server
from tests.support import SetupGateBypassMixin
import brain.core_ai as core_ai
import brain.runtime_core as runtime_core
import security.enforcement as enforcement
import security.otp_manager as otp_manager
import security.session_manager as session_manager


class SecuritySystemTests(SetupGateBypassMixin, unittest.TestCase):
    def test_describe_login_session_returns_expiry_details(self):
        with TemporaryDirectory() as temp_dir:
            sessions_path = Path(temp_dir) / "sessions.json"
            with patch.object(session_manager, "SESSIONS_FILE", sessions_path):
                token = session_manager.create_login_session(
                    user_id="user-1",
                    username="tester",
                    ip_address="127.0.0.1",
                    user_agent="pytest",
                )

                snapshot = session_manager.describe_login_session(token)

        self.assertTrue(snapshot["valid"])
        self.assertEqual(snapshot["reason"], "active")
        self.assertIsInstance(snapshot["remaining_seconds"], int)
        self.assertGreater(snapshot["remaining_seconds"], 0)
        self.assertEqual(snapshot["session"]["username"], "tester")

    def test_blocked_response_shape_is_uniform_across_trust_levels(self):
        """Every blocked decision must surface the full contract fields.

        The runtime, agents and UI all rely on this shape — a missing
        ``required_action`` or ``next_step_hint`` silently breaks the
        follow-up prompt flow, so pin it down here.
        """

        required_fields = {
            "allowed",
            "reason",
            "trust_level",
            "required_action",
            "next_step_hint",
            "status",
        }
        for action in ("memory_read", "screenshot", "purchase"):
            with self.subTest(action=action):
                result = enforcement.enforce_action(
                    action,
                    session_id=f"shape-{action}",
                    require_auth=False,
                )
                self.assertFalse(result["allowed"], result)
                missing = required_fields.difference(result.keys())
                self.assertFalse(missing, f"{action} missing {missing}")
                self.assertTrue(result["reason"])
                self.assertTrue(result["required_action"])
                self.assertTrue(result["next_step_hint"])

    def test_enforce_action_allows_critical_action_with_valid_otp(self):
        with TemporaryDirectory() as temp_dir:
            otp_state_path = Path(temp_dir) / "otp_state.json"
            with patch.object(otp_manager, "OTP_STATE_FILE", otp_state_path):
                issued = otp_manager.request_otp("user-1", "purchase")
                result = enforcement.enforce_action(
                    "purchase",
                    username="tester",
                    user_id="user-1",
                    session_id="session-1",
                    otp=issued["code"],
                    otp_token=issued["token"],
                    require_auth=False,
                )

        self.assertTrue(result["allowed"])
        self.assertTrue(result["otp_verified"])
        self.assertEqual(result["status"], "approved")

    def test_runtime_personal_memory_read_is_blocked_when_permission_fails(self):
        def _fake_check_permission(action, session=None, context=None):
            access = {
                "allowed": False,
                "status": "confirm",
                "reason": "Private action requires confirmation.",
                "trust_level": "private",
                "approval_type": "confirm",
                "action_name": action,
                "decision": {
                    "action_name": action,
                    "trust_level": "private",
                    "approval_type": "confirm",
                    "allowed": False,
                    "reason": "Private action requires confirmation.",
                },
            }
            return {
                "allowed": False,
                "reason": access["reason"],
                "required_action": "confirm",
                "trust_level": "private",
                "action": action,
                "status": "confirm",
                "enforcement": access,
            }

        with patch.object(
            runtime_core,
            "check_permission",
            side_effect=_fake_check_permission,
        ), patch.object(
            runtime_core,
            "get_personal_display_name",
            side_effect=AssertionError("Memory read should not execute when permission is denied."),
        ):
            result = runtime_core.process_single_command_detailed("what is my name")

        self.assertEqual(result["execution_mode"], "permission_blocked")
        self.assertEqual(result["permission_action"], "memory_read")
        self.assertIn("requires confirmation", result["response"].lower())

    def test_core_ai_passes_security_context_into_runtime(self):
        captured = {}

        def _fake_runtime(command: str, **kwargs):
            captured.update(kwargs)
            return {
                "intent": "general",
                "detected_intent": "general",
                "confidence": 1.0,
                "response": "Done.",
                "plan": [],
                "used_agents": ["general"],
                "agent_capabilities": [],
                "execution_mode": "assistant_llm",
                "decision": {},
                "orchestration": {},
                "permission_action": "general",
                "permission": {"success": True, "status": "approved", "permission": {"reason": ""}},
                "provider": "groq",
                "model": "test-model",
                "providers_tried": ["groq"],
            }

        with patch.object(core_ai, "_sync_context_into_response_engine"), patch.object(
            core_ai.runtime_core_module,
            "process_command_detailed",
            side_effect=_fake_runtime,
        ):
            core_ai.process_command_detailed(
                "hello",
                session_id="session-42",
                security_context={"username": "tester", "pin": "1234"},
            )

        self.assertEqual(captured["session_id"], "session-42")
        self.assertEqual(captured["security_context"]["username"], "tester")
        self.assertEqual(captured["security_context"]["pin"], "1234")

    def test_auth_session_endpoint_reports_session_state(self):
        client = TestClient(api_server.app)
        with patch.object(api_server, "_current_user", return_value=None), patch.object(
            api_server,
            "describe_login_session",
            return_value={
                "valid": False,
                "reason": "expired_or_missing",
                "session": None,
                "remaining_seconds": 0,
                "expires_at": None,
            },
        ):
            response = client.get("/api/auth/session")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertFalse(body["authenticated"])
        self.assertFalse(body["session_valid"])
        self.assertEqual(body["session_reason"], "expired_or_missing")

    def test_phone_register_endpoint_requires_enforcement(self):
        client = TestClient(api_server.app)
        with patch.object(
            api_server,
            "_current_user",
            return_value={"id": "user-1", "username": "tester"},
        ), patch.object(
            api_server,
            "enforce_action",
            return_value={
                "allowed": False,
                "status": "pin",
                "reason": "Critical action requires PIN.",
                "trust_level": "critical",
                "approval_type": "pin",
                "action_name": "phone_register",
                "decision": {
                    "action_name": "phone_register",
                    "trust_level": "critical",
                    "approval_type": "pin",
                    "allowed": False,
                    "reason": "Critical action requires PIN.",
                },
            },
        ):
            response = client.post("/api/security/phone/register", json={"phone": "+923001234567"})

        self.assertEqual(response.status_code, 403)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertEqual(body["status"], "pin")


if __name__ == "__main__":
    unittest.main()
