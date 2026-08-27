import unittest
from pathlib import Path
from tempfile import mkdtemp
from unittest.mock import patch

import security.pin_manager as pin_manager


class PinManagerTests(unittest.TestCase):
    def test_pin_can_be_set_and_verified(self):
        temp_dir = mkdtemp()
        with patch.object(pin_manager, "PIN_STATE_FILE", Path(temp_dir) / "pin.json"):
            set_result = pin_manager.set_pin("1234")
            verify_result = pin_manager.verify_pin("1234")
            bad_result = pin_manager.verify_pin("0000")

        self.assertTrue(set_result["success"])
        self.assertTrue(verify_result["success"])
        self.assertFalse(bad_result["success"])


if __name__ == "__main__":
    unittest.main()
