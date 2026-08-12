from agents.agent_fabric import build_agent_exports

globals().update(build_agent_exports(__file__))
import unittest
from unittest.mock import patch

import agents.integration.translation_agent as translation_agent


class TranslationAgentTests(unittest.TestCase):
    def test_translate_uses_structured_parser_output(self):
        fake_response = (
            "ORIGINAL TEXT: Hello\n"
            "TRANSLATION: السلام علیکم\n"
            "SOURCE LANGUAGE: English\n"
            "TARGET LANGUAGE: Urdu\n"
            "NOTES: greeting"
        )

        with patch.object(translation_agent.translation_agent.llm, "translate", return_value=fake_response):
            result = translation_agent.translate("Hello", "urdu", "english")

        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["translated_text"], "السلام علیکم")
        self.assertEqual(result["data"]["target_language"], "Urdu")


if __name__ == "__main__":
    unittest.main()
