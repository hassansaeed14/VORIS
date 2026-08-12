from agents.agent_fabric import build_agent_exports

globals().update(build_agent_exports(__file__))
import unittest
from unittest.mock import patch

import agents.integration.reminder_agent as reminder_agent


class ReminderAgentTests(unittest.TestCase):
    def test_add_and_list_reminder_uses_repository_hooks(self):
        stored_items = []

        def fake_load():
            return list(stored_items)

        def fake_save(items):
            stored_items[:] = list(items)

        with patch.object(reminder_agent.reminder_agent.repo, "load", side_effect=fake_load), patch.object(
            reminder_agent.reminder_agent.repo,
            "save",
            side_effect=fake_save,
        ):
            created = reminder_agent.add_reminder("Review AURA build", "5 pm", "tomorrow")
            listed = reminder_agent.get_reminders()

        self.assertTrue(created["success"])
        self.assertEqual(created["data"]["text"], "Review AURA build")
        self.assertTrue(listed["success"])
        self.assertEqual(listed["data"]["count"], 1)


if __name__ == "__main__":
    unittest.main()
