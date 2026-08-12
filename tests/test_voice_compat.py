import importlib
import unittest

import voice.speech_to_text as speech_to_text
import voice.text_to_speech as text_to_speech
import voice.voice_controller as voice_controller
import voice.voice_manager as voice_manager


class VoiceCompatibilityTests(unittest.TestCase):
    def test_text_to_speech_exposes_legacy_cli_functions(self):
        self.assertTrue(callable(text_to_speech.speak))
        self.assertTrue(callable(text_to_speech.stop_speaking))

    def test_speech_to_text_exposes_legacy_cli_listen_function(self):
        self.assertTrue(callable(speech_to_text.listen))

    def test_main_module_imports_successfully(self):
        main_module = importlib.import_module("main")
        self.assertTrue(callable(main_module.start_goku))

    def test_voice_status_marks_wake_as_beta_push_to_talk(self):
        status = voice_controller.get_voice_status()

        self.assertEqual(status["wake_word"]["mode"], "beta_single_phrase")
        self.assertIn("push-to-talk", status["wake_word"]["continuous_listening_note"])
        self.assertIn("always-on", status["wake_word"]["truth_note"])


class SpeechControlTests(unittest.TestCase):
    def test_is_stop_speech_phrase_matches_explicit_commands(self):
        for phrase in (
            "stop",
            "Stop.",
            "okay stop",
            "Okay, stop!",
            "stop it",
            "enough",
            "that's enough",
            "I'll read it myself",
            "ill read it myself",
            "let me read",
            "be quiet",
            "shut up",
            "silence",
        ):
            self.assertTrue(
                voice_manager.is_stop_speech_phrase(phrase),
                msg=f"Expected stop-speech match for {phrase!r}",
            )

    def test_is_stop_speech_phrase_ignores_unrelated_transcripts(self):
        for phrase in (
            "",
            "what is the weather",
            "tell me about transformers",
            "can you help me with my homework",
            "please continue",
        ):
            self.assertFalse(
                voice_manager.is_stop_speech_phrase(phrase),
                msg=f"Expected NOT stop-speech match for {phrase!r}",
            )

    def test_build_spoken_preview_reads_short_response_fully(self):
        short = "Hello there. This is a quick response."
        self.assertEqual(voice_manager.build_spoken_preview(short), short)

    def test_build_spoken_preview_summarises_very_long_response(self):
        long_text = " ".join(
            f"Sentence number {index} is part of the long response and contains plenty of detail."
            for index in range(60)
        )
        preview = voice_manager.build_spoken_preview(long_text)
        self.assertTrue(preview)
        self.assertLess(len(preview), len(long_text))
        self.assertIn("on screen", preview.lower())


if __name__ == "__main__":
    unittest.main()
