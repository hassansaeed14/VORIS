import unittest
import time
from types import SimpleNamespace
from unittest.mock import patch

import brain.provider_hub as provider_hub


def _fake_completion_result(text: str = "OK"):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=text))],
    )


def _status_or_unconfigured(statuses, provider):
    """Treat providers absent from a test's status map as not configured.

    SUPPORTED_PROVIDERS grows over time -- sambanova, openrouter, claude and
    ollama were all added after these tests were written. Indexing a partial
    dict directly means every such addition breaks unrelated tests with a
    KeyError, which is what happened here.
    """
    return statuses.get(provider) or provider_hub.ProviderStatus(
        provider, "x", "hybrid", False, False, True, "missing",
        status=provider_hub.STATUS_NOT_CONFIGURED,
    )


class ProviderHubTests(unittest.TestCase):
    def setUp(self):
        provider_hub.reset_provider_runtime_state()

    def test_provider_statuses_cover_major_backends(self):
        statuses = provider_hub.list_provider_statuses(fresh=False)
        provider_ids = {item["provider"] for item in statuses}
        self.assertTrue({"sambanova", "openai", "groq", "claude", "gemini", "ollama"}.issubset(provider_ids))

    def test_configured_provider_starts_as_unverified_not_healthy(self):
        with patch.object(provider_hub, "GEMINI_API_KEY", "demo-key"), patch.object(provider_hub, "genai", object()):
            status = provider_hub.get_provider_status("gemini", fresh=False)

        self.assertEqual(status.status, provider_hub.STATUS_CONFIGURED_UNVERIFIED)
        self.assertTrue(status.configured)
        self.assertFalse(status.available)

    def test_get_provider_status_preserves_last_verified_state_without_forcing_probe(self):
        now = time.time()
        cached = provider_hub.ProviderStatus(
            "gemini",
            "gemini-2.5-flash",
            "real",
            True,
            False,
            True,
            "Provider is rate limited.",
            status=provider_hub.STATUS_RATE_LIMITED,
            verified=True,
            last_checked_at=now,
            cooldown_until=now + 120,
            error_type="rate_limit",
        )
        provider_hub.provider_hub._status_cache["gemini"] = cached

        with patch.object(provider_hub, "GEMINI_API_KEY", "demo-key"), patch.object(provider_hub, "genai", object()):
            status = provider_hub.get_provider_status("gemini", fresh=False)

        self.assertEqual(status.status, provider_hub.STATUS_RATE_LIMITED)
        self.assertTrue(status.verified)
        self.assertEqual(status.error_type, "rate_limit")

    def test_stale_healthy_provider_expires_to_configured_unverified(self):
        cached = provider_hub.ProviderStatus(
            "groq",
            "llama-3.3-70b-versatile",
            "real",
            True,
            True,
            True,
            "Recent live inference succeeded.",
            status=provider_hub.STATUS_HEALTHY,
            verified=True,
            last_checked_at=time.time() - provider_hub.HEALTH_TTL_SECONDS - 5,
            last_success_at=time.time() - provider_hub.HEALTH_TTL_SECONDS - 5,
        )
        provider_hub.provider_hub._status_cache["groq"] = cached

        with patch.object(provider_hub, "GROQ_API_KEY", "demo-key"), patch.object(provider_hub, "Groq", object()):
            status = provider_hub.get_provider_status("groq", fresh=False)

        self.assertEqual(status.status, provider_hub.STATUS_CONFIGURED_UNVERIFIED)
        self.assertFalse(status.available)
        self.assertIn("stale", status.reason)

    def test_rate_limit_error_updates_provider_cooldown(self):
        with patch.object(provider_hub, "GROQ_API_KEY", "demo-key"), patch.object(provider_hub, "Groq", object()):
            status = provider_hub.record_provider_failure("groq", "429 rate limit exceeded")
            current = provider_hub.get_provider_status("groq", fresh=False)

        self.assertEqual(status.status, provider_hub.STATUS_RATE_LIMITED)
        self.assertEqual(status.error_type, "rate_limit")
        self.assertIsNotNone(status.cooldown_until)
        self.assertEqual(current.status, provider_hub.STATUS_RATE_LIMITED)
        self.assertTrue(provider_hub.should_skip_provider("groq"))

    def test_fresh_health_check_respects_active_rate_limit_cooldown(self):
        now = time.time()
        provider_hub.provider_hub._status_cache["groq"] = provider_hub.ProviderStatus(
            "groq",
            "llama-3.3-70b-versatile",
            "hybrid",
            True,
            False,
            True,
            "Provider is rate limited.",
            status=provider_hub.STATUS_RATE_LIMITED,
            verified=True,
            last_checked_at=now,
            cooldown_until=now + 120,
            error_type="rate_limit",
        )

        with patch.object(provider_hub, "GROQ_API_KEY", "demo-key"), patch.object(provider_hub, "Groq", object()), patch.object(
            provider_hub.provider_hub,
            "_call_provider",
            side_effect=AssertionError("Cooldown providers should not be probed."),
        ):
            result = provider_hub.provider_hub.check_groq(fresh=True)

        self.assertEqual(result["status"], provider_hub.STATUS_RATE_LIMITED)
        self.assertEqual(result["error_type"], "rate_limit")

    def test_auth_error_is_normalized(self):
        classified = provider_hub.normalize_provider_error("401 invalid api key")

        self.assertEqual(classified["status"], provider_hub.STATUS_AUTH_FAILED)
        self.assertEqual(classified["error_type"], "authentication")

    def test_timeout_error_is_normalized_to_unavailable(self):
        classified = provider_hub.normalize_provider_error(TimeoutError("request timed out"))

        self.assertEqual(classified["status"], provider_hub.STATUS_UNAVAILABLE)
        self.assertEqual(classified["error_type"], "timeout")

    def test_successful_groq_check_marks_provider_healthy(self):
        fake_client = SimpleNamespace(
            chat=SimpleNamespace(
                completions=SimpleNamespace(create=lambda **kwargs: _fake_completion_result())
            )
        )

        with patch.object(provider_hub, "GROQ_API_KEY", "demo-key"), patch.object(provider_hub, "Groq", return_value=fake_client):
            result = provider_hub.provider_hub.check_groq(fresh=True)

        self.assertEqual(result["status"], provider_hub.STATUS_HEALTHY)
        self.assertIsNotNone(result["response_time_ms"])

    def test_sambanova_uses_openai_compatible_client_and_token_budget(self):
        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return _fake_completion_result("SambaNova says hello.")

        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
        )

        with patch.object(provider_hub, "SAMBANOVA_API_KEY", "demo-key"), patch.object(
            provider_hub,
            "SAMBANOVA_BASE_URL",
            "https://api.sambanova.ai/v1",
        ), patch.object(provider_hub, "OpenAI", return_value=fake_client):
            text = provider_hub.provider_hub._call_sambanova(
                [{"role": "user", "content": "ping"}],
                max_tokens=4096,
                temperature=0.2,
            )

        self.assertEqual(text, "SambaNova says hello.")
        self.assertEqual(captured["model"], provider_hub._provider_model("sambanova"))
        self.assertEqual(captured["max_tokens"], 4096)

    def test_extract_vision_payload_strips_frontend_tags(self):
        payload = (
            "[VISION_PROMPT]What is in this image?[/VISION_PROMPT]"
            "[VISION_URL]data:image/png;base64,abc123==[/VISION_URL]"
        )

        result = provider_hub.extract_vision_payload(payload)

        self.assertEqual(result, ("What is in this image?", "data:image/png;base64,abc123=="))

    def test_groq_vision_payload_uses_clean_image_url_and_vision_model(self):
        captured = {}

        def fake_create(**kwargs):
            captured.update(kwargs)
            return _fake_completion_result("A small test image.")

        fake_client = SimpleNamespace(
            chat=SimpleNamespace(completions=SimpleNamespace(create=fake_create))
        )
        payload = (
            "[VISION_PROMPT]Describe this image.[/VISION_PROMPT]"
            "[VISION_URL]data:image/png;base64,abc123==[/VISION_URL]"
        )

        with patch.object(provider_hub, "GROQ_API_KEY", "demo-key"), patch.object(
            provider_hub,
            "Groq",
            return_value=fake_client,
        ), patch.object(provider_hub, "GROQ_VISION_MODEL", "vision-test-model"):
            text = provider_hub.provider_hub._call_groq(
                [{"role": "user", "content": payload}],
                max_tokens=100,
                temperature=0.0,
            )

        self.assertEqual(text, "A small test image.")
        self.assertEqual(captured["model"], "vision-test-model")
        message = captured["messages"][0]
        self.assertEqual(message["content"][0]["text"], "Describe this image.")
        self.assertEqual(
            message["content"][1]["image_url"]["url"],
            "data:image/png;base64,abc123==",
        )

    def test_extract_gemini_text_uses_candidate_parts_when_text_accessor_fails(self):
        class BrokenTextResponse:
            @property
            def text(self):
                raise ValueError("quick accessor failed")

        response = BrokenTextResponse()
        response.candidates = [
            SimpleNamespace(
                finish_reason=1,
                content=SimpleNamespace(parts=[SimpleNamespace(text="Gemini says hello")]),
            )
        ]

        text = provider_hub._extract_gemini_text(response)

        self.assertEqual(text, "Gemini says hello")

    def test_pick_provider_prefers_healthy_provider(self):
        fake_statuses = {
            "gemini": provider_hub.ProviderStatus("gemini", "gemini", "real", True, False, True, "not ready", status=provider_hub.STATUS_CONFIGURED_UNVERIFIED),
            "openai": provider_hub.ProviderStatus("openai", "gpt", "hybrid", False, False, True, "missing", status=provider_hub.STATUS_NOT_CONFIGURED),
            "groq": provider_hub.ProviderStatus("groq", "llama", "real", True, True, True, "healthy", status=provider_hub.STATUS_HEALTHY),
        }

        with patch.object(provider_hub, "get_provider_status", side_effect=lambda provider, fresh=False: fake_statuses.get(provider) or provider_hub.ProviderStatus(provider, "x", "hybrid", False, False, True, "missing", status=provider_hub.STATUS_NOT_CONFIGURED)):
            chosen = provider_hub.pick_provider(preferred="router")

        self.assertEqual(chosen, "groq")

    def test_generate_with_best_provider_uses_groq_primary(self):
        statuses = {
            "groq": provider_hub.ProviderStatus("groq", "llama-3.3-70b-versatile", "real", True, True, True, "healthy", status=provider_hub.STATUS_HEALTHY),
            "gemini": provider_hub.ProviderStatus("gemini", "gemini-2.5-flash", "real", True, True, True, "healthy", status=provider_hub.STATUS_HEALTHY),
            "openai": provider_hub.ProviderStatus("openai", "gpt-4o-mini", "real", True, True, True, "healthy", status=provider_hub.STATUS_HEALTHY),
        }

        with patch.object(provider_hub, "get_provider_status", side_effect=lambda provider, fresh=False: _status_or_unconfigured(statuses, provider)), patch.object(
            provider_hub.provider_hub,
            "generate_with_provider",
            side_effect=lambda provider, messages, max_tokens, temperature: {
                "success": True,
                "provider": provider,
                "model": statuses[provider].model,
                "text": f"{provider} says hello",
                "latency_ms": 12.0,
                "status": provider_hub.STATUS_HEALTHY,
            },
        ) as generate_mock:
            result = provider_hub.provider_hub.generate_with_best_provider(
                [{"role": "user", "content": "ping"}],
                max_tokens=10,
                temperature=0.0,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["provider"], "groq")
        self.assertEqual(generate_mock.call_args.args[0], "groq")

    def test_generate_with_best_provider_falls_back_to_gemini_when_groq_is_unavailable(self):
        statuses = {
            "sambanova": provider_hub.ProviderStatus("sambanova", "Meta-Llama-3.3-70B-Instruct", "real", False, False, True, "not configured", status=provider_hub.STATUS_NOT_CONFIGURED),
            "groq": provider_hub.ProviderStatus("groq", "llama-3.3-70b-versatile", "real", True, False, True, "degraded", status=provider_hub.STATUS_DEGRADED),
            "gemini": provider_hub.ProviderStatus("gemini", "gemini-2.5-flash", "real", True, True, True, "healthy", status=provider_hub.STATUS_HEALTHY),
            "openai": provider_hub.ProviderStatus("openai", "gpt-4o-mini", "real", True, True, True, "healthy", status=provider_hub.STATUS_HEALTHY),
        }

        def fake_generate(provider, messages, max_tokens, temperature):
            if provider == "groq":
                raise provider_hub.ProviderExecutionError("groq", status=provider_hub.STATUS_UNAVAILABLE, error="Groq unavailable")
            return {
                "success": True,
                "provider": provider,
                "model": statuses[provider].model,
                "text": f"{provider} says hello",
                "latency_ms": 12.0,
                "status": provider_hub.STATUS_HEALTHY,
            }

        with patch.object(provider_hub, "get_provider_status", side_effect=lambda provider, fresh=False: _status_or_unconfigured(statuses, provider)), patch.object(
            provider_hub.provider_hub,
            "generate_with_provider",
            side_effect=fake_generate,
        ):
            result = provider_hub.provider_hub.generate_with_best_provider(
                [{"role": "user", "content": "ping"}],
                max_tokens=10,
                temperature=0.0,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["provider"], "gemini")
        # PROVIDER_PRIORITY leads with sambanova, so groq is no longer the
        # first attempt. What this test is actually about is that groq was
        # tried and reported unavailable before gemini answered.
        groq_attempt = next(a for a in result["attempts"] if a["provider"] == "groq")
        self.assertEqual(groq_attempt["status"], provider_hub.STATUS_UNAVAILABLE)

    def test_generate_with_best_provider_skips_rate_limited_primary_and_uses_groq(self):
        statuses = {
            "sambanova": provider_hub.ProviderStatus("sambanova", "Meta-Llama-3.3-70B-Instruct", "real", False, False, True, "not configured", status=provider_hub.STATUS_NOT_CONFIGURED),
            "gemini": provider_hub.ProviderStatus("gemini", "gemini-2.5-flash", "real", True, False, True, "degraded", status=provider_hub.STATUS_DEGRADED),
            "openai": provider_hub.ProviderStatus("openai", "gpt-4o-mini", "real", True, False, True, "rate limited", status=provider_hub.STATUS_RATE_LIMITED),
            "groq": provider_hub.ProviderStatus("groq", "llama-3.3-70b-versatile", "real", True, True, True, "healthy", status=provider_hub.STATUS_HEALTHY),
        }

        def fake_generate(provider, messages, max_tokens, temperature):
            if provider == "gemini":
                raise provider_hub.ProviderExecutionError("gemini", status=provider_hub.STATUS_UNAVAILABLE, error="Gemini unavailable")
            if provider == "groq":
                return {
                    "success": True,
                    "provider": "groq",
                    "model": statuses["groq"].model,
                    "text": "groq says hello",
                    "latency_ms": 12.0,
                    "status": provider_hub.STATUS_HEALTHY,
                }
            raise AssertionError("OpenAI should be skipped while rate limited")

        with patch.object(provider_hub, "get_provider_status", side_effect=lambda provider, fresh=False: _status_or_unconfigured(statuses, provider)), patch.object(
            provider_hub.provider_hub,
            "generate_with_provider",
            side_effect=fake_generate,
        ):
            result = provider_hub.provider_hub.generate_with_best_provider(
                [{"role": "user", "content": "ping"}],
                preferred="gemini",
                max_tokens=10,
                temperature=0.0,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["provider"], "groq")
        self.assertEqual(result["attempts"][0]["provider"], "gemini")
        self.assertEqual(result["attempts"][0]["status"], provider_hub.STATUS_UNAVAILABLE)

    def test_generate_with_best_provider_skips_unavailable_provider_in_cooldown(self):
        statuses = {
            "groq": provider_hub.ProviderStatus(
                "groq",
                "llama-3.3-70b-versatile",
                "real",
                True,
                False,
                True,
                "Provider request timed out.",
                status=provider_hub.STATUS_UNAVAILABLE,
                cooldown_until=time.time() + 30,
                error_type="timeout",
            ),
            "gemini": provider_hub.ProviderStatus("gemini", "gemini-2.5-flash", "real", True, True, True, "healthy", status=provider_hub.STATUS_HEALTHY),
            "openai": provider_hub.ProviderStatus("openai", "gpt-4o-mini", "real", True, True, True, "healthy", status=provider_hub.STATUS_HEALTHY),
        }

        with patch.object(provider_hub, "get_provider_status", side_effect=lambda provider, fresh=False: statuses.get(provider) or provider_hub.ProviderStatus(provider, "x", "hybrid", False, False, True, "missing", status=provider_hub.STATUS_NOT_CONFIGURED)), patch.object(
            provider_hub.provider_hub,
            "generate_with_provider",
            side_effect=lambda provider, messages, max_tokens, temperature: {
                "success": True,
                "provider": provider,
                "model": statuses[provider].model,
                "text": f"{provider} says hello",
                "latency_ms": 12.0,
                "status": provider_hub.STATUS_HEALTHY,
            },
        ) as generate_mock:
            result = provider_hub.provider_hub.generate_with_best_provider(
                [{"role": "user", "content": "ping"}],
                preferred="groq",
                max_tokens=10,
                temperature=0.0,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["provider"], "gemini")
        self.assertEqual(generate_mock.call_args.args[0], "gemini")
        self.assertEqual(result["attempts"][0]["provider"], "groq")
        self.assertTrue(result["attempts"][0]["skipped"])

    def test_generate_with_best_provider_can_lock_to_preferred_provider_only(self):
        statuses = {
            "groq": provider_hub.ProviderStatus("groq", "llama-3.3-70b-versatile", "real", True, False, True, "auth failed", status=provider_hub.STATUS_AUTH_FAILED),
            "gemini": provider_hub.ProviderStatus("gemini", "gemini-2.5-flash", "real", True, True, True, "healthy", status=provider_hub.STATUS_HEALTHY),
            "openai": provider_hub.ProviderStatus("openai", "gpt-4o-mini", "real", True, True, True, "healthy", status=provider_hub.STATUS_HEALTHY),
        }

        with patch.object(provider_hub, "get_provider_status", side_effect=lambda provider, fresh=False: _status_or_unconfigured(statuses, provider)), patch.object(
            provider_hub.provider_hub,
            "generate_with_provider",
        ) as generate_mock:
            result = provider_hub.provider_hub.generate_with_best_provider(
                [{"role": "user", "content": "ping"}],
                preferred="groq",
                preferred_only=True,
                max_tokens=10,
                temperature=0.0,
            )

        self.assertFalse(result["success"])
        self.assertEqual(result["routing_order"], ["groq"])
        self.assertEqual(result["attempts"][0]["provider"], "groq")
        self.assertEqual(result["attempts"][0]["status"], provider_hub.STATUS_AUTH_FAILED)
        generate_mock.assert_not_called()

    def test_runtime_provider_summary_explains_fallback_route(self):
        statuses = {
            "gemini": provider_hub.ProviderStatus("gemini", "gemini-2.5-flash", "real", True, False, True, "rate limited", status=provider_hub.STATUS_RATE_LIMITED),
            "openai": provider_hub.ProviderStatus("openai", "gpt-4o-mini", "real", True, False, True, "rate limited", status=provider_hub.STATUS_RATE_LIMITED),
            "groq": provider_hub.ProviderStatus("groq", "llama-3.3-70b-versatile", "real", True, True, True, "healthy", status=provider_hub.STATUS_HEALTHY, last_used_at=10.0),
        }

        with patch.object(provider_hub, "get_provider_status", side_effect=lambda provider, fresh=False: statuses.get(provider) or provider_hub.ProviderStatus(provider, "x", "hybrid", False, False, True, "missing", status=provider_hub.STATUS_NOT_CONFIGURED)):
            summary = provider_hub.get_runtime_provider_summary(preferred="groq", fresh=False)

        self.assertEqual(summary["status"], provider_hub.STATUS_HEALTHY)
        self.assertEqual(summary["preferred_provider"], "groq")
        self.assertEqual(summary["active_provider"], "groq")
        self.assertIn("serving VORIS's active reasoning path", summary["message"])


if __name__ == "__main__":
    unittest.main()
