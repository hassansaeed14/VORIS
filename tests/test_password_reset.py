"""Regression tests for the forgot-password / password-reset flow."""

from __future__ import annotations

import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import bcrypt

import security.auth_manager as auth_manager
import security.otp_manager as otp_manager
import security.password_reset as password_reset
import security.session_manager as session_manager


def _hash_pw(text: str) -> str:
    return bcrypt.hashpw(text.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _make_user_file(tmp_dir: Path, *, username: str = "tester",
                    email: str = "tester@aura.dev",
                    password: str = "OldPassw0rd!") -> Path:
    users_path = tmp_dir / "users.json"
    payload = {
        username: {
            "id": "user-abc-123",
            "username": username,
            "password": _hash_pw(password),
            "name": "Test User",
            "email": email,
            "admin": False,
            "owner": False,
        }
    }
    users_path.write_text(json.dumps(payload), encoding="utf-8")
    return users_path


class PasswordResetFlowTests(unittest.TestCase):
    """End-to-end assertions for request -> verify -> confirm."""

    def _run_happy_path(self, identifier: str) -> None:
        with TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            users_file = _make_user_file(tmp_dir)
            reset_state = tmp_dir / "password_reset_state.json"
            otp_state = tmp_dir / "otp_state.json"
            sessions_file = tmp_dir / "sessions.json"

            with patch.object(auth_manager, "USERS_FILE", users_file), \
                 patch.object(password_reset, "RESET_STATE_FILE", reset_state), \
                 patch.object(otp_manager, "OTP_STATE_FILE", otp_state), \
                 patch.object(session_manager, "SESSIONS_FILE", sessions_file):
                # Seed a live login session that must be revoked after reset.
                session_token = session_manager.create_login_session(
                    user_id="user-abc-123",
                    username="tester",
                    ip_address="127.0.0.1",
                    user_agent="pytest",
                )
                self.assertIsNotNone(session_manager.get_login_session(session_token))

                # 1. Request reset
                issued = password_reset.request_password_reset(
                    identifier,
                    ip_address="198.51.100.10",
                    user_agent="pytest",
                )
                self.assertTrue(issued["success"])
                self.assertEqual(issued["status"], "issued")
                reset_token = issued["reset_token"]
                code = issued["code"]  # dev delivery returns code inline
                self.assertTrue(reset_token)
                self.assertTrue(code)
                # Identifier must NOT leak back
                self.assertNotIn("username", issued)
                self.assertNotIn("user_id", issued)

                # 2. Verify OTP
                verified = password_reset.verify_password_reset(
                    reset_token, code, ip_address="198.51.100.10"
                )
                self.assertTrue(verified["success"], verified)
                self.assertEqual(verified["status"], "verified")
                confirm_token = verified["confirm_token"]
                self.assertTrue(confirm_token)

                # 3. Confirm with new password
                confirmed = password_reset.confirm_password_reset(
                    reset_token,
                    confirm_token,
                    "NewPassw0rd!X",
                    ip_address="198.51.100.10",
                )
                self.assertTrue(confirmed["success"], confirmed)
                self.assertEqual(confirmed["status"], "password_rotated")

                # Password hash must have rotated
                updated = json.loads(users_file.read_text(encoding="utf-8"))
                self.assertTrue(
                    bcrypt.checkpw(b"NewPassw0rd!X", updated["tester"]["password"].encode())
                )
                self.assertIn("password_rotated_at", updated["tester"])

                # Existing sessions must be revoked
                self.assertIsNone(session_manager.get_login_session(session_token))

                # Token cannot be replayed
                replay = password_reset.confirm_password_reset(
                    reset_token, confirm_token, "NewPassw0rd!X",
                )
                self.assertFalse(replay["success"])
                self.assertEqual(replay["status"], "consumed")

    def test_happy_path_by_email(self):
        self._run_happy_path("tester@aura.dev")

    def test_happy_path_by_username(self):
        self._run_happy_path("tester")

    def test_unknown_identifier_still_returns_reset_token(self):
        """No account enumeration — unknown identifier must not leak."""

        with TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            users_file = _make_user_file(tmp_dir)
            reset_state = tmp_dir / "password_reset_state.json"
            otp_state = tmp_dir / "otp_state.json"

            with patch.object(auth_manager, "USERS_FILE", users_file), \
                 patch.object(password_reset, "RESET_STATE_FILE", reset_state), \
                 patch.object(otp_manager, "OTP_STATE_FILE", otp_state):
                result = password_reset.request_password_reset(
                    "nobody@nowhere.test",
                    ip_address="198.51.100.20",
                )
                self.assertTrue(result["success"])
                self.assertEqual(result["status"], "issued")
                self.assertIn("reset_token", result)
                # Phantom must NOT surface an OTP code
                self.assertIsNone(result.get("code"))

                # Verifying any OTP against a phantom token must fail
                failed = password_reset.verify_password_reset(
                    result["reset_token"], "000000",
                )
                self.assertFalse(failed["success"])
                self.assertEqual(failed["status"], "incorrect")

    def test_phantom_locks_after_five_attempts(self):
        with TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            users_file = _make_user_file(tmp_dir)
            reset_state = tmp_dir / "password_reset_state.json"
            otp_state = tmp_dir / "otp_state.json"

            with patch.object(auth_manager, "USERS_FILE", users_file), \
                 patch.object(password_reset, "RESET_STATE_FILE", reset_state), \
                 patch.object(otp_manager, "OTP_STATE_FILE", otp_state):
                issued = password_reset.request_password_reset(
                    "ghost@nowhere.test", ip_address="198.51.100.30"
                )
                token = issued["reset_token"]
                for _ in range(4):
                    result = password_reset.verify_password_reset(token, "000000")
                    self.assertEqual(result["status"], "incorrect")
                final = password_reset.verify_password_reset(token, "000000")
                self.assertEqual(final["status"], "too_many_attempts")

    def test_rate_limit_per_identifier(self):
        with TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            users_file = _make_user_file(tmp_dir)
            reset_state = tmp_dir / "password_reset_state.json"
            otp_state = tmp_dir / "otp_state.json"

            with patch.object(auth_manager, "USERS_FILE", users_file), \
                 patch.object(password_reset, "RESET_STATE_FILE", reset_state), \
                 patch.object(otp_manager, "OTP_STATE_FILE", otp_state):
                for _ in range(password_reset.REQUESTS_PER_IDENTIFIER):
                    ok = password_reset.request_password_reset(
                        "tester@aura.dev", ip_address="198.51.100.40",
                    )
                    self.assertTrue(ok["success"])
                blocked = password_reset.request_password_reset(
                    "tester@aura.dev", ip_address="198.51.100.40",
                )
                self.assertFalse(blocked["success"])
                self.assertEqual(blocked["status"], "rate_limited")

    def test_weak_password_rejected_at_confirm(self):
        with TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            users_file = _make_user_file(tmp_dir)
            reset_state = tmp_dir / "password_reset_state.json"
            otp_state = tmp_dir / "otp_state.json"
            sessions_file = tmp_dir / "sessions.json"

            with patch.object(auth_manager, "USERS_FILE", users_file), \
                 patch.object(password_reset, "RESET_STATE_FILE", reset_state), \
                 patch.object(otp_manager, "OTP_STATE_FILE", otp_state), \
                 patch.object(session_manager, "SESSIONS_FILE", sessions_file):
                issued = password_reset.request_password_reset(
                    "tester@aura.dev", ip_address="198.51.100.50"
                )
                verified = password_reset.verify_password_reset(
                    issued["reset_token"], issued["code"]
                )
                weak = password_reset.confirm_password_reset(
                    issued["reset_token"], verified["confirm_token"], "short",
                )
                self.assertFalse(weak["success"])
                self.assertEqual(weak["status"], "weak_password")

    def test_confirm_requires_valid_confirm_token(self):
        with TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            users_file = _make_user_file(tmp_dir)
            reset_state = tmp_dir / "password_reset_state.json"
            otp_state = tmp_dir / "otp_state.json"
            sessions_file = tmp_dir / "sessions.json"

            with patch.object(auth_manager, "USERS_FILE", users_file), \
                 patch.object(password_reset, "RESET_STATE_FILE", reset_state), \
                 patch.object(otp_manager, "OTP_STATE_FILE", otp_state), \
                 patch.object(session_manager, "SESSIONS_FILE", sessions_file):
                issued = password_reset.request_password_reset(
                    "tester@aura.dev", ip_address="198.51.100.60"
                )
                password_reset.verify_password_reset(
                    issued["reset_token"], issued["code"]
                )
                bad = password_reset.confirm_password_reset(
                    issued["reset_token"], "not-the-real-confirm-token",
                    "AnotherStrong1!",
                )
                self.assertFalse(bad["success"])
                self.assertEqual(bad["status"], "invalid_confirm_token")

    def test_confirm_without_otp_verify_is_blocked(self):
        with TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            users_file = _make_user_file(tmp_dir)
            reset_state = tmp_dir / "password_reset_state.json"
            otp_state = tmp_dir / "otp_state.json"

            with patch.object(auth_manager, "USERS_FILE", users_file), \
                 patch.object(password_reset, "RESET_STATE_FILE", reset_state), \
                 patch.object(otp_manager, "OTP_STATE_FILE", otp_state):
                issued = password_reset.request_password_reset(
                    "tester@aura.dev", ip_address="198.51.100.70"
                )
                blocked = password_reset.confirm_password_reset(
                    issued["reset_token"], "whatever",
                    "Strong1Pass!",
                )
                self.assertFalse(blocked["success"])
                self.assertEqual(blocked["status"], "otp_required")

    def test_reset_action_is_registered_critical(self):
        from config.permissions import get_action_policy
        policy = get_action_policy("password_reset")
        self.assertEqual(policy.trust_level, "critical")
        self.assertTrue(policy.requires_otp)


if __name__ == "__main__":
    unittest.main()
