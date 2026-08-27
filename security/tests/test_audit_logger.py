import json
import unittest
from pathlib import Path
from tempfile import mkdtemp
from unittest.mock import patch

import security.audit_logger as audit_logger


class AuditLoggerTests(unittest.TestCase):
    def test_record_audit_event_writes_jsonl_entry(self):
        temp_root = Path(mkdtemp())
        with patch.object(audit_logger, "AUDIT_LOG_FILE", temp_root / "audit.jsonl"):
            event = audit_logger.record_audit_event(
                action_name="file_delete",
                allowed=False,
                trust_level="critical",
                reason="PIN_REQUIRED",
                username="beast",
                session_id="audit-test",
            )
            payload = json.loads((temp_root / "audit.jsonl").read_text(encoding="utf-8").strip())

        self.assertEqual(payload["action_name"], "file_delete")
        self.assertFalse(payload["allowed"])
        self.assertEqual(event["session_id"], "audit-test")


if __name__ == "__main__":
    unittest.main()
