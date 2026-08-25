import inspect
import unittest
from unittest.mock import Mock

from workers import (
    DownloadWorker,
    YoutubeAccessMode,
    YoutubeFailureKind,
    build_youtube_access_args,
    classify_youtube_failure,
    next_youtube_access_mode,
)


class YoutubeFailureClassificationTests(unittest.TestCase):
    def test_workspace_restriction_is_not_misclassified_as_generic_unavailable(self):
        details = (
            "ERROR: [youtube] id: Video unavailable. This video is restricted. "
            "Please check the Google Workspace administrator and/or the network "
            "administrator restrictions."
        )

        self.assertEqual(
            classify_youtube_failure(details),
            YoutubeFailureKind.WORKSPACE_RESTRICTED,
        )

    def test_private_removed_and_copyright_failures_are_permanent(self):
        messages = (
            "ERROR: Private video. Sign in if you've been granted access",
            "ERROR: This video has been removed by the uploader",
            "ERROR: This video is no longer available due to a copyright claim",
        )

        for message in messages:
            with self.subTest(message=message):
                self.assertEqual(
                    classify_youtube_failure(message),
                    YoutubeFailureKind.PERMANENT,
                )

    def test_network_failure_is_not_an_access_failure(self):
        self.assertEqual(
            classify_youtube_failure("ERROR: Unable to download webpage: timed out"),
            YoutubeFailureKind.OTHER,
        )

    def test_bot_challenge_is_an_access_failure(self):
        self.assertEqual(
            classify_youtube_failure(
                "ERROR: Sign in to confirm you're not a bot. Use --cookies-from-browser"
            ),
            YoutubeFailureKind.WORKSPACE_RESTRICTED,
        )


class YoutubeFallbackRoutingTests(unittest.TestCase):
    def test_workspace_failure_before_transfer_retries_clean_anonymous(self):
        self.assertEqual(
            next_youtube_access_mode(
                YoutubeAccessMode.NORMAL_NO_COOKIE,
                YoutubeFailureKind.WORKSPACE_RESTRICTED,
                transfer_started=False,
                cookies_available=True,
            ),
            YoutubeAccessMode.CLEAN_ANONYMOUS,
        )

    def test_failure_after_transfer_started_never_switches_access_mode(self):
        self.assertIsNone(
            next_youtube_access_mode(
                YoutubeAccessMode.NORMAL_NO_COOKIE,
                YoutubeFailureKind.WORKSPACE_RESTRICTED,
                transfer_started=True,
                cookies_available=True,
            )
        )

    def test_clean_anonymous_failure_uses_cookie_once_when_available(self):
        self.assertEqual(
            next_youtube_access_mode(
                YoutubeAccessMode.CLEAN_ANONYMOUS,
                YoutubeFailureKind.OTHER,
                transfer_started=False,
                cookies_available=True,
            ),
            YoutubeAccessMode.COOKIE,
        )

    def test_permanent_failure_stops_in_every_mode(self):
        for mode in YoutubeAccessMode:
            with self.subTest(mode=mode):
                self.assertIsNone(
                    next_youtube_access_mode(
                        mode,
                        YoutubeFailureKind.PERMANENT,
                        transfer_started=False,
                        cookies_available=True,
                    )
                )

    def test_clean_anonymous_failure_stops_without_configured_cookie(self):
        self.assertIsNone(
            next_youtube_access_mode(
                YoutubeAccessMode.CLEAN_ANONYMOUS,
                YoutubeFailureKind.OTHER,
                transfer_started=False,
                cookies_available=False,
            )
        )

    def test_cookie_attempt_never_retries(self):
        self.assertIsNone(
            next_youtube_access_mode(
                YoutubeAccessMode.COOKIE,
                YoutubeFailureKind.WORKSPACE_RESTRICTED,
                transfer_started=False,
                cookies_available=True,
            )
        )


class YoutubeAccessArgumentTests(unittest.TestCase):
    def test_normal_mode_explicitly_disables_all_cookie_sources(self):
        args = build_youtube_access_args(
            YoutubeAccessMode.NORMAL_NO_COOKIE,
            use_cookies=True,
            cookies_file_path=r"C:\cookies\youtube.txt",
            cookies_from_browser="edge",
        )

        self.assertIn("--no-cookies", args)
        self.assertIn("--no-cookies-from-browser", args)
        self.assertNotIn("--ignore-config", args)
        self.assertNotIn("--cookies", args)
        self.assertNotIn("--cookies-from-browser", args)

    def test_clean_anonymous_mode_ignores_config_and_disables_cookies(self):
        args = build_youtube_access_args(
            YoutubeAccessMode.CLEAN_ANONYMOUS,
            use_cookies=True,
            cookies_file_path=r"C:\cookies\youtube.txt",
            cookies_from_browser="edge",
        )

        self.assertIn("--ignore-config", args)
        self.assertIn("--no-cookies", args)
        self.assertIn("--no-cookies-from-browser", args)

    def test_cookie_mode_prefers_valid_cookie_file(self):
        args = build_youtube_access_args(
            YoutubeAccessMode.COOKIE,
            use_cookies=True,
            cookies_file_path=__file__,
            cookies_from_browser="edge",
        )

        self.assertEqual(args, ["--cookies", __file__])

    def test_browser_cookie_mode_preserves_exact_profile_directory(self):
        args = build_youtube_access_args(
            YoutubeAccessMode.COOKIE,
            use_cookies=False,
            cookies_file_path="",
            cookies_from_browser="chrome:Profile 66",
        )

        self.assertEqual(args, ["--cookies-from-browser", "chrome:Profile 66"])


class YoutubeTransferBoundaryTests(unittest.TestCase):
    def _worker(self):
        return DownloadWorker(
            "task-test",
            "https://www.youtube.com/watch?v=test",
            "best",
            ".",
            "yt-dlp.exe",
            False,
            False,
            "",
            1,
            False,
            "",
            False,
        )

    def test_destination_marks_transfer_as_started(self):
        worker = self._worker()

        worker._parse_yt_dlp_output('[download] Destination: example.mp4')

        self.assertTrue(worker.transfer_started)

    def test_progress_marks_transfer_as_started(self):
        worker = self._worker()

        worker._parse_yt_dlp_output(
            "[download]   1.0% of 10.00MiB at 1.00MiB/s ETA 00:09"
        )

        self.assertTrue(worker.transfer_started)


class YoutubeAttemptSequenceTests(unittest.TestCase):
    def _worker(self, *, cookie_file="", browser=""):
        return DownloadWorker(
            "task-test",
            "https://www.youtube.com/watch?v=test",
            "best",
            ".",
            "yt-dlp.exe",
            False,
            False,
            "",
            1,
            bool(cookie_file),
            cookie_file,
            False,
            cookies_from_browser=browser,
        )

    def test_workspace_then_clean_success_uses_two_fresh_attempts(self):
        worker = self._worker(cookie_file=__file__)
        worker._execute_yt_dlp_command = Mock(side_effect=[
            (1, "This video is restricted by a Google Workspace administrator"),
            (0, "download complete"),
        ])

        return_code, details = worker._run_access_attempts(
            ["yt-dlp.exe", "--no-playlist", worker.url]
        )

        self.assertEqual(return_code, 0)
        self.assertEqual(details, "download complete")
        self.assertEqual(worker._execute_yt_dlp_command.call_count, 2)
        first = worker._execute_yt_dlp_command.call_args_list[0].args[0]
        second = worker._execute_yt_dlp_command.call_args_list[1].args[0]
        self.assertIn("--no-cookies", first)
        self.assertNotIn("--ignore-config", first)
        self.assertIn("--ignore-config", second)
        self.assertNotIn("--cookies", second)

    def test_clean_failure_uses_cookie_only_once(self):
        worker = self._worker(cookie_file=__file__)
        worker._execute_yt_dlp_command = Mock(side_effect=[
            (1, "This video is restricted by a Google Workspace administrator"),
            (1, "Video unavailable"),
            (1, "Sign in required"),
        ])

        return_code, _details = worker._run_access_attempts(
            ["yt-dlp.exe", worker.url]
        )

        self.assertEqual(return_code, 1)
        self.assertEqual(worker._execute_yt_dlp_command.call_count, 3)
        cookie_attempt = worker._execute_yt_dlp_command.call_args_list[2].args[0]
        self.assertIn("--cookies", cookie_attempt)
        self.assertEqual(cookie_attempt.count("--cookies"), 1)

    def test_transfer_started_during_first_attempt_prevents_fallback(self):
        worker = self._worker(cookie_file=__file__)

        def fail_after_transfer(_command):
            worker.transfer_started = True
            return 1, "This video is restricted by a Google Workspace administrator"

        worker._execute_yt_dlp_command = Mock(side_effect=fail_after_transfer)

        return_code, _details = worker._run_access_attempts(
            ["yt-dlp.exe", worker.url]
        )

        self.assertEqual(return_code, 1)
        worker._execute_yt_dlp_command.assert_called_once()

    def test_bot_challenge_falls_back_to_local_browser_cookie_once(self):
        worker = self._worker(browser="edge")
        worker._execute_yt_dlp_command = Mock(side_effect=[
            (1, "Sign in to confirm you're not a bot"),
            (1, "Sign in to confirm you're not a bot"),
            (0, "download complete"),
        ])

        return_code, _details = worker._run_access_attempts(
            ["yt-dlp.exe", worker.url]
        )

        self.assertEqual(return_code, 0)
        commands = [call.args[0] for call in worker._execute_yt_dlp_command.call_args_list]
        self.assertEqual(len(commands), 3)
        self.assertIn("--ignore-config", commands[1])
        self.assertEqual(commands[2][1:3], ["--cookies-from-browser", "edge"])

    def test_command_log_does_not_expose_proxy_credentials(self):
        worker = self._worker()
        messages = []
        worker.log_message.connect(lambda _task_id, message: messages.append(message))
        worker._execute_yt_dlp_command = Mock(return_value=(0, "done"))

        worker._run_access_attempts([
            "yt-dlp.exe",
            "--proxy",
            "http://alice:super-secret@example.test:8080",
            worker.url,
        ])

        log_text = "\n".join(messages)
        self.assertNotIn("alice", log_text)
        self.assertNotIn("super-secret", log_text)

    def test_download_command_keeps_tls_certificate_validation_enabled(self):
        source = inspect.getsource(DownloadWorker.run)

        self.assertNotIn("--no-check-certificate", source)

if __name__ == "__main__":
    unittest.main()
