import unittest
from pathlib import Path

from security.permission_engine import classify_action
from voice.assistant_runtime import get_assistant_runtime_status


PROJECT_ROOT = Path(__file__).resolve().parents[1]
WEB_V2 = PROJECT_ROOT / "interface" / "web_v2"


class RealAssistantRuntimeTests(unittest.TestCase):
    def test_assistant_modes_report_truthful_runtime_status(self):
        status = get_assistant_runtime_status()

        self.assertTrue(status["success"])
        self.assertTrue(status["modes"]["text"]["available"])
        self.assertTrue(status["modes"]["push_to_talk"]["requires_microphone"])
        self.assertFalse(status["modes"]["desktop_voice"]["active"])
        self.assertIn(
            status["modes"]["desktop_voice"]["message"],
            {
                "Desktop voice runtime is not active.",
                "Desktop voice runtime is not available on this system.",
                "Desktop voice runtime is installed but disabled for production safety. Set AURA_ENABLE_DESKTOP_VOICE_LOOP=true to test local wake listening.",
            },
        )
        self.assertFalse(status["safety"]["always_on_browser_wake"])

    def test_permission_classification_for_real_assistant_commands(self):
        self.assertEqual(classify_action("open YouTube and search carryminati"), "safe")
        self.assertEqual(classify_action("open Chrome and search AI trends"), "safe")
        self.assertEqual(classify_action("open ChatGPT and ask it to write an assignment"), "sensitive")
        self.assertEqual(classify_action("type my password"), "critical")
        self.assertEqual(classify_action("make a payment"), "critical")
        self.assertEqual(classify_action("delete files"), "critical")

    def test_copy_and_speak_controls_are_rendered_by_web_v2(self):
        html = (WEB_V2 / "aura.html").read_text(encoding="utf-8")
        script = (WEB_V2 / "app.js").read_text(encoding="utf-8")

        self.assertIn('id="speechToggleButton"', html)
        self.assertIn('id="desktopVoiceButton"', html)
        self.assertIn('id="assistantModeLabel"', html)
        self.assertIn('id="voiceRuntimeLabel"', html)
        self.assertIn("function buildMessageActions", script)
        self.assertIn("function copyMessageText", script)
        self.assertIn("function speakMessage", script)
        self.assertIn("window.speechSynthesis.speak", script)

    def test_web_v2_polish_labels_and_action_cards_stay_truthful(self):
        html = (WEB_V2 / "aura.html").read_text(encoding="utf-8")
        script = (WEB_V2 / "app.js").read_text(encoding="utf-8")
        styles = (WEB_V2 / "styles.css").read_text(encoding="utf-8")

        self.assertIn("Limited response", script)
        self.assertIn("function actionStatusLabel", script)
        self.assertIn("function actionStatusMarker", script)
        self.assertIn("Approval required. VORIS will not type, press keys, or scroll", script)
        self.assertIn("function buildWelcomeCard", script)
        self.assertIn("function normalizeActionTrace", script)
        self.assertIn("function syncRuntimeStateFromPayload", script)
        self.assertIn("messageTextForControls", script)
        self.assertIn(".welcome-card", styles)
        self.assertIn(".automation-warning--blocked", styles)
        self.assertIn(".message-action-button.is-success", styles)

        combined = "\n".join([html, script])
        self.assertNotIn("Fallback result", combined)
        self.assertNotIn("fallback path", combined)
        self.assertNotIn("degraded_assistant", combined)
        self.assertNotIn("Invitation required", combined)
        self.assertNotIn("click, or scroll", combined)

    def test_tts_toggle_persists_without_forcing_text_chat_speech(self):
        script = (WEB_V2 / "app.js").read_text(encoding="utf-8")

        self.assertIn("function toggleSpeechEnabled", script)
        self.assertIn("function toggleDesktopVoice", script)
        self.assertIn("/api/voice/desktop/start", script)
        self.assertIn("/api/voice/desktop/interrupt", script)
        self.assertIn("STORAGE_KEYS.speechEnabled", script)
        self.assertIn("state.speechEnabled && state.speechCommandInFlight", script)
        self.assertIn("Text chat stays silent unless you press Speak", script)


if __name__ == "__main__":
    unittest.main()
