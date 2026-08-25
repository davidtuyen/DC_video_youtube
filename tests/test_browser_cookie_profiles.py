import importlib
import inspect
import tempfile
import time
import unittest
from pathlib import Path


class BrowserCookieProfileTests(unittest.TestCase):
    def setUp(self):
        try:
            self.module = importlib.import_module("browser_cookie_profiles")
        except ModuleNotFoundError:
            self.fail("browser_cookie_profiles module is required")

    def test_personal_browser_profile_discovery_api_is_removed(self):
        source = inspect.getsource(self.module)

        for forbidden in (
            "def discover_browser_profiles",
            "class BrowserProfile",
            "def split_browser_cookie_spec",
            "def normalize_browser_cookie_spec",
        ):
            with self.subTest(forbidden=forbidden):
                self.assertNotIn(forbidden, source)

    def test_browser_cookie_spec_preserves_managed_profile_path(self):
        profile = r"C:\app\data\browser\chrome-user-data\Default"

        self.assertEqual(
            self.module.build_browser_cookie_spec("Chrome", profile),
            f"chrome:{profile}",
        )

    def test_cookie_mode_migration_maps_legacy_settings_and_removes_profile_keys(self):
        cases = (
            (
                {
                    "use_cookies": True,
                    "cookies_file_path": r"C:\cookies\manual.txt",
                    "cookies_from_browser": "edge:Profile 9",
                },
                "file",
            ),
            ({"cookies_from_browser": "chrome:Profile 66"}, "managed"),
            ({"cookies_profile": "Profile 66"}, "managed"),
            ({}, "none"),
        )
        for settings, expected_mode in cases:
            with self.subTest(settings=settings):
                changed = self.module.migrate_cookie_source_settings(settings)

                self.assertTrue(changed)
                self.assertEqual(settings["cookie_source_mode"], expected_mode)
                for legacy_key in (
                    "cookies_from_browser",
                    "cookies_profile",
                    "chrome_profile",
                    "extracted_cookies_path",
                ):
                    self.assertNotIn(legacy_key, settings)

    def test_set_cookie_mode_preserves_inactive_manual_file_path(self):
        settings = {
            "cookie_source_mode": "file",
            "use_cookies": True,
            "cookies_file_path": r"C:\cookies\manual.txt",
            "cookies_from_browser": "chrome:Profile 66",
        }

        self.module.set_cookie_source_mode(settings, "managed")

        self.assertEqual(settings["cookie_source_mode"], "managed")
        self.assertFalse(settings["use_cookies"])
        self.assertEqual(settings["cookies_file_path"], r"C:\cookies\manual.txt")
        self.assertNotIn("cookies_from_browser", settings)

    def test_cookie_file_requires_live_youtube_login_cookie(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cookie_file = Path(temp_dir) / "cookies.txt"
            cookie_file.write_text(
                "# Netscape HTTP Cookie File\n"
                ".youtube.com\tTRUE\t/\tTRUE\t0\tPREF\tfake\n",
                encoding="utf-8",
            )
            self.assertFalse(
                self.module.cookie_file_has_youtube_auth(cookie_file)
            )

            cookie_file.write_text(
                "# Netscape HTTP Cookie File\n"
                ".notyoutube.com\tTRUE\t/\tTRUE\t0\tLOGIN_INFO\tspoofed\n",
                encoding="utf-8",
            )
            self.assertFalse(
                self.module.cookie_file_has_youtube_auth(cookie_file)
            )

            cookie_file.write_text(
                "# Netscape HTTP Cookie File\n"
                f".youtube.com\tTRUE\t/\tTRUE\t{int(time.time()) + 3600}"
                "\tLOGIN_INFO\tfake-login\n",
                encoding="utf-8",
            )
            self.assertTrue(
                self.module.cookie_file_has_youtube_auth(cookie_file)
            )

            cookie_file.write_text(
                "# Netscape HTTP Cookie File\n"
                ".youtube.com\tTRUE\t/\tTRUE\t0\tLOGIN_INFO\t\n",
                encoding="utf-8",
            )
            self.assertFalse(
                self.module.cookie_file_has_youtube_auth(cookie_file)
            )

    def test_file_mode_uses_valid_manual_cookie(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cookie_file = Path(temp_dir) / "cookies.txt"
            cookie_file.write_text(
                "# Netscape HTTP Cookie File\n"
                ".youtube.com\tTRUE\t/\tTRUE\t0\tLOGIN_INFO\tmanual-login\n",
                encoding="utf-8",
            )
            managed = self.module.DownloadCookieSource(
                browser_spec=r"chrome:C:\app\data\browser\chrome-user-data\Default"
            )

            source = self.module.resolve_download_cookie_source(
                {
                    "cookie_source_mode": "file",
                    "use_cookies": True,
                    "cookies_file_path": str(cookie_file),
                },
                managed_source=managed,
            )

        self.assertTrue(source.use_cookie_file)
        self.assertEqual(source.cookie_file_path, str(cookie_file))
        self.assertFalse(source.browser_spec)

    def test_managed_mode_uses_only_managed_source(self):
        managed = self.module.DownloadCookieSource(
            browser_spec=r"chrome:C:\app\data\browser\chrome-user-data\Default"
        )

        source = self.module.resolve_download_cookie_source(
            {
                "cookie_source_mode": "managed",
            },
            managed_source=managed,
        )

        self.assertEqual(source, managed)

    def test_invalid_manual_cookie_file_is_not_accepted(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            cookie_file = Path(temp_dir) / "cookies.txt"
            cookie_file.write_text(
                "# Netscape HTTP Cookie File\n"
                ".youtube.com\tTRUE\t/\tTRUE\t0\tPREF\tfake\n",
                encoding="utf-8",
            )

            source = self.module.resolve_download_cookie_source({
                "cookie_source_mode": "file",
                "use_cookies": True,
                "cookies_file_path": str(cookie_file),
            })

        self.assertTrue(source.invalid_cookie_file)
        self.assertFalse(source.use_cookie_file)
        self.assertEqual(source.cookie_file_path, "")

    def test_none_mode_ignores_managed_and_legacy_browser_sources(self):
        managed = self.module.DownloadCookieSource(
            browser_spec=r"chrome:C:\app\data\browser\chrome-user-data\Default"
        )

        source = self.module.resolve_download_cookie_source(
            {
                "cookie_source_mode": "none",
                "cookies_from_browser": "edge:Profile 9",
            },
            managed_source=managed,
        )

        self.assertEqual(source, self.module.DownloadCookieSource())

    def test_managed_mode_never_falls_back_to_personal_browser_profile(self):
        source = self.module.resolve_download_cookie_source({
            "cookie_source_mode": "managed",
            "cookies_from_browser": "edge:Profile 9",
            "cookies_profile": "Profile 9",
        })

        self.assertEqual(source, self.module.DownloadCookieSource())

    def test_file_mode_rejects_invalid_file_without_falling_back_to_managed(self):
        managed = self.module.DownloadCookieSource(
            browser_spec=r"chrome:C:\app\data\browser\chrome-user-data\Default"
        )
        source = self.module.resolve_download_cookie_source(
            {
                "cookie_source_mode": "file",
                "cookies_file_path": r"C:\missing\cookies.txt",
            },
            managed_source=managed,
        )

        self.assertEqual(source.browser_spec, "")
        self.assertFalse(source.use_cookie_file)
        self.assertTrue(source.invalid_cookie_file)


if __name__ == "__main__":
    unittest.main()
