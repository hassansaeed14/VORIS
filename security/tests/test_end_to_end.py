import unittest
from pathlib import Path
from tempfile import mkdtemp
from unittest.mock import patch

import security.session_manager as session_manager
from security.access_control import evaluate_access


class SecurityEndToEndSmokeTests(unittest.TestCase):
    def test_sensitive_action_can_be_reused_after_session_approval(self):
        # Approvals live in ACTION_APPROVAL_FILE; login sessions live in
        # SESSIONS_FILE (renamed from the legacy ``SESSION_FILE``). Isolate
        # both so the smoke test never touches the real on-disk store.
        temp_root = Path(mkdtemp())
        with patch.object(session_manager, "ACTION_APPROVAL_FILE", temp_root / "action_approvals.json"), \
             patch.object(session_manager, "SESSIONS_FILE", temp_root / "sessions.json"):
            session_manager.approve_action("security-e2e", "screenshot", minutes=5)
            result = evaluate_access("screenshot", session_id="security-e2e")

        self.assertTrue(result["success"])
        self.assertEqual(result["status"], "approved")


if __name__ == "__main__":
    unittest.main()
