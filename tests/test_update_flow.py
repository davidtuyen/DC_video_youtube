import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt5.QtWidgets import QApplication

import workers
import update_manager
from ui_script import MainWindow


class ReleaseAssetTests(unittest.TestCase):
    def test_selects_only_exact_v2_asset_with_digest(self):
        digest = "a" * 64
        release = {
            "assets": [
                {
                    "name": "node-runtime-win-x64.pkg",
                    "browser_download_url": "https://example.test/node.pkg",
                    "digest": f"sha256:{'b' * 64}",
                    "size": 10,
                    "state": "uploaded",
                },
                {
                    "name": "app-update-v2.pkg",
                    "browser_download_url": "https://example.test/app.pkg",
                    "digest": f"sha256:{digest}",
                    "size": 123,
                    "state": "uploaded",
                },
            ]
        }

        asset = workers._select_app_update_asset(release)

        self.assertEqual(
            asset,
            update_manager.ReleaseAsset("app-update-v2.pkg", "https://example.test/app.pkg", digest, 123),
        )

    def test_rejects_fallback_archives_and_missing_digest(self):
        for asset in (
            {
                "name": "update.zip",
                "browser_download_url": "https://example.test/update.zip",
                "digest": f"sha256:{'a' * 64}",
                "size": 123,
                "state": "uploaded",
            },
            {
                "name": "app-update-v2.pkg",
                "browser_download_url": "https://example.test/app.pkg",
                "size": 123,
                "state": "uploaded",
            },
            {
                "name": "app-update-v2.pkg",
                "browser_download_url": "https://example.test/app.pkg",
                "digest": f"sha256:{'a' * 64}",
                "size": 0,
                "state": "uploaded",
            },
        ):
            with self.subTest(asset=asset):
                self.assertIsNone(workers._select_app_update_asset({"assets": [asset]}))

    def test_download_worker_passes_required_outer_digest(self):
        asset = update_manager.ReleaseAsset(
            "app-update-v2.pkg",
            "https://example.test/app.pkg",
            "a" * 64,
            123,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            artifact = Path(temp_dir) / "app.pkg"
            artifact.write_bytes(b"package")
            manager = mock.Mock()
            manager.update_app.return_value = update_manager.UpdateResult(
                True,
                "app",
                artifact_path=str(artifact),
            )
            worker = workers.UpdateCheckerWorker(mode="download", release_asset=asset)

            with mock.patch.object(workers, "UpdateManager", return_value=manager):
                worker._download_update()

            manager.update_app.assert_called_once_with(
                download_url=asset.url,
                expected_sha256=asset.sha256,
                expected_size=asset.size,
            )

    def test_latest_app_check_repairs_missing_runtime(self):
        response = mock.Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {"tag_name": "1.0.13", "assets": []}
        manager = mock.Mock()
        manager.check_runtime.return_value = update_manager.RuntimeStatus(
            update_manager.RuntimeState.MISSING,
            Path("data/node/node.exe"),
        )
        manager.repair_runtime.return_value = update_manager.UpdateResult(
            True,
            "node",
            changed_components=("node",),
        )
        worker = workers.UpdateCheckerWorker(mode="check")
        results = []
        worker.no_update.connect(lambda *args: results.append(tuple(args)))

        with mock.patch.object(workers, "APP_VERSION", "1.0.13"):
            with mock.patch.object(workers.requests, "get", return_value=response):
                with mock.patch.object(workers, "UpdateManager", return_value=manager):
                    worker._check_latest_release()

        manager.repair_runtime.assert_called_once_with()
        self.assertEqual(results, [("1.0.13", True)])


class UpdateUiIsolationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def _create_window(self, settings=None):
        with mock.patch("ui_script.main_logic.load_settings_from_file", return_value=settings or {}):
            with mock.patch.object(MainWindow, "_load_download_history"):
                with mock.patch.object(MainWindow, "_initialize_proxy_manager"):
                    with mock.patch.object(MainWindow, "_initialize_yt_dlp_non_blocking"):
                        return MainWindow()

    def test_auto_yt_dlp_setting_does_not_schedule_app_update(self):
        with mock.patch("ui_script.QTimer.singleShot") as single_shot:
            window = self._create_window({"auto_update_yt_dlp": True})
        try:
            single_shot.assert_not_called()
        finally:
            window.deleteLater()

    def test_update_is_blocked_while_download_is_active(self):
        window = self._create_window()
        try:
            window.active_threads["download-1"] = {"status": "downloading"}

            self.assertFalse(window._can_start_update(manual=False))
        finally:
            window.deleteLater()


if __name__ == "__main__":
    unittest.main()
