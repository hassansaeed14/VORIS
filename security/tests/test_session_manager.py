import unittest
from pathlib import Path
from tempfile import mkdtemp
from unittest.mock import patch

import security.session_manager as session_manager


class SessionManagerTests(unittest.TestCase):
    def test_session_approval_can_be_created_and_checked(self):
        # Action approvals are persisted via ``ACTION_APPROVAL_FILE``; the old
        # test patched ``SESSION_FILE`` (renamed to ``SESSIONS_FILE``) which
        # was never the right target for approve_action/is_action_approved.
        temp_dir = mkdtemp()
        approval_file = Path(temp_dir) / "action_approvals.json"
        sessions_file = Path(temp_dir) / "sessions.json"
        with patch.object(session_manager, "ACTION_APPROVAL_FILE", approval_file), \
             patch.object(session_manager, "SESSIONS_FILE", sessions_file):
            session_manager.approve_action("abc", "file_write", minutes=5)
            self.assertTrue(session_manager.is_action_approved("abc", "file_write"))
            session_manager.revoke_action("abc", "file_write")
            self.assertFalse(session_manager.is_action_approved("abc", "file_write"))


if __name__ == "__main__":
    unittest.main()
