import unittest
from unittest.mock import patch

from voice.noise_filter import clean_transcript_text
from voice.voice_pipeline import process_voice_text
from voice.wake_word import detect_wake_word


class VoicePipelineTests(unittest.TestCase):
    def test_wake_word_must_match_at_start(self):
        result = detect_wake_word("I think hey aura is a cool phrase")
        self.assertFalse(result["detected"])

    def test_noise_filter_preserves_meaning_without_forcing_lowercase(self):
        cleaned = clean_transcript_text("Um Please open Chrome, plz")
        self.assertEqual(cleaned, "Please open Chrome, please")

    def test_voice_pipeline_acknowledges_wake_word_without_command(self):
        result = process_voice_text("Hey Aura")
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "wake_only")
        self.assertTrue(result["requires_followup_command"])
        self.assertIn(result["assistant_reply"], {"Yes?", "I'm here.", "Go ahead."})

    def test_voice_pipeline_routes_transcript_through_main_assistant_path(self):
        fake_result = {"response": "Quantum computing uses qubits.", "provider": "groq"}
        with patch("voice.voice_pipeline.process_command_detailed", return_value=fake_result) as process_mock:
            result = process_voice_text(
                "Hey Aura what is quantum computing",
                session_id="session-42",
                user_profile={"id": "owner"},
                current_mode="hybrid",
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["command_text"], "what is quantum computing")
        self.assertEqual(result["result"]["provider"], "groq")
        process_mock.assert_called_once_with(
            "what is quantum computing",
            session_id="session-42",
            user_profile={"id": "owner"},
            current_mode="hybrid",
        )


if __name__ == "__main__":
    unittest.main()
