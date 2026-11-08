import importlib.util
import json
import os
from pathlib import Path
import tempfile
import threading
import unittest
from unittest import mock


FORWARDER_PATH = Path(__file__).resolve().parents[1] / "mail_forwarder_pro.py"
SPEC = importlib.util.spec_from_file_location("mail_forwarder_pro_under_test", FORWARDER_PATH)
forwarder = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(forwarder)


class UidStateTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state_path = Path(self.temp_dir.name) / "state" / "forwarded_uids.json"
        forwarder.UID_STORE_FILE = str(self.state_path)
        forwarder.REQUIRE_UID_STORE = False

    def tearDown(self):
        forwarder.REQUIRE_UID_STORE = False
        self.temp_dir.cleanup()

    def test_missing_state_is_empty(self):
        self.assertEqual(forwarder.load_forwarded_uids(), set())

    def test_missing_state_fails_when_required(self):
        forwarder.REQUIRE_UID_STORE = True
        with self.assertRaises(FileNotFoundError):
            forwarder.load_forwarded_uids()

    def test_valid_state_is_loaded(self):
        self.state_path.parent.mkdir()
        self.state_path.write_text('["10", "2"]', encoding="utf-8")
        self.assertEqual(forwarder.load_forwarded_uids(), {"10", "2"})

    def test_corrupt_state_fails_closed(self):
        self.state_path.parent.mkdir()
        self.state_path.write_text("not json", encoding="utf-8")
        with self.assertRaises(json.JSONDecodeError):
            forwarder.load_forwarded_uids()

    def test_wrong_state_shape_fails_closed(self):
        self.state_path.parent.mkdir()
        self.state_path.write_text('{"uid": "10"}', encoding="utf-8")
        with self.assertRaises(ValueError):
            forwarder.load_forwarded_uids()

    def test_non_string_uid_fails_closed(self):
        self.state_path.parent.mkdir()
        self.state_path.write_text('[10]', encoding="utf-8")
        with self.assertRaises(ValueError):
            forwarder.load_forwarded_uids()

    def test_save_is_sorted_private_and_leaves_no_temp_file(self):
        forwarder.save_forwarded_uids({"10", "2"})
        self.assertEqual(json.loads(self.state_path.read_text()), ["10", "2"])
        self.assertEqual(self.state_path.stat().st_mode & 0o777, 0o600)
        self.assertEqual(list(self.state_path.parent.glob("*.tmp")), [])

    def test_failed_replace_preserves_old_state_and_cleans_temp(self):
        self.state_path.parent.mkdir()
        self.state_path.write_text('["old"]', encoding="utf-8")
        with mock.patch.object(forwarder.os, "replace", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                forwarder.save_forwarded_uids({"new"})
        self.assertEqual(json.loads(self.state_path.read_text()), ["old"])
        self.assertEqual(list(self.state_path.parent.glob(".forwarded_uids.*.tmp")), [])


class FakeImap:
    def __init__(self, host, port, **kwargs):
        self.host = host
        self.port = port
        self.kwargs = kwargs
        self.selected = None

    def login(self, account, password):
        self.login_args = (account, password)

    def select(self, mailbox, readonly):
        self.selected = (mailbox, readonly)


class FakeSmtp:
    instances = []

    def __init__(self, host, port, **kwargs):
        self.host = host
        self.port = port
        self.kwargs = kwargs
        self.calls = []
        self.__class__.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self.calls.append("close")

    def starttls(self, context):
        self.calls.append(("starttls", context))

    def login(self, account, password):
        self.calls.append(("login", account, password))

    def sendmail(self, account, target, message):
        self.calls.append(("sendmail", account, target, message))


class ForwarderBehaviorTests(unittest.TestCase):
    def setUp(self):
        forwarder.IMAP_HOST = "imap.example.test"
        forwarder.IMAP_PORT = 993
        forwarder.SMTP_HOST = "smtp.example.test"
        forwarder.SMTP_PORT = 587
        forwarder.EMAIL_ACCOUNT = "source@example.test"
        forwarder.EMAIL_PASSWORD = "secret"
        forwarder.TARGET_EMAIL = "target@example.test"
        forwarder.CONNECTION_TIMEOUT = 23
        forwarder.REQUIRE_UID_STORE = False
        forwarder.STOP_EVENT = None

    def test_imap_uses_configured_timeout_and_readonly_inbox(self):
        with mock.patch.object(forwarder.imaplib, "IMAP4_SSL", FakeImap):
            mail = forwarder.connect_imap()
        self.assertEqual(mail.kwargs["timeout"], 23)
        self.assertEqual(mail.login_args, ("source@example.test", "secret"))
        self.assertEqual(mail.selected, ("INBOX", True))

    def test_smtp_timeout_and_send_order_are_preserved(self):
        FakeSmtp.instances = []
        with mock.patch.object(forwarder.smtplib, "SMTP", FakeSmtp):
            self.assertTrue(forwarder.send_raw_email(b"raw message"))
        smtp = FakeSmtp.instances[0]
        self.assertEqual(smtp.kwargs["timeout"], 23)
        self.assertEqual([call[0] if isinstance(call, tuple) else call for call in smtp.calls],
                         ["starttls", "login", "sendmail", "close"])

    def test_resent_headers_preserve_original_message(self):
        raw = b"From: original@example.test\r\nSubject: test\r\n\r\nbody\r\n"
        result = forwarder.build_resent_message(raw)
        self.assertTrue(result.startswith(b"Resent-From: source@example.test\r\n"))
        self.assertIn(b"\r\nResent-To: target@example.test\r\n", result)
        self.assertTrue(result.endswith(raw))

    def test_resent_rejects_message_without_crlf_separator(self):
        self.assertIsNone(forwarder.build_resent_message(b"Subject: test\n\nbody"))


if __name__ == "__main__":
    unittest.main()
