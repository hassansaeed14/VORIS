import unittest

from brain.intent_engine import detect_intent_with_confidence


class IntentEngineTests(unittest.TestCase):
    def test_detects_casual_conversation(self):
        intent, confidence = detect_intent_with_confidence("hi how are you")
        self.assertEqual(intent, "conversation")
        self.assertGreaterEqual(confidence, 0.6)

    def test_detects_translation_request(self):
        intent, confidence = detect_intent_with_confidence("translate this to urdu")
        self.assertEqual(intent, "translation")
        self.assertGreaterEqual(confidence, 0.35)

    def test_detects_math_expression(self):
        intent, confidence = detect_intent_with_confidence("14 / 2 + 3")
        self.assertEqual(intent, "math")
        self.assertGreaterEqual(confidence, 0.8)

    def test_detects_currency_from_iso_codes(self):
        intent, confidence = detect_intent_with_confidence("convert 25 usd to pkr")
        self.assertEqual(intent, "currency")
        self.assertGreaterEqual(confidence, 0.6)

    def test_detects_write_request(self):
        intent, confidence = detect_intent_with_confidence("write a short blog post about AI")
        self.assertEqual(intent, "write")
        self.assertGreaterEqual(confidence, 0.35)

    def test_detects_document_generation_request(self):
        intent, confidence = detect_intent_with_confidence("write assignment on artificial intelligence")
        self.assertEqual(intent, "document")
        self.assertGreaterEqual(confidence, 0.35)


if __name__ == "__main__":
    unittest.main()
