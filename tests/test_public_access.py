import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import api.api_server as api_server
from _support import bypass_first_run_setup


class PublicAccessTests(unittest.TestCase):
    def setUp(self):
        bypass_first_run_setup(self)
        self.client = TestClient(api_server.app)

    def test_home_page_is_public_after_setup(self):
        with patch.object(api_server, "requires_first_run_setup", return_value=False), patch.object(
            api_server,
            "_current_user",
            return_value=None,
        ), patch.object(
            api_server,
            "_read_html",
            return_value="<html><body>AURA</body></html>",
        ):
            response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("AURA", response.text)

    def test_api_chat_returns_consistent_payload_without_login(self):
        context = {
            "raw_message": "hello",
            "requested_mode": "hybrid",
            "session_id": "public-session",
            "cleaned_message": "hello",
            "detected_intent": "general",
            "confidence": 0.91,
            "decision": {"agent": "general"},
            "permission": {"success": True, "status": "approved", "permission": {"trust_level": "safe"}},
            "user": None,
            "user_profile": {},
            "confirmation_required": False,
            "confirmation_ok": False,
        }
        with patch.object(api_server, "requires_first_run_setup", return_value=False), patch.object(
            api_server,
            "_current_user",
            return_value=None,
        ), patch.object(
            api_server,
            "_prepare_chat_context",
            return_value=context,
        ), patch.object(
            api_server,
            "_attempt_persist_chat_turn",
            return_value={"saved": True},
        ):
            response = self.client.post("/api/chat", json={"message": "hello", "mode": "hybrid"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["content"], "Hey. What can I help you with?")
        self.assertEqual(body["provider"], "local")
        self.assertIsNone(body["error"])
        self.assertIn("request_id", body)
        self.assertEqual(body["action_trace"]["response_mode"], "conversation")
        self.assertEqual(body["action_trace"]["final_status"], "ok")
        self.assertEqual(body["runtime_state"]["task_scope"], "internal")

    def test_api_chat_blank_message_returns_meaningful_error_payload(self):
        with patch.object(api_server, "requires_first_run_setup", return_value=False), patch.object(
            api_server,
            "_current_user",
            return_value=None,
        ):
            response = self.client.post("/api/chat", json={"message": "", "mode": "hybrid"})

        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertEqual(body["reply"], "Please send a message so I can help.")
        self.assertEqual(body["content"], "Please send a message so I can help.")
        self.assertEqual(body["intent"], "validation")
        self.assertEqual(body["agent_used"], "api_chat")
        self.assertEqual(body["action_trace"]["final_status"], "error")
        self.assertEqual(body["action_trace"]["response_mode"], "error")
        self.assertEqual(body["runtime_state"]["assistant_state"], "error")

    def test_public_essay_request_is_not_blocked_by_auth_precheck(self):
        context = api_server._prepare_chat_context(
            "write me an essay of 1000 words about VORIS",
            "hybrid",
            "public-session",
            user=None,
        )

        self.assertEqual(context["detected_intent"], "write")
        self.assertEqual(context["permission_action"], "write")
        self.assertTrue(context["permission"]["success"])
        self.assertEqual(context["permission"]["permission"]["trust_level"], "safe")

    def test_api_chat_replaces_failed_agent_reply_with_structured_degraded_response(self):
        context = {
            "raw_message": "write something helpful",
            "requested_mode": "hybrid",
            "session_id": "public-session",
            "cleaned_message": "write something helpful",
            "detected_intent": "write",
            "confidence": 0.91,
            "decision": {"agent": "write"},
            "permission": {"success": True, "status": "approved", "permission": {"trust_level": "safe"}},
            "user": None,
            "user_profile": {},
            "confirmation_required": False,
            "confirmation_ok": False,
        }
        runtime_result = {
            "intent": "write",
            "detected_intent": "write",
            "confidence": 0.91,
            "response": "writing_runtime agent failed: provider offline",
            "used_agents": ["writing_runtime"],
            "agent_capabilities": [],
            "execution_mode": "single_agent",
            "decision": {"intent": "write"},
            "orchestration": {"primary_agent": "writing_runtime"},
            "permission": {"success": True, "status": "approved", "permission": {"trust_level": "safe"}},
            "provider": None,
            "model": None,
            "providers_tried": [{"provider": "groq", "status": "rate_limited"}],
            "degraded": False,
        }
        with patch.object(api_server, "requires_first_run_setup", return_value=False), patch.object(
            api_server,
            "_current_user",
            return_value=None,
        ), patch.object(
            api_server,
            "_prepare_chat_context",
            return_value=context,
        ), patch.object(
            api_server,
            "process_command_detailed",
            return_value=runtime_result,
        ), patch.object(
            api_server,
            "generate_response_payload",
            return_value={
                "success": False,
                "error": "No healthy AI provider completed the request.",
                "providers_tried": [{"provider": "groq", "status": "rate_limited"}],
                "degraded_reply": "",
            },
        ), patch.object(
            api_server,
            "_attempt_persist_chat_turn",
            return_value={"saved": True},
        ), patch("builtins.print") as print_mock:
            response = self.client.post("/api/chat", json={"message": "write something helpful", "mode": "hybrid"})

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["execution_mode"], "degraded_assistant")
        self.assertTrue(body["degraded"])
        self.assertNotEqual(body["reply"].strip(), "")
        self.assertNotIn("agent failed:", body["reply"].lower())
        self.assertIn("provider", body["routing_trace"])
        self.assertEqual(body["action_trace"]["response_mode"], "limited_response")
        self.assertEqual(body["action_trace"]["final_status"], "degraded")
        self.assertTrue(
            any("[CHAT TRACE]" in str(call.args[0]) for call in print_mock.call_args_list if call.args)
        )

    def test_admin_api_remains_protected_for_public_user(self):
        with patch.object(api_server, "requires_first_run_setup", return_value=False), patch.object(
            api_server,
            "_current_user",
            return_value=None,
        ):
            response = self.client.get("/api/admin/system-status")

        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["status"], "error")

    def test_desktop_apps_endpoint_is_public_and_returns_truthful_app_list(self):
        with patch.object(
            api_server,
            "get_supported_desktop_apps",
            return_value=[
                {
                    "app_id": "chrome",
                    "display_name": "Chrome",
                    "aliases": ["chrome", "google chrome"],
                    "available": True,
                    "status": "available",
                },
                {
                    "app_id": "vs code",
                    "display_name": "VS Code",
                    "aliases": ["vs code", "vscode", "visual studio code"],
                    "available": False,
                    "status": "unavailable",
                },
            ],
        ):
            response = self.client.get("/api/desktop/apps")

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["success"])
        self.assertEqual(body["status"], "ok")
        self.assertEqual(len(body["apps"]), 2)
        self.assertEqual(body["apps"][0]["app_id"], "chrome")
        self.assertFalse(body["apps"][1]["available"])


if __name__ == "__main__":
    unittest.main()
