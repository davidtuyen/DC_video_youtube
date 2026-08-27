import base64
import hashlib
import json
import os
import sqlite3
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock


class ManagedChromeTests(unittest.TestCase):
    def setUp(self):
        try:
            import managed_chrome
        except ModuleNotFoundError:
            self.fail("managed_chrome module is required")
        self.module = managed_chrome

    def _session(self, root, **kwargs):
        return self.module.ManagedChromeSession(Path(root) / "data" / "browser", **kwargs)

    def _create_cookie_database(
        self,
        profile_dir,
        *,
        name="LOGIN_INFO",
        domain=".youtube.com",
        value="",
        encrypted_value=b"v10-encrypted",
        expires=None,
    ):
        database = Path(profile_dir) / "Network" / "Cookies"
        database.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(database)
        try:
            connection.execute(
                "CREATE TABLE cookies ("
                "host_key TEXT, name TEXT, expires_utc INTEGER, "
                "value TEXT, encrypted_value BLOB)"
            )
            webkit_expiry = expires
            if webkit_expiry is None:
                webkit_expiry = int((time.time() + 11644473600 + 3600) * 1_000_000)
            connection.execute(
                "INSERT INTO cookies VALUES (?, ?, ?, ?, ?)",
                (domain, name, webkit_expiry, value, encrypted_value),
            )
            connection.commit()
        finally:
            connection.close()

    def test_paths_and_launch_arguments_use_only_app_owned_profile(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = self._session(temp_dir, chrome_path=r"C:\Chrome\chrome.exe")

            arguments = session.build_launch_arguments("https://www.youtube.com/")

            self.assertEqual(
                session.profile_dir,
                Path(temp_dir) / "data" / "browser" / "chrome-user-data" / "Default",
            )
            self.assertIn(
                f"--user-data-dir={session.user_data_dir}",
                arguments,
            )
            self.assertIn("--profile-directory=Default", arguments)
            self.assertIn("--remote-debugging-address=127.0.0.1", arguments)
            self.assertIn("--remote-debugging-port=0", arguments)
            personal_profile = (
                Path.home()
                / "AppData"
                / "Local"
                / "Google"
                / "Chrome"
                / "User Data"
            )
            self.assertNotIn(str(personal_profile), " ".join(arguments))

    def test_unauthenticated_login_launch_has_no_remote_debugging_flags(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = self._session(temp_dir, chrome_path=r"C:\Chrome\chrome.exe")
            process = mock.Mock()
            process.poll.return_value = None
            with mock.patch.object(
                session, "_active_websocket_url", return_value=""
            ), mock.patch.object(
                session, "_profile_has_login_cookie_record", return_value=False
            ), mock.patch.object(
                self.module.subprocess, "Popen", return_value=process
            ) as popen, mock.patch.object(
                session, "_wait_for_active_websocket"
            ) as wait_for_cdp:
                result = session.open_browser()

            arguments = popen.call_args.args[0]
            self.assertTrue(result.success)
            self.assertNotIn("--remote-debugging-address=127.0.0.1", arguments)
            self.assertNotIn("--remote-debugging-port=0", arguments)
            self.assertEqual(arguments[-1], self.module.YOUTUBE_LOGIN_URL)
            wait_for_cdp.assert_not_called()

    def test_running_login_browser_is_reused_without_starting_cdp_process(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = self._session(temp_dir, chrome_path=r"C:\Chrome\chrome.exe")
            session._process = mock.Mock()
            session._process.poll.return_value = None
            with mock.patch.object(
                session, "_active_websocket_url", return_value=""
            ), mock.patch.object(self.module.subprocess, "Popen") as popen:
                result = session.open_browser()

            self.assertTrue(result.success)
            self.assertTrue(result.reused)
            self.assertIn("đang mở", result.message.casefold())
            popen.assert_not_called()

    def test_constructor_removes_plaintext_files_left_by_crash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            browser_root = Path(temp_dir) / "data" / "browser"
            browser_root.mkdir(parents=True)
            snapshot = browser_root / "session-cookies.txt"
            snapshot.write_text("stale plaintext", encoding="utf-8")
            staged_snapshot = browser_root / ".session-cookies.txt.crash.tmp"
            staged_snapshot.write_text("staged plaintext", encoding="utf-8")
            lease_dir = browser_root / "cookie-leases"
            lease_dir.mkdir()
            stale_lease = lease_dir / "old-task.txt"
            stale_lease.write_text("leased plaintext", encoding="utf-8")
            staged_lease = lease_dir / ".old-task.txt.crash.tmp"
            staged_lease.write_text("staged lease", encoding="utf-8")

            session = self.module.ManagedChromeSession(
                browser_root,
                chrome_path=r"C:\Chrome\chrome.exe",
            )

            self.assertFalse(session.snapshot_path.exists())
            self.assertFalse(staged_snapshot.exists())
            self.assertFalse(stale_lease.exists())
            self.assertFalse(staged_lease.exists())

    def test_finder_uses_program_files_then_local_app_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            local_chrome = root / "Local" / "Google" / "Chrome" / "Application" / "chrome.exe"
            local_chrome.parent.mkdir(parents=True)
            local_chrome.write_bytes(b"exe")

            found = self.module.find_chrome_executable({
                "PROGRAMFILES": str(root / "ProgramFiles"),
                "PROGRAMFILES(X86)": str(root / "ProgramFilesX86"),
                "LOCALAPPDATA": str(root / "Local"),
            })

            self.assertEqual(found, local_chrome)

    def test_finder_reports_missing_chrome(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            with self.assertRaises(self.module.ManagedChromeError):
                self.module.find_chrome_executable({
                    "PROGRAMFILES": temp_dir,
                    "PROGRAMFILES(X86)": temp_dir,
                    "LOCALAPPDATA": temp_dir,
                })

    def test_finder_never_executes_path_shadowed_chrome(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            fake = Path(temp_dir) / "chrome.exe"
            fake.write_bytes(b"not google chrome")
            with mock.patch.dict(
                os.environ,
                {
                    "PROGRAMFILES": temp_dir,
                    "PROGRAMFILES(X86)": temp_dir,
                    "LOCALAPPDATA": temp_dir,
                },
                clear=True,
            ), mock.patch("shutil.which", return_value=str(fake)):
                with self.assertRaises(self.module.ManagedChromeError):
                    self.module.find_chrome_executable()

    def test_visitor_only_snapshot_is_rejected_without_overwriting_old_file(self):
        visitor = [{
            "domain": ".youtube.com",
            "path": "/",
            "secure": True,
            "expires": time.time() + 3600,
            "name": "PREF",
            "value": "visitor",
        }]
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "session-cookies.txt"
            output.write_text("old-valid-snapshot", encoding="utf-8")

            with self.assertRaises(self.module.ManagedChromeError):
                self.module.write_authenticated_snapshot(visitor, output)

            self.assertEqual(output.read_text(encoding="utf-8"), "old-valid-snapshot")

    def test_authenticated_snapshot_is_netscape_and_atomic(self):
        cookies = [{
            "domain": ".youtube.com",
            "path": "/",
            "secure": True,
            "httpOnly": True,
            "expires": time.time() + 3600,
            "name": "LOGIN_INFO",
            "value": "login-value",
        }]
        with tempfile.TemporaryDirectory() as temp_dir:
            output = Path(temp_dir) / "session-cookies.txt"

            count = self.module.write_authenticated_snapshot(cookies, output)

            self.assertEqual(count, 1)
            content = output.read_text(encoding="utf-8")
            self.assertIn("#HttpOnly_.youtube.com", content)
            self.assertIn("\tLOGIN_INFO\tlogin-value", content)
            self.assertEqual(list(output.parent.glob("*.tmp")), [])

    def test_closed_profile_with_live_auth_cookie_returns_direct_browser_spec(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = self._session(temp_dir, chrome_path=r"C:\Chrome\chrome.exe")
            self._create_cookie_database(session.profile_dir)
            with mock.patch.object(session, "_active_websocket_url", return_value=""):
                source = session.resolve_cookie_source()

            self.assertFalse(source.use_cookie_file)
            self.assertEqual(
                source.browser_spec,
                f"chrome:{session.profile_dir.resolve()}",
            )

    def test_login_browser_must_close_before_cookie_source_is_used(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = self._session(temp_dir, chrome_path=r"C:\Chrome\chrome.exe")
            self._create_cookie_database(session.profile_dir)
            session._process = mock.Mock()
            session._process.poll.return_value = None
            with mock.patch.object(session, "_active_websocket_url", return_value=""):
                source = session.resolve_cookie_source()

            self.assertEqual(source, self.module.DownloadCookieSource())
            self.assertIn("đóng Chrome", session.last_error)

    def test_closed_profile_rejects_spoofed_domain_and_empty_cookie_record(self):
        cases = (
            {"domain": ".notyoutube.com"},
            {"domain": ".youtube.com", "value": "", "encrypted_value": b""},
        )
        for cookie in cases:
            with self.subTest(cookie=cookie), tempfile.TemporaryDirectory() as temp_dir:
                session = self._session(temp_dir, chrome_path=r"C:\Chrome\chrome.exe")
                self._create_cookie_database(session.profile_dir, **cookie)
                with mock.patch.object(session, "_active_websocket_url", return_value=""):
                    source = session.resolve_cookie_source()

                self.assertFalse(source.use_cookie_file)
                self.assertFalse(source.browser_spec)

    def test_login_status_uses_cdp_for_running_authenticated_browser_without_snapshot(self):
        auth_cookie = {
            "domain": ".youtube.com",
            "name": "LOGIN_INFO",
            "value": "authenticated",
            "expires": time.time() + 3600,
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            session = self._session(temp_dir, chrome_path=r"C:\Chrome\chrome.exe")
            websocket_url = "ws://127.0.0.1:9222/devtools/browser/id"
            with mock.patch.object(
                session, "_active_websocket_url", return_value=websocket_url
            ), mock.patch.object(
                self.module,
                "cdp_command",
                return_value={"result": {"cookies": [auth_cookie]}},
            ) as command:
                status = session.check_login_status()

            self.assertEqual(status.state, "authenticated")
            self.assertTrue(status.browser_running)
            self.assertIn("đăng nhập", status.message.casefold())
            self.assertFalse(session.snapshot_path.exists())
            command.assert_called_once_with(websocket_url, "Storage.getCookies")

    def test_login_status_rejects_visitor_and_expired_cookies(self):
        visitor_cookie = {
            "domain": ".youtube.com",
            "name": "PREF",
            "value": "visitor",
            "expires": time.time() + 3600,
        }
        expired_auth_cookie = {
            "domain": ".youtube.com",
            "name": "LOGIN_INFO",
            "value": "expired",
            "expires": time.time() - 1,
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            session = self._session(temp_dir, chrome_path=r"C:\Chrome\chrome.exe")
            with mock.patch.object(
                session,
                "_active_websocket_url",
                return_value="ws://127.0.0.1:9222/devtools/browser/id",
            ), mock.patch.object(
                self.module,
                "cdp_command",
                return_value={
                    "result": {"cookies": [visitor_cookie, expired_auth_cookie]}
                },
            ):
                status = session.check_login_status()

            self.assertEqual(status.state, "not_authenticated")
            self.assertTrue(status.browser_running)
            self.assertFalse(session.snapshot_path.exists())

    def test_login_status_uses_profile_database_only_when_browser_is_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = self._session(temp_dir, chrome_path=r"C:\Chrome\chrome.exe")
            self._create_cookie_database(session.profile_dir)
            with mock.patch.object(
                session, "_active_websocket_url", return_value=""
            ), mock.patch.object(self.module, "cdp_command") as command:
                status = session.check_login_status()

            self.assertEqual(status.state, "authenticated")
            self.assertFalse(status.browser_running)
            command.assert_not_called()
            self.assertFalse(session.snapshot_path.exists())

    def test_login_status_explains_that_non_cdp_browser_must_be_closed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = self._session(temp_dir, chrome_path=r"C:\Chrome\chrome.exe")
            session._process = mock.Mock()
            session._process.poll.return_value = None
            with mock.patch.object(
                session, "_active_websocket_url", return_value=""
            ), mock.patch.object(
                session, "_profile_has_login_cookie_record", return_value=False
            ):
                status = session.check_login_status()

            self.assertEqual(status.state, "not_authenticated")
            self.assertTrue(status.browser_running)
            self.assertIn("đóng Chrome", status.message)

    def test_login_status_reports_cdp_failure_and_missing_chrome(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = self._session(temp_dir, chrome_path=r"C:\Chrome\chrome.exe")
            with mock.patch.object(
                session,
                "_active_websocket_url",
                return_value="ws://127.0.0.1:9222/devtools/browser/id",
            ), mock.patch.object(
                self.module,
                "cdp_command",
                side_effect=self.module.ManagedChromeError("CDP unavailable"),
            ):
                status = session.check_login_status()

            self.assertEqual(status.state, "unavailable")
            self.assertTrue(status.browser_running)
            self.assertIn("CDP unavailable", status.message)

        with tempfile.TemporaryDirectory() as temp_dir:
            session = self._session(temp_dir)
            with mock.patch.object(
                session, "_active_websocket_url", return_value=""
            ), mock.patch.object(
                self.module,
                "find_chrome_executable",
                side_effect=self.module.ManagedChromeError("Chrome missing"),
            ):
                status = session.check_login_status()

            self.assertEqual(status.state, "unavailable")
            self.assertFalse(status.browser_running)
            self.assertIn("Chrome missing", status.message)

    def test_live_profile_exports_cdp_snapshot_for_locked_database(self):
        cookies = [{
            "domain": ".google.com",
            "path": "/",
            "secure": True,
            "expires": time.time() + 3600,
            "name": "SAPISID",
            "value": "secret",
        }]
        with tempfile.TemporaryDirectory() as temp_dir:
            session = self._session(temp_dir, chrome_path=r"C:\Chrome\chrome.exe")
            with mock.patch.object(
                session, "_active_websocket_url", return_value="ws://127.0.0.1:9222/devtools/browser/id"
            ), mock.patch.object(
                self.module, "cdp_command", return_value={"result": {"cookies": cookies}}
            ):
                source = session.resolve_cookie_source()

            self.assertTrue(source.use_cookie_file)
            self.assertEqual(source.cookie_file_path, str(session.snapshot_path))
            self.assertTrue(session.snapshot_path.is_file())

    def test_live_profile_creates_immutable_cookie_lease_per_task(self):
        def auth_cookie(value):
            return {
                "domain": ".youtube.com",
                "path": "/",
                "secure": True,
                "expires": time.time() + 3600,
                "name": "LOGIN_INFO",
                "value": value,
            }

        with tempfile.TemporaryDirectory() as temp_dir:
            session = self._session(temp_dir, chrome_path=r"C:\Chrome\chrome.exe")
            with mock.patch.object(
                session,
                "_active_websocket_url",
                return_value="ws://127.0.0.1:9222/devtools/browser/id",
            ), mock.patch.object(
                self.module,
                "cdp_command",
                side_effect=[
                    {"result": {"cookies": [auth_cookie("account-a")]}},
                    {"result": {"cookies": [auth_cookie("account-b")]}},
                ],
            ):
                first = session.resolve_cookie_source(lease_id="task-a")
                second = session.resolve_cookie_source(lease_id="task-b")

            self.assertNotEqual(first.cookie_file_path, second.cookie_file_path)
            self.assertIn("account-a", Path(first.cookie_file_path).read_text(encoding="utf-8"))
            self.assertNotIn("account-b", Path(first.cookie_file_path).read_text(encoding="utf-8"))
            session.release_cookie_source(first)
            self.assertFalse(Path(first.cookie_file_path).exists())
            self.assertTrue(Path(second.cookie_file_path).exists())

    def test_failed_lease_refresh_does_not_leave_old_credentials(self):
        auth = {
            "domain": ".youtube.com",
            "path": "/",
            "secure": True,
            "expires": time.time() + 3600,
            "name": "LOGIN_INFO",
            "value": "old-account",
        }
        visitor = {**auth, "name": "PREF", "value": "visitor"}
        with tempfile.TemporaryDirectory() as temp_dir:
            session = self._session(temp_dir, chrome_path=r"C:\Chrome\chrome.exe")
            with mock.patch.object(
                session,
                "_active_websocket_url",
                return_value="ws://127.0.0.1:9222/devtools/browser/id",
            ), mock.patch.object(
                self.module,
                "cdp_command",
                side_effect=[
                    {"result": {"cookies": [auth]}},
                    {"result": {"cookies": [visitor]}},
                ],
            ):
                first = session.resolve_cookie_source(lease_id="same-task")
                failed = session.resolve_cookie_source(lease_id="same-task")

            self.assertTrue(first.cookie_file_path)
            self.assertFalse(failed.use_cookie_file)
            self.assertFalse(Path(first.cookie_file_path).exists())

    def test_reuse_creates_target_without_starting_another_process(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = self._session(temp_dir, chrome_path=r"C:\Chrome\chrome.exe")
            websocket_url = "ws://127.0.0.1:9222/devtools/browser/id"
            with mock.patch.object(session, "_active_websocket_url", return_value=websocket_url), \
                    mock.patch.object(
                        self.module,
                        "cdp_command",
                        side_effect=[
                            {"result": {"cookies": []}},
                            {"result": {"targetId": "new"}},
                        ],
                    ) as command, \
                    mock.patch.object(self.module.subprocess, "Popen") as popen:
                result = session.open_browser()

            self.assertTrue(result.success)
            self.assertTrue(result.reused)
            self.assertEqual(
                command.call_args_list,
                [
                    mock.call(websocket_url, "Storage.getCookies"),
                    mock.call(
                        websocket_url,
                        "Target.createTarget",
                        {"url": self.module.YOUTUBE_LOGIN_URL},
                    ),
                ],
            )
            popen.assert_not_called()

    def test_reused_logged_in_browser_opens_youtube_home(self):
        auth_cookie = {
            "domain": ".youtube.com",
            "name": "LOGIN_INFO",
            "value": "authenticated",
            "expires": time.time() + 3600,
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            session = self._session(temp_dir, chrome_path=r"C:\Chrome\chrome.exe")
            websocket_url = "ws://127.0.0.1:9222/devtools/browser/id"
            with mock.patch.object(
                session, "_active_websocket_url", return_value=websocket_url
            ), mock.patch.object(
                self.module,
                "cdp_command",
                side_effect=[
                    {"result": {"cookies": [auth_cookie]}},
                    {"result": {"targetId": "new"}},
                ],
            ) as command:
                result = session.open_browser()

            self.assertTrue(result.success)
            self.assertEqual(
                command.call_args_list[-1],
                mock.call(
                    websocket_url,
                    "Target.createTarget",
                    {"url": self.module.YOUTUBE_HOME_URL},
                ),
            )

    def test_fresh_launch_waits_for_cdp_before_reporting_success(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = self._session(temp_dir, chrome_path=r"C:\Chrome\chrome.exe")
            process = mock.Mock()
            process.poll.return_value = None
            websocket_url = "ws://127.0.0.1:9222/devtools/browser/id"
            with mock.patch.object(
                session,
                "_active_websocket_url",
                side_effect=["", websocket_url],
            ) as active_endpoint, mock.patch.object(
                session,
                "_profile_has_login_cookie_record",
                return_value=True,
            ), mock.patch.object(
                self.module.subprocess,
                "Popen",
                return_value=process,
            ), mock.patch.object(self.module.time, "sleep"):
                result = session.open_browser()

            self.assertTrue(result.success)
            self.assertFalse(result.reused)
            self.assertEqual(active_endpoint.call_count, 2)

    def test_profile_lock_or_early_chrome_exit_is_reported_as_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = self._session(temp_dir, chrome_path=r"C:\Chrome\chrome.exe")
            process = mock.Mock()
            process.poll.return_value = 21
            with mock.patch.object(
                session,
                "_active_websocket_url",
                return_value="",
            ), mock.patch.object(
                self.module.subprocess,
                "Popen",
                return_value=process,
            ):
                result = session.open_browser()

            self.assertFalse(result.success)
            self.assertIn("profile", result.message.casefold())

    def test_process_cleanup_error_never_crashes_the_app(self):
        process = mock.Mock()
        process.poll.return_value = None
        process.terminate.side_effect = OSError("access denied")

        self.module.ManagedChromeSession._stop_exact_process(process)

    def test_shutdown_closes_only_cdp_browser_and_removes_snapshot(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            session = self._session(temp_dir, chrome_path=r"C:\Chrome\chrome.exe")
            session.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            session.snapshot_path.write_text("secret", encoding="utf-8")
            websocket_url = "ws://127.0.0.1:9222/devtools/browser/id"
            with mock.patch.object(session, "_active_websocket_url", return_value=websocket_url), \
                    mock.patch.object(self.module, "cdp_command", return_value={}) as command, \
                    mock.patch.object(self.module.subprocess, "run") as run:
                session.shutdown()

            command.assert_called_once_with(
                websocket_url,
                "Browser.close",
                allow_disconnect=True,
            )
            run.assert_not_called()
            self.assertFalse(session.snapshot_path.exists())

    def test_cdp_rejects_non_loopback_websocket_url(self):
        with self.assertRaises(self.module.ManagedChromeError):
            self.module.cdp_command(
                "ws://192.0.2.1:9222/devtools/browser/id",
                "Storage.getCookies",
            )

    def test_cdp_matches_response_id_and_validates_handshake(self):
        random_bytes = b"x" * 16
        key = base64.b64encode(random_bytes).decode("ascii")
        accept = base64.b64encode(hashlib.sha1(
            (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")
        ).digest()).decode("ascii")
        event = json.dumps({"method": "Network.event"}).encode()
        response = json.dumps({"id": 1, "result": {"cookies": []}}).encode()
        incoming = bytearray(
            f"HTTP/1.1 101 Switching Protocols\r\n"
            f"Sec-WebSocket-Accept: {accept}\r\n\r\n".encode("ascii")
        )
        for payload in (event, response):
            incoming.extend(bytes([0x81, len(payload)]))
            incoming.extend(payload)

        class FakeSocket:
            def settimeout(self, _timeout):
                pass

            def sendall(self, _data):
                pass

            def recv(self, size):
                data = bytes(incoming[:size])
                del incoming[:size]
                return data

            def close(self):
                pass

        with mock.patch.object(
            self.module.socket, "create_connection", return_value=FakeSocket()
        ), mock.patch.object(self.module.os, "urandom", return_value=random_bytes):
            result = self.module.cdp_command(
                "ws://127.0.0.1:9222/devtools/browser/id",
                "Storage.getCookies",
            )

        self.assertEqual(result["result"]["cookies"], [])


if __name__ == "__main__":
    unittest.main()
