from agents.agent_fabric import build_agent_exports

globals().update(build_agent_exports(__file__))
import unittest

from agents.integration.password_agent import check_password_strength, generate_password


class PasswordAgentTests(unittest.TestCase):
    def test_generate_password_returns_entropy_and_length(self):
        result = generate_password(length=16)
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["length"], 16)
        self.assertIn("entropy_bits", result["data"])

    def test_check_password_strength_scores_common_password_as_weak(self):
        result = check_password_strength("password123")
        self.assertTrue(result["success"])
        self.assertEqual(result["data"]["strength"], "WEAK")


if __name__ == "__main__":
    unittest.main()
