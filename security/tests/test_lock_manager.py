import unittest
from pathlib import Path
from tempfile import mkdtemp
from unittest.mock import patch

import security.lock_manager as lock_manager


class LockManagerTests(unittest.TestCase):
    def test_lock_and_unlock_resource_with_temp_store(self):
        temp_root = Path(mkdtemp())
        with patch.object(lock_manager, "LOCKS_FILE", temp_root / "locks.json"):
            lock_manager.lock_resource("chat-1", owner="beast")
            self.assertTrue(lock_manager.is_locked("chat-1"))
            lock_manager.unlock_resource("chat-1")
            self.assertFalse(lock_manager.is_locked("chat-1"))


if __name__ == "__main__":
    unittest.main()
