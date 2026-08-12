import unittest
from pathlib import Path
from tempfile import mkdtemp
from unittest.mock import patch

import tools.tool_guard as tool_guard
import tools.validation_tools as validation_tools
from tools.tool_guard import guard_and_execute


class ToolExecutionTests(unittest.TestCase):
    def test_private_file_list_requires_confirmation_but_executes_when_confirmed(self):
        root = Path(mkdtemp())
        (root / "sample.txt").write_text("demo", encoding="utf-8")
        with patch.object(validation_tools, "WORKSPACE_ROOT", root.resolve()):
            with patch.object(tool_guard, "enforce_action", return_value={"allowed": True, "status": "approved", "reason": "Private action approved."}):
                result = guard_and_execute("file.list", username="tester", confirmed=True, path_value=str(root))
        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "executed")

    def test_critical_delete_is_blocked_without_pin(self):
        root = Path(mkdtemp())
        target = root / "demo.txt"
        target.write_text("demo", encoding="utf-8")
        with patch.object(validation_tools, "WORKSPACE_ROOT", root.resolve()):
            with patch.object(tool_guard, "enforce_action", return_value={"allowed": False, "status": "pin", "reason": "Critical action requires PIN."}):
                result = guard_and_execute("file.delete", path_value=str(target))
        self.assertFalse(result["success"])
        self.assertEqual(result["status"], "pin")


if __name__ == "__main__":
    unittest.main()
