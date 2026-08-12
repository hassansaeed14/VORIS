from __future__ import annotations

import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ProductionHardeningTests(unittest.TestCase):
    def test_provider_startup_logs_do_not_echo_api_key_prefixes(self):
        for relative_path in ("brain/core_ai.py", "brain/response_engine.py"):
            source = (ROOT / relative_path).read_text(encoding="utf-8")
            self.assertNotIn("Groq key loaded", source)
            self.assertNotIn("GROQ_API_KEY[:10]", source)
            self.assertNotIn("_groq_key[:10]", source)

    def test_web_v2_has_no_button_clicked_console_spam(self):
        for relative_path in ("interface/web_v2/app.js", "interface/web_v2/auth.js"):
            source = (ROOT / relative_path).read_text(encoding="utf-8")
            self.assertNotIn("BUTTON CLICKED", source)

    def test_health_check_covers_core_demo_readiness_endpoints(self):
        from tools.health_check import ENDPOINTS

        self.assertIn("/api/auth/session", ENDPOINTS)
        self.assertIn("/api/assistant/runtime", ENDPOINTS)
        self.assertIn("/api/desktop/apps", ENDPOINTS)
        self.assertIn("/api/system/health", ENDPOINTS)

    def test_public_web_v2_does_not_fetch_protected_history_endpoints(self):
        source = (ROOT / "interface/web_v2/app.js").read_text(encoding="utf-8")

        self.assertIn("if (!state.auth?.authenticated) {\n      state.sessions = [];", source)
        self.assertIn("if (!state.auth?.authenticated) {\n      state.messages = [];", source)

    def test_launcher_quiets_waitress_queue_noise(self):
        source = (ROOT / "run_voris.py").read_text(encoding="utf-8")

        self.assertIn('logging.getLogger("waitress.queue").setLevel(logging.ERROR)', source)

    def test_desktop_voice_loop_is_explicit_opt_in(self):
        source = (ROOT / "voice/desktop_voice_runtime.py").read_text(encoding="utf-8")

        self.assertIn("AURA_ENABLE_DESKTOP_VOICE_LOOP", source)
        self.assertIn("desktop_voice_loop_disabled", source)


if __name__ == "__main__":
    unittest.main()
