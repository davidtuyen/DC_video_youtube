import os
import inspect
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock


os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from PyQt5.QtWidgets import QApplication

from managed_chrome import BrowserLaunchResult, ManagedChromeStatus
from settings_dialog import SettingsDialog


class CookieSettingsUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _session(self):
        session = Mock()
        session.profile_dir = Path(r"C:\app\data\browser\chrome-user-data\Default")
        session.open_browser.return_value = BrowserLaunchResult(
            True, message="Đã mở Chrome riêng."
        )
        session.check_login_status.return_value = ManagedChromeStatus(
            "authenticated", True, "Đã đăng nhập YouTube trong Chrome riêng."
        )
        return session

    def _dialog(self, settings=None, session=None):
        return SettingsDialog(
            settings or {},
            managed_chrome=session or self._session(),
        )

    def test_cookie_tab_only_offers_none_managed_and_file_modes(self):
        dialog = self._dialog()
        try:
            modes = [
                dialog.cookies_mode_combo.itemText(index)
                for index in range(dialog.cookies_mode_combo.count())
            ]
            self.assertEqual(
                modes,
                [
                    "Không dùng",
                    "Chrome riêng của ứng dụng",
                    "File tùy chỉnh (.txt)",
                ],
            )
            self.assertFalse(hasattr(dialog, "cookies_browser_combo"))
            self.assertFalse(hasattr(dialog, "chrome_profile_combo"))
            self.assertFalse(hasattr(dialog, "cookies_test_button"))
        finally:
            dialog.deleteLater()

    def test_legacy_personal_browser_extractor_is_removed(self):
        source = inspect.getsource(SettingsDialog)

        for forbidden in (
            "_populate_browser_profiles",
            "_test_browser_cookies",
            "_extract_youtube_cookies",
            "dQw4w9WgXcQ",
            "DPAPI",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_managed_panel_uses_shared_session_for_open_and_status(self):
        session = self._session()
        dialog = self._dialog(session=session)
        try:
            self.assertIn(str(session.profile_dir), dialog.managed_profile_path.text())

            dialog.managed_open_button.click()
            dialog.managed_status_button.click()

            session.open_browser.assert_called_once_with()
            session.check_login_status.assert_called_once_with()
            self.assertIn("Đã đăng nhập", dialog.managed_status_label.text())
        finally:
            dialog.deleteLater()

    def test_legacy_browser_profile_loads_as_managed_and_is_cleared_on_save(self):
        dialog = self._dialog({
            "cookies_from_browser": "chrome:Profile 66",
            "cookies_profile": "Profile 66",
            "chrome_profile": "Profile 66",
            "extracted_cookies_path": r"C:\stale\youtube_cookies.txt",
            "cookies_file_path": r"C:\cookies\manual.txt",
        })
        try:
            self.assertEqual(dialog.cookies_mode_combo.currentIndex(), 1)
            dialog.accept_settings()
            saved = dialog.get_settings()

            self.assertEqual(saved["cookie_source_mode"], "managed")
            self.assertFalse(saved["use_cookies"])
            self.assertEqual(saved["cookies_file_path"], r"C:\cookies\manual.txt")
            for legacy_key in (
                "cookies_from_browser",
                "cookies_profile",
                "chrome_profile",
                "extracted_cookies_path",
            ):
                self.assertNotIn(legacy_key, saved)
        finally:
            dialog.deleteLater()

    def test_file_and_none_modes_save_explicit_mode_without_losing_file_path(self):
        dialog = self._dialog({"cookies_file_path": r"C:\cookies\manual.txt"})
        try:
            dialog.cookies_mode_combo.setCurrentIndex(2)
            dialog.accept_settings()
            saved = dialog.get_settings()
            self.assertEqual(saved["cookie_source_mode"], "file")
            self.assertTrue(saved["use_cookies"])
            self.assertEqual(saved["cookies_file_path"], r"C:\cookies\manual.txt")
        finally:
            dialog.deleteLater()

        dialog = self._dialog({"cookies_file_path": r"C:\cookies\manual.txt"})
        try:
            dialog.cookies_mode_combo.setCurrentIndex(0)
            dialog.accept_settings()
            saved = dialog.get_settings()
            self.assertEqual(saved["cookie_source_mode"], "none")
            self.assertFalse(saved["use_cookies"])
            self.assertEqual(saved["cookies_file_path"], r"C:\cookies\manual.txt")
        finally:
            dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
