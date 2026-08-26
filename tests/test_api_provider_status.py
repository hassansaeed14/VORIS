import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import api.api_server as api_server
from tests.support import SetupGateBypassMixin


class ApiProviderStatusTests(SetupGateBypassMixin, unittest.TestCase):
    def setUp(self):
        super().setUp()
        api_server.PROVIDER_HEALTH_CACHE.update(
            {
                "checked_at_ts": 0.0,
                "checked_at": 0.0,
                "items": [],
                "providers": {},
                "assistant_runtime": {},
                "provider_state_version": -1,
            }
        )
        self.client = TestClient(api_server.app)

    def test_provider_endpoint_returns_truthful_status_payload(self):
        provider_snapshot = {
            "checked_at": "2026-04-11T10:00:00",
            "routing_order": ["gemini", "openai", "groq"],
            "healthy": ["gemini"],
            "configured": ["gemini", "groq"],
            "items": [
                {
                    "provider": "gemini",
                    "model": "gemini-2.5-flash",
                    "status": "healthy",
                    "reason": "Live health check passed.",
                    "configured": True,
                    "installed": True,
                    "response_time_ms": 120.0,
                },
                {
                    "provider": "groq",
                    "model": "llama-3.3-70b-versatile",
                    "status": "configured_unverified",
                    "reason": "Provider is configured but has not passed a live check yet.",
                    "configured": True,
                    "installed": True,
                    "response_time_ms": None,
                },
            ],
            "providers": {"gemini": "healthy", "groq": "configured_unverified"},
            "assistant_runtime": {
                "status": "healthy",
                "preferred_provider": "gemini",
                "active_provider": "gemini",
                "active_model": "gemini-2.5-flash",
                "message": "GEMINI is healthy and serving AURA's active reasoning path.",
            },
        }

        with patch.object(api_server, "_current_user", return_value={"id": "owner", "username": "owner", "admin": True}), patch.object(
            api_server,
            "requires_first_run_setup",
            return_value=False,
        ), patch.object(
            api_server,
            "_provider_health_snapshot",
            return_value=provider_snapshot,
        ):
            response = self.client.get("/api/providers")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["providers"]["gemini"], "healthy")
        self.assertEqual(payload["providers"]["groq"], "configured_unverified")
        self.assertEqual(payload["routing_order"], ["gemini", "openai", "groq"])
        self.assertEqual(payload["assistant_runtime"]["active_provider"], "gemini")

    def test_system_health_uses_provider_truth_model(self):
        provider_snapshot = {
            "items": [
                {"provider": "gemini", "status": "healthy"},
                {"provider": "groq", "status": "configured_unverified"},
            ],
            "providers": {"gemini": "healthy", "groq": "configured_unverified"},
            "routing_order": ["gemini", "openai", "groq"],
            "assistant_runtime": {
                "status": "healthy",
                "preferred_provider": "gemini",
                "active_provider": "gemini",
                "active_model": "gemini-2.5-flash",
                "message": "GEMINI is healthy and serving AURA's active reasoning path.",
            },
        }

        with patch.object(api_server, "_provider_health_snapshot", return_value=provider_snapshot), patch.object(
            api_server,
            "get_voice_status",
            return_value={"stt": {"available": False}, "tts": {"available": True}},
        ), patch.object(
            api_server,
            "_chat_requests_today",
            return_value=3,
        ):
            payload = api_server._system_health_payload()

        self.assertEqual(payload["brain"], "working")
        self.assertEqual(payload["providers"]["gemini"], "healthy")
        self.assertEqual(payload["routing_order"], ["gemini", "openai", "groq"])
        self.assertEqual(payload["assistant_runtime"]["active_provider"], "gemini")

    def test_system_health_reports_browser_only_tts_and_truth_notes(self):
        with patch.object(api_server, "_provider_health_snapshot", return_value={"items": [], "providers": {}, "routing_order": [], "assistant_runtime": {}}), patch.object(
            api_server,
            "get_voice_status",
            return_value={
                "stt": {"available": False},
                "tts": {"available": True, "status": "browser_only"},
            },
        ), patch.object(
            api_server,
            "_chat_requests_today",
            return_value=0,
        ):
            payload = api_server._system_health_payload()

        self.assertEqual(payload["voice_tts"], "browser_only")
        self.assertIn("push-to-talk", payload["truth_notes"]["voice"])
        self.assertIn("rate-limited", payload["truth_notes"]["providers"])

    def test_agents_endpoint_exposes_truth_note(self):
        with patch.object(api_server, "list_agents", return_value=[]), patch.object(
            api_server,
            "list_generated_agent_cards",
            return_value=[],
        ), patch.object(
            api_server,
            "summarize_provider_statuses",
            return_value={},
        ), patch.object(
            api_server,
            "get_agent_summary",
            return_value={"capability_modes": {"real": 1, "hybrid": 2, "placeholder": 3}},
        ), patch.object(
            api_server,
            "requires_first_run_setup",
            return_value=False,
        ), patch.object(
            api_server,
            "_current_user",
            return_value={"id": "owner", "username": "owner", "admin": True},
        ):
            response = self.client.get("/api/agents")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("truth_note", payload)
        self.assertIn("real, hybrid, and placeholder", payload["truth_note"])

    def test_provider_endpoint_exposes_truth_note(self):
        provider_snapshot = {
            "checked_at": "2026-04-22T10:00:00",
            "routing_order": ["groq"],
            "healthy": [],
            "configured": ["groq"],
            "items": [{"provider": "groq", "status": "rate_limited"}],
            "providers": {"groq": "rate_limited"},
            "assistant_runtime": {"status": "rate_limited", "preferred_provider": "groq"},
        }

        with patch.object(api_server, "_provider_health_snapshot", return_value=provider_snapshot):
            response = self.client.get("/api/providers")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("truth_note", payload)
        self.assertIn("rate-limit", payload["truth_note"])

    def test_provider_health_snapshot_refreshes_when_runtime_state_changes(self):
        api_server.PROVIDER_HEALTH_CACHE.update(
            {
                "checked_at_ts": 9999999999.0,
                "checked_at": "old",
                "items": [{"provider": "groq", "status": "healthy"}],
                "providers": {"groq": "healthy"},
                "assistant_runtime": {},
                "provider_state_version": 1,
            }
        )
        summary = {
            "items": [{"provider": "groq", "status": "rate_limited", "configured": True}],
            "providers": {"groq": "rate_limited"},
            "routing_order": ["groq"],
            "healthy": [],
            "configured": ["groq"],
        }

        with patch.object(api_server, "get_provider_state_version", return_value=2), patch.object(
            api_server,
            "summarize_provider_statuses",
            return_value=summary,
        ) as summary_mock, patch.object(
            api_server,
            "get_runtime_provider_summary",
            return_value={"status": "degraded", "preferred_provider": "groq"},
        ):
            snapshot = api_server._provider_health_snapshot(force=False)

        self.assertEqual(snapshot["providers"]["groq"], "rate_limited")
        self.assertEqual(snapshot["provider_state_version"], 2)
        summary_mock.assert_called_once()

    def test_forge_report_endpoint_requires_admin_and_returns_real_report(self):
        forge_report = {"status": "ok", "audit": {"findings": []}, "repair_plan": []}

        with patch.object(api_server, "_current_user", return_value={"id": "owner", "username": "owner", "admin": True}), patch.object(
            api_server,
            "requires_first_run_setup",
            return_value=False,
        ), patch.object(
            api_server.forge_engine,
            "run_audit_cycle",
            return_value=forge_report,
        ):
            response = self.client.get("/api/forge/report")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")


if __name__ == "__main__":
    unittest.main()
