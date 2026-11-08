import contextlib
import hashlib
import importlib.util
from importlib.machinery import SourceFileLoader
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock


MAILCTL_PATH = Path(__file__).resolve().parents[1] / "mailctl"
LOADER = SourceFileLoader("mailctl_under_test", str(MAILCTL_PATH))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
mailctl = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(mailctl)


class MailctlTestCase(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name)
        self.config_home = self.root / "config"
        self.state_home = self.root / "state"
        self.env_patcher = mock.patch.dict(
            os.environ,
            {
                "XDG_CONFIG_HOME": str(self.config_home),
                "XDG_STATE_HOME": str(self.state_home),
                "MAILCTL_PASSWORD": "test-secret",
            },
            clear=False,
        )
        self.env_patcher.start()
        self.paths = mailctl.Paths(
            self.config_home / "mailctl" / "config.json",
            self.state_home / "mailctl",
        )
        self.legacy = self.root / "legacy.json"

    def tearDown(self):
        self.env_patcher.stop()
        self.temp_dir.cleanup()

    def init_args(self, **overrides):
        values = {
            "account": "source@example.test",
            "target": "target@example.test",
            "imap_host": "imap.example.test",
            "imap_port": 993,
            "smtp_host": "smtp.example.test",
            "smtp_port": 587,
            "check_interval": 5,
            "connection_timeout": 15,
            "legacy_state": str(self.legacy),
        }
        values.update(overrides)
        return SimpleNamespace(**values)

    def call_init(self, **overrides):
        with contextlib.redirect_stdout(io.StringIO()):
            return mailctl.cmd_init(self.init_args(**overrides), self.paths)

    def test_init_migrates_uid_without_touching_legacy_and_uses_private_modes(self):
        self.legacy.write_text('["10", "2"]\n', encoding="utf-8")
        original = self.legacy.read_bytes()
        self.assertEqual(self.call_init(), 0)

        self.assertEqual(json.loads(self.paths.uid_state.read_text()), ["10", "2"])
        self.assertEqual(self.legacy.read_bytes(), original)
        self.assertEqual(self.paths.config.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.paths.secrets.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.paths.uid_state.stat().st_mode & 0o777, 0o600)
        self.assertEqual(self.paths.config.parent.stat().st_mode & 0o777, 0o700)
        self.assertEqual(self.paths.state_dir.stat().st_mode & 0o777, 0o700)
        config_text = self.paths.config.read_text()
        self.assertNotIn("test-secret", config_text)
        self.assertNotIn("password\":", config_text)

    def test_init_without_legacy_creates_empty_state(self):
        self.call_init()
        self.assertEqual(json.loads(self.paths.uid_state.read_text()), [])

    def test_duplicate_init_does_not_overwrite_config(self):
        self.call_init()
        before = self.paths.config.read_bytes()
        with self.assertRaises(mailctl.MailctlError):
            self.call_init(account="other@example.test")
        self.assertEqual(self.paths.config.read_bytes(), before)

    def test_secret_file_round_trip_quotes_spaces_and_symbols(self):
        password = "p@ss word '\"$\\end"
        with mock.patch.dict(os.environ, {"MAILCTL_PASSWORD": password}):
            self.call_init()
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("MAILCTL_PASSWORD", None)
            config = mailctl.load_config(self.paths)
        self.assertEqual(config["_password"], password)

    def test_config_rejects_header_injection_and_bad_numbers(self):
        self.call_init()
        config = mailctl.load_config(self.paths)
        config["target_email"] = "target@example.test\r\nBcc: other@example.test"
        with self.assertRaises(mailctl.MailctlError):
            mailctl.validate_config(config)
        config["target_email"] = "target@example.test"
        config["imap_port"] = True
        with self.assertRaises(mailctl.MailctlError):
            mailctl.validate_config(config)

    def test_redaction_covers_even_short_secrets(self):
        self.assertEqual(mailctl.redact("abc xy", ["xy", "abc"]), "*** ***")

    def test_instance_lock_rejects_second_fd_and_reports_held_state(self):
        mailctl.secure_dir(self.paths.state_dir)
        with mailctl.instance_lock(self.paths):
            self.assertTrue(mailctl.lock_is_held(self.paths))
            with self.assertRaises(mailctl.MailctlError):
                with mailctl.instance_lock(self.paths):
                    pass
        self.assertFalse(mailctl.lock_is_held(self.paths))

    def test_run_injects_absolute_state_and_changes_to_state_dir(self):
        self.call_init()
        observed = {}

        class FakeForwarder:
            def main(self):
                observed["uid"] = self.UID_STORE_FILE
                observed["cwd"] = Path.cwd()
                observed["timeout"] = self.CONNECTION_TIMEOUT
                observed["password"] = self.EMAIL_PASSWORD

        previous_cwd = Path.cwd()
        try:
            with mock.patch.object(mailctl, "load_forwarder", return_value=FakeForwarder()):
                self.assertEqual(mailctl.cmd_run(SimpleNamespace(), self.paths), 0)
        finally:
            os.chdir(previous_cwd)
        self.assertEqual(observed["uid"], str(self.paths.uid_state))
        self.assertEqual(observed["cwd"], self.paths.state_dir)
        self.assertEqual(observed["timeout"], 15)
        self.assertEqual(observed["password"], "test-secret")

    def test_install_writes_user_unit_and_does_not_start_service(self):
        self.call_init()
        commands = []
        with mock.patch.object(mailctl, "run_process", side_effect=lambda command: commands.append(command) or 0):
            result = mailctl.cmd_install(SimpleNamespace(user=True), self.paths)
        self.assertEqual(result, 0)
        self.assertTrue(self.paths.unit.is_file())
        unit = self.paths.unit.read_text()
        self.assertIn("Type=simple", unit)
        self.assertIn("Restart=on-failure", unit)
        self.assertIn("WantedBy=default.target", unit)
        self.assertIn(str(self.paths.config), unit)
        self.assertIn(str(self.paths.state_dir), unit)
        self.assertIn(str(self.paths.secrets), unit)
        self.assertNotIn("test-secret", unit)
        self.assertEqual(commands, [
            ["systemctl", "--user", "daemon-reload"],
            ["systemctl", "--user", "enable", "mailctl.service"],
        ])

    def test_offline_doctor_passes_initialized_temp_environment(self):
        self.call_init()
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(stderr):
            result = mailctl.cmd_doctor(SimpleNamespace(network=False), self.paths)
        self.assertEqual(result, 0, stderr.getvalue())
        self.assertIn("UID 状态有效", stdout.getvalue())
        self.assertIn("未进行网络连接", stdout.getvalue())

    def test_corrupt_uid_state_makes_doctor_fail(self):
        self.call_init()
        self.paths.uid_state.write_text("broken", encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(mailctl.cmd_doctor(SimpleNamespace(network=False), self.paths), 1)


class FakeImap:
    instances = []
    error = None

    def __init__(self, host, port, **kwargs):
        self.host = host
        self.port = port
        self.kwargs = kwargs
        self.login_args = None
        self.selected = None
        self.logged_out = False
        self.__class__.instances.append(self)
        if self.__class__.error:
            raise self.__class__.error

    def login(self, account, password):
        self.login_args = (account, password)

    def select(self, mailbox, readonly):
        self.selected = (mailbox, readonly)
        return "OK", []

    def logout(self):
        self.logged_out = True


class FakeSmtp:
    instances = []

    def __init__(self, host, port, **kwargs):
        self.host = host
        self.port = port
        self.kwargs = kwargs
        self.calls = []
        self.__class__.instances.append(self)

    def ehlo(self):
        self.calls.append("ehlo")

    def starttls(self, context):
        self.calls.append("starttls")

    def login(self, account, password):
        self.calls.append(("login", account, password))

    def sendmail(self, *args):
        raise AssertionError("doctor 不得发送邮件")

    def quit(self):
        self.calls.append("quit")

    def close(self):
        self.calls.append("close")


class NetworkAndBackupTests(MailctlTestCase):
    def test_network_doctor_authenticates_without_fetch_or_send(self):
        self.call_init()
        config = mailctl.load_config(self.paths)
        FakeImap.instances = []
        FakeImap.error = None
        FakeSmtp.instances = []
        with mock.patch.object(mailctl.imaplib, "IMAP4_SSL", FakeImap), \
                mock.patch.object(mailctl.smtplib, "SMTP", FakeSmtp):
            results = mailctl.network_diagnostics(config)
        self.assertTrue(all(success for success, _ in results), results)
        self.assertEqual(FakeImap.instances[0].selected, ("INBOX", True))
        self.assertTrue(FakeImap.instances[0].logged_out)
        smtp = FakeSmtp.instances[0]
        self.assertIn("starttls", smtp.calls)
        self.assertIn("quit", smtp.calls)
        self.assertFalse(any(isinstance(call, tuple) and call[0] == "sendmail" for call in smtp.calls))

    def test_network_error_is_redacted(self):
        self.call_init()
        config = mailctl.load_config(self.paths)
        FakeImap.error = RuntimeError("login failed: test-secret source@example.test")
        with mock.patch.object(mailctl.imaplib, "IMAP4_SSL", FakeImap), \
                mock.patch.object(mailctl.smtplib, "SMTP", FakeSmtp):
            results = mailctl.network_diagnostics(config)
        imap_message = results[0][1]
        self.assertNotIn("test-secret", imap_message)
        self.assertNotIn("source@example.test", imap_message)
        self.assertIn("***", imap_message)

    def test_backup_contains_only_state_and_manifest_with_correct_hash(self):
        self.legacy.write_text('["1", "2"]', encoding="utf-8")
        self.call_init()
        self.paths.secrets.unlink()  # 备份不需要读取授权码
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(mailctl.cmd_backup(SimpleNamespace(), self.paths), 0)
        archives = list(self.paths.backups.glob("mailctl-*.tar.gz"))
        self.assertEqual(len(archives), 1)
        archive_path = archives[0]
        self.assertEqual(archive_path.stat().st_mode & 0o777, 0o600)
        with tarfile.open(archive_path, "r:gz") as archive:
            self.assertEqual(set(archive.getnames()), {"forwarded_uids.json", "manifest.json"})
            state = archive.extractfile("forwarded_uids.json").read()
            manifest = json.loads(archive.extractfile("manifest.json").read())
        self.assertEqual(manifest["uid_count"], 2)
        self.assertEqual(manifest["state_sha256"], hashlib.sha256(state).hexdigest())
        self.assertNotIn(b"test-secret", state)
        self.assertNotIn(b"test-secret", json.dumps(manifest).encode())

    def test_backup_retention_only_prunes_mailctl_archives(self):
        self.call_init()
        config = json.loads(self.paths.config.read_text())
        config["backup_keep"] = 2
        self.paths.config.write_text(json.dumps(config), encoding="utf-8")
        for name in ("mailctl-20000101-000000.tar.gz", "mailctl-20000102-000000.tar.gz"):
            (self.paths.backups / name).write_bytes(b"old")
        unrelated = self.paths.backups / "other.tar.gz"
        unrelated.write_bytes(b"keep")
        with contextlib.redirect_stdout(io.StringIO()):
            mailctl.cmd_backup(SimpleNamespace(), self.paths)
        self.assertEqual(len(list(self.paths.backups.glob("mailctl-*.tar.gz"))), 2)
        self.assertTrue(unrelated.exists())

    def test_backup_refuses_corrupt_state(self):
        self.call_init()
        self.paths.uid_state.write_text("broken", encoding="utf-8")
        with self.assertRaises(mailctl.MailctlError):
            mailctl.cmd_backup(SimpleNamespace(), self.paths)
        self.assertEqual(list(self.paths.backups.glob("mailctl-*.tar.gz")), [])


class CommandLineTests(unittest.TestCase):
    def test_offline_cli_workflow_and_duplicate_init(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = root / "config" / "mailctl" / "config.json"
            state = root / "state" / "mailctl"
            env = os.environ.copy()
            env["MAILCTL_PASSWORD"] = "cli-test-secret"
            base = [
                sys.executable,
                str(MAILCTL_PATH),
                "--config",
                str(config),
                "--state-dir",
                str(state),
            ]
            init_command = base + [
                "init",
                "--account",
                "source@example.test",
                "--target",
                "target@example.test",
                "--imap-host",
                "imap.example.test",
                "--smtp-host",
                "smtp.example.test",
                "--legacy-state",
                str(root / "missing-legacy.json"),
            ]
            initialized = subprocess.run(init_command, env=env, text=True, capture_output=True)
            self.assertEqual(initialized.returncode, 0, initialized.stderr)
            self.assertNotIn("cli-test-secret", initialized.stdout + initialized.stderr)

            doctor = subprocess.run(base + ["doctor"], env=env, text=True, capture_output=True)
            self.assertEqual(doctor.returncode, 0, doctor.stderr)

            status = subprocess.run(base + ["status"], env=env, text=True, capture_output=True)
            self.assertEqual(status.returncode, 1)
            self.assertIn("尚未安装", status.stdout)

            before = config.read_bytes()
            duplicate = subprocess.run(init_command, env=env, text=True, capture_output=True)
            self.assertEqual(duplicate.returncode, 1)
            self.assertEqual(config.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
