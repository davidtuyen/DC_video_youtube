import unittest
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PyQt5.QtWidgets import QMessageBox

from ui_script import MainWindow


class CookieDownloadConfirmationTests(unittest.TestCase):
    def _window(self, settings):
        return SimpleNamespace(settings=settings, log_to_gui=Mock())

    def _confirm(self, window, tasks):
        return MainWindow._confirm_cookie_mode_for_downloads(window, tasks)

    def test_browser_cookie_mode_asks_once_with_yes_as_default(self):
        window = self._window({
            "use_cookies": False,
            "cookies_from_browser": "edge",
            "extracted_cookies_path": "",
        })
        tasks = [
            {"url": "https://www.youtube.com/watch?v=one", "type": "youtube_video"},
            {"url": "https://www.youtube.com/watch?v=two", "type": "youtube_video"},
        ]

        with patch.object(QMessageBox, "question", return_value=QMessageBox.Yes) as question:
            confirmed = self._confirm(window, tasks)

        self.assertTrue(confirmed)
        question.assert_called_once()
        args = question.call_args.args
        self.assertEqual(args[4], QMessageBox.Yes)
        self.assertIn("toàn bộ 2 URL", args[2])
        self.assertIn("Edge", args[2])

    def test_no_cancels_the_entire_batch(self):
        window = self._window({
            "use_cookies": True,
            "cookies_file_path": r"C:\cookies\youtube.txt",
            "cookies_from_browser": "",
        })
        tasks = [{"url": "https://youtu.be/example", "type": "youtube_video"}]

        with patch.object(QMessageBox, "question", return_value=QMessageBox.No):
            confirmed = self._confirm(window, tasks)

        self.assertFalse(confirmed)
        window.log_to_gui.assert_called_once()

    def test_rejected_confirmation_adds_no_download_tasks(self):
        with TemporaryDirectory() as download_dir:
            window = SimpleNamespace(
                yt_dlp_path="yt-dlp.exe",
                current_download_dir=download_dir,
                log_to_gui=Mock(),
                _confirm_cookie_mode_for_downloads=Mock(return_value=False),
                _add_task_to_model_and_queue=Mock(),
            )

            MainWindow._prepare_downloads_from_text(
                window,
                "https://youtu.be/first\nhttps://youtu.be/second",
            )

        window._confirm_cookie_mode_for_downloads.assert_called_once()
        window._add_task_to_model_and_queue.assert_not_called()

    def test_no_prompt_when_cookie_mode_is_off(self):
        window = self._window({"use_cookies": False, "cookies_from_browser": ""})
        tasks = [{"url": "https://youtu.be/example", "type": "youtube_video"}]

        with patch.object(QMessageBox, "question") as question:
            confirmed = self._confirm(window, tasks)

        self.assertTrue(confirmed)
        question.assert_not_called()

    def test_no_prompt_for_drive_only_batch(self):
        window = self._window({"use_cookies": True, "cookies_file_path": "cookies.txt"})
        tasks = [{"url": "https://drive.google.com/file/d/id/view", "type": "drive"}]

        with patch.object(QMessageBox, "question") as question:
            confirmed = self._confirm(window, tasks)

        self.assertTrue(confirmed)
        question.assert_not_called()


if __name__ == "__main__":
    unittest.main()
