import os
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PyQt5.QtWidgets import QApplication, QMessageBox, QToolBar

from browser_cookie_profiles import DownloadCookieSource
from ui_script import MainWindow


class ManagedBrowserUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _create_window(self):
        with patch("ui_script.main_logic.load_settings_from_file", return_value={}):
            with patch.object(MainWindow, "_load_download_history"):
                with patch.object(MainWindow, "_initialize_proxy_manager"):
                    with patch.object(MainWindow, "_initialize_yt_dlp_non_blocking"):
                        return MainWindow()

    def test_browser_action_is_immediately_after_google_drive_and_keeps_dashboard(self):
        window = self._create_window()
        try:
            toolbar = window.findChild(QToolBar, "Main Toolbar")
            self.assertIsNotNone(toolbar)
            actions = toolbar.actions()
            drive_index = actions.index(window.add_drive_link_action)
            browser_action = actions[drive_index + 1]
            self.assertEqual(browser_action.text(), "Trình Duyệt")

            central_widget = window.centralWidget()
            window.managed_chrome.open_browser = Mock(
                return_value=Mock(success=True, message="Đã mở Chrome riêng.")
            )
            browser_action.trigger()

            window.managed_chrome.open_browser.assert_called_once_with()
            self.assertIs(window.centralWidget(), central_widget)
        finally:
            window.managed_chrome.shutdown = Mock()
            window.deleteLater()
            self.app.processEvents()

    def test_browser_launch_failure_shows_clear_warning(self):
        window = self._create_window()
        try:
            window.managed_chrome.open_browser = Mock(
                return_value=Mock(
                    success=False,
                    message="Không tìm thấy Google Chrome. Hãy cài Chrome rồi thử lại.",
                )
            )
            with patch.object(QMessageBox, "warning") as warning:
                window._open_managed_browser()

            warning.assert_called_once()
            self.assertIn("Không tìm thấy Google Chrome", warning.call_args.args[2])
        finally:
            window.managed_chrome.shutdown = Mock()
            window.deleteLater()
            self.app.processEvents()

    def test_toolbar_enables_managed_mode_only_after_successful_launch(self):
        window = self._create_window()
        try:
            window.settings.update({
                "cookie_source_mode": "file",
                "use_cookies": True,
                "cookies_file_path": r"C:\cookies\manual.txt",
                "cookies_from_browser": "edge:Profile 9",
            })
            window.managed_chrome.open_browser = Mock(
                return_value=Mock(success=True, message="Đã mở Chrome riêng.")
            )
            with patch("ui_script.main_logic.save_settings_to_file") as save:
                window._open_managed_browser()

            self.assertEqual(window.settings["cookie_source_mode"], "managed")
            self.assertFalse(window.settings["use_cookies"])
            self.assertEqual(
                window.settings["cookies_file_path"], r"C:\cookies\manual.txt"
            )
            self.assertNotIn("cookies_from_browser", window.settings)
            save.assert_called_once()

            window.settings["cookie_source_mode"] = "none"
            window.managed_chrome.open_browser.return_value = Mock(
                success=False, message="Chrome missing"
            )
            with patch.object(QMessageBox, "warning"), patch(
                "ui_script.main_logic.save_settings_to_file"
            ) as save:
                window._open_managed_browser()

            self.assertEqual(window.settings["cookie_source_mode"], "none")
            save.assert_not_called()
        finally:
            window.managed_chrome.shutdown = Mock()
            window.deleteLater()
            self.app.processEvents()

    def test_settings_dialog_receives_the_main_window_managed_session(self):
        window = self._create_window()
        try:
            dialog = Mock()
            dialog.exec_.return_value = 0
            with patch("ui_script.SettingsDialog", return_value=dialog) as dialog_type:
                window._open_settings_dialog()

            self.assertIs(
                dialog_type.call_args.kwargs["managed_chrome"],
                window.managed_chrome,
            )
        finally:
            window.managed_chrome.shutdown = Mock()
            window.deleteLater()
            self.app.processEvents()

    def test_download_resolution_requests_an_immutable_task_lease(self):
        window = self._create_window()
        try:
            window.settings["cookie_source_mode"] = "managed"
            managed = DownloadCookieSource(
                browser_spec=r"chrome:C:\app\data\browser\chrome-user-data\Default"
            )
            window.managed_chrome.resolve_cookie_source = Mock(return_value=managed)

            source = window._resolve_download_cookie_source("task-123")

            self.assertEqual(source, managed)
            window.managed_chrome.resolve_cookie_source.assert_called_once_with(
                lease_id="task-123"
            )
        finally:
            window.managed_chrome.shutdown = Mock()
            window.deleteLater()
            self.app.processEvents()

    def test_none_mode_never_contacts_managed_chrome(self):
        window = self._create_window()
        try:
            window.settings["cookie_source_mode"] = "none"
            window.managed_chrome.resolve_cookie_source = Mock()

            source = window._resolve_download_cookie_source("task-none")

            self.assertEqual(source, DownloadCookieSource())
            window.managed_chrome.resolve_cookie_source.assert_not_called()
        finally:
            window.managed_chrome.shutdown = Mock()
            window.deleteLater()
            self.app.processEvents()

    def test_file_mode_never_contacts_managed_chrome_when_file_is_invalid(self):
        window = self._create_window()
        try:
            window.settings.update({
                "cookie_source_mode": "file",
                "use_cookies": True,
                "cookies_file_path": r"C:\missing\cookies.txt",
            })
            window.managed_chrome.resolve_cookie_source = Mock()

            source = window._resolve_download_cookie_source("task-file")

            self.assertTrue(source.invalid_cookie_file)
            window.managed_chrome.resolve_cookie_source.assert_not_called()
        finally:
            window.managed_chrome.shutdown = Mock()
            window.deleteLater()
            self.app.processEvents()

    def test_shutdown_closes_managed_chrome_once_and_removes_snapshot(self):
        window = self._create_window()
        window._save_download_history = Mock()
        window.managed_chrome.shutdown = Mock()

        with patch("ui_script.main_logic.save_settings_to_file"):
            window.close()
            self.app.processEvents()

        window.managed_chrome.shutdown.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
