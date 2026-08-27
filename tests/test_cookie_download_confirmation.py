import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from PyQt5.QtWidgets import QMessageBox

from ui_script import MainWindow


class CookieDownloadConfirmationTests(unittest.TestCase):
    def _window(self, settings):
        return SimpleNamespace(settings=settings, log_to_gui=Mock())

    def _confirm(self, window, tasks):
        return MainWindow._confirm_cookie_mode_for_downloads(window, tasks)

    def test_browser_cookie_mode_is_reserved_for_fallback_without_prompt(self):
        window = self._window({
            "cookie_source_mode": "managed",
        })
        tasks = [
            {"url": "https://www.youtube.com/watch?v=one", "type": "youtube_video"},
            {"url": "https://www.youtube.com/watch?v=two", "type": "youtube_video"},
        ]

        with patch.object(QMessageBox, "question") as question:
            confirmed = self._confirm(window, tasks)

        self.assertTrue(confirmed)
        question.assert_not_called()
        window.log_to_gui.assert_called_once()
        self.assertIn("fallback", window.log_to_gui.call_args.args[0].lower())

    def test_cookie_file_mode_does_not_block_the_batch(self):
        window = self._window({
            "cookie_source_mode": "file",
            "use_cookies": True,
            "cookies_file_path": r"C:\cookies\youtube.txt",
        })
        tasks = [{"url": "https://youtu.be/example", "type": "youtube_video"}]

        with patch.object(QMessageBox, "question") as question:
            confirmed = self._confirm(window, tasks)

        self.assertTrue(confirmed)
        question.assert_not_called()
        window.log_to_gui.assert_called_once()

    def test_no_prompt_when_cookie_mode_is_off(self):
        window = self._window({"cookie_source_mode": "none"})
        tasks = [{"url": "https://youtu.be/example", "type": "youtube_video"}]

        with patch.object(QMessageBox, "question") as question:
            confirmed = self._confirm(window, tasks)

        self.assertTrue(confirmed)
        question.assert_not_called()
        window.log_to_gui.assert_not_called()

    def test_no_prompt_for_drive_only_batch(self):
        window = self._window({"use_cookies": True, "cookies_file_path": "cookies.txt"})
        tasks = [{"url": "https://drive.google.com/file/d/id/view", "type": "drive"}]

        with patch.object(QMessageBox, "question") as question:
            confirmed = self._confirm(window, tasks)

        self.assertTrue(confirmed)
        question.assert_not_called()


if __name__ == "__main__":
    unittest.main()
