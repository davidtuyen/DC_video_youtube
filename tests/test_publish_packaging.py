import hashlib
import json
import tempfile
import unittest
import zipfile
import io
import subprocess
from pathlib import Path
from unittest import mock

import publish
from update_manager import UpdatePackageApplier


class PublishPackagingTests(unittest.TestCase):
    def _make_dist(self, root: Path, runtime_tag="1.0.14", updater_tag="1.0.14"):
        app_dir = root / publish.APP_NAME
        (app_dir / "data" / "node").mkdir(parents=True)
        (app_dir / "data" / "node" / "node.exe").write_bytes(b"node")
        (app_dir / "data" / "runtime-manifest.json").write_text(json.dumps({
            "schema_version": 2,
            "release_tag": runtime_tag,
        }), encoding="utf-8")
        worker = app_dir / "updater" / "UpdaterWorker-2.1.0.exe"
        worker.parent.mkdir(parents=True)
        worker.write_bytes(b"worker")
        (app_dir / "data" / "updater-manifest.json").write_text(json.dumps({
            "schema_version": 1,
            "protocol_version": 2,
            "worker": {
                "path": "updater/UpdaterWorker-2.1.0.exe",
                "sha256": hashlib.sha256(b"worker").hexdigest(),
                "release_tag": updater_tag,
            },
        }), encoding="utf-8")
        (app_dir / "yt-dlp").mkdir()
        (app_dir / "yt-dlp" / "yt-dlp.exe").write_bytes(b"yt-dlp")
        (app_dir / "UpdaterLauncher.exe").write_bytes(b"launcher")
        (app_dir / "data" / "downloader_settings_qt.json").write_bytes(b"user")
        (app_dir / "YouTube Downloader Pro.exe").write_bytes(b"app")
        return app_dir

    def test_smart_package_uses_v2_pkg_and_component_release_tags(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dist_dir = Path(temp_dir) / "dist"
            self._make_dist(dist_dir)

            with mock.patch.object(publish, "DIST_DIR", dist_dir):
                package = publish.create_package("smart", "1.0.14")

            self.assertEqual(package.name, "app-update-v2.pkg")
            manifest = UpdatePackageApplier.validate_package(package)
            self.assertEqual(manifest["schema_version"], 2)
            self.assertEqual(manifest["minimum_app_version"], "1.0.13")
            entries = {entry["path"]: entry for entry in manifest["files"]}
            self.assertIn("data/node/node.exe", entries)
            self.assertEqual(entries["data/node/node.exe"]["component"], "runtime")
            self.assertIn("updater/UpdaterWorker-2.1.0.exe", entries)
            self.assertEqual(entries["updater/UpdaterWorker-2.1.0.exe"]["component"], "updater")
            self.assertNotIn("yt-dlp/yt-dlp.exe", entries)
            self.assertNotIn("UpdaterLauncher.exe", entries)
            self.assertNotIn("data/downloader_settings_qt.json", entries)

    def test_unchanged_runtime_and_worker_are_not_reshipped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dist_dir = Path(temp_dir) / "dist"
            self._make_dist(dist_dir, runtime_tag="1.0.13", updater_tag="1.0.13")

            with mock.patch.object(publish, "DIST_DIR", dist_dir):
                package = publish.create_package("smart", "1.0.15")

            manifest = UpdatePackageApplier.validate_package(package)
            paths = {entry["path"] for entry in manifest["files"]}
            self.assertNotIn("data/node/node.exe", paths)
            self.assertNotIn("updater/UpdaterWorker-2.1.0.exe", paths)
            self.assertIn("data/runtime-manifest.json", paths)
            self.assertIn("data/updater-manifest.json", paths)

    def test_v1013_refuses_smart_package(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dist_dir = Path(temp_dir) / "dist"
            self._make_dist(dist_dir, runtime_tag="1.0.13", updater_tag="1.0.13")

            with mock.patch.object(publish, "DIST_DIR", dist_dir):
                with self.assertRaisesRegex(ValueError, "installer-only"):
                    publish.create_package("smart", "1.0.13")

    def test_build_failure_restores_source_version_exactly(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "ui_script.py"
            original = 'APP_VERSION = "1.0.13"\nprint("keep bytes")\n'
            source.write_text(original, encoding="utf-8")

            with mock.patch.object(publish, "REPO_ROOT", root):
                with self.assertRaisesRegex(RuntimeError, "build failed"):
                    publish.run_release_pipeline(
                        "1.0.14",
                        build_callback=mock.Mock(side_effect=RuntimeError("build failed")),
                        upload_callback=mock.Mock(),
                    )

            self.assertEqual(source.read_text(encoding="utf-8"), original)

    def test_release_is_published_only_after_verified_asset_upload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            asset = Path(temp_dir) / "app-update-v2.pkg"
            asset.write_bytes(b"package")
            digest = hashlib.sha256(asset.read_bytes()).hexdigest()
            create_response = mock.Mock(status_code=201)
            create_response.json.return_value = {
                "id": 7,
                "draft": True,
                "upload_url": "https://uploads.example/assets{?name,label}",
                "assets": [],
            }
            upload_response = mock.Mock(status_code=201)
            upload_response.json.return_value = {
                "name": asset.name,
                "size": asset.stat().st_size,
                "digest": f"sha256:{digest}",
            }
            publish_response = mock.Mock(status_code=200)

            with mock.patch.object(publish, "GITHUB_TOKEN", "test-token"):
                with mock.patch.object(
                    publish.requests,
                    "post",
                    side_effect=[create_response, upload_response],
                ) as post:
                    with mock.patch.object(publish.requests, "patch", return_value=publish_response) as patch:
                        publish.upload_to_github([asset], "1.0.14")

            self.assertTrue(post.call_args_list[0].kwargs["json"]["draft"])
            self.assertIn(asset.name, post.call_args_list[0].kwargs["json"]["body"])
            self.assertIn(digest, post.call_args_list[0].kwargs["json"]["body"])
            self.assertEqual(patch.call_args.kwargs["json"], {"draft": False})

    def test_v1013_release_notes_explain_migration_and_preserved_data(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            setup = Path(temp_dir) / "YouTubeDownloaderPro-Setup-v1.0.13.exe"
            runtime = Path(temp_dir) / "node-runtime-win-x64.pkg"
            setup.write_bytes(b"setup")
            runtime.write_bytes(b"runtime")

            body = publish._release_body("1.0.13", [setup, runtime])

        self.assertIn("migration", body)
        self.assertIn("cài đè", body)
        self.assertIn("settings, history, cookies, token, proxy, thumbnails", body)
        self.assertIn(setup.name, body)
        self.assertIn(runtime.name, body)

    def test_published_release_is_never_modified(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            asset = Path(temp_dir) / "app-update-v2.pkg"
            asset.write_bytes(b"package")
            create_response = mock.Mock(status_code=422)
            existing_response = mock.Mock(status_code=200)
            existing_response.json.return_value = {"id": 7, "draft": False}

            with mock.patch.object(publish, "GITHUB_TOKEN", "test-token"):
                with mock.patch.object(publish.requests, "post", return_value=create_response):
                    with mock.patch.object(publish.requests, "get", return_value=existing_response):
                        with mock.patch.object(publish.requests, "delete") as delete:
                            with self.assertRaisesRegex(RuntimeError, "already published"):
                                publish.upload_to_github([asset], "1.0.14")

        delete.assert_not_called()

    def test_portable_node_comes_from_verified_official_archive(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            archive_buffer = io.BytesIO()
            prefix = f"node-v{publish.NODE_VERSION}-win-x64/"
            with zipfile.ZipFile(archive_buffer, "w") as archive:
                archive.writestr(prefix + "node.exe", b"official-node")
                archive.writestr(prefix + "LICENSE", b"official-license")
            archive_bytes = archive_buffer.getvalue()
            archive_hash = hashlib.sha256(archive_bytes).hexdigest()
            shasums = f"{archive_hash}  {publish.NODE_DISTRIBUTION_NAME}\n".encode()
            completed = subprocess.CompletedProcess(
                ["node.exe", "--version"], 0, f"v{publish.NODE_VERSION}\n", ""
            )

            with mock.patch.object(publish, "REPO_ROOT", root):
                with mock.patch.object(
                    publish,
                    "_download_bytes",
                    side_effect=[shasums, archive_bytes],
                ):
                    with mock.patch.object(publish.subprocess, "run", return_value=completed):
                        node_path = publish.ensure_portable_node()

            self.assertEqual(node_path.read_bytes(), b"official-node")
            self.assertEqual((node_path.parent / "LICENSE").read_bytes(), b"official-license")

    def test_v1013_release_contains_only_setup_and_pkg_assets(self):
        setup = Path("YouTubeDownloaderPro-Setup-v1.0.13.exe")
        runtime = Path("node-runtime-win-x64.pkg")
        updater_outputs = (Path("launcher.exe"), Path("worker.exe"), {})

        with mock.patch.object(publish, "clean_build"):
            with mock.patch.object(publish, "prepare_runtime_assets", return_value=runtime):
                with mock.patch.object(publish, "build_updaters", return_value=updater_outputs):
                    with mock.patch.object(publish, "build_main_app", return_value=Path("app")):
                        with mock.patch.object(
                            publish, "build_installer", return_value=setup, create=True
                        ):
                            assets = publish.build_release_assets("1.0.13")

        self.assertEqual(assets, [setup, runtime])
        self.assertFalse(any(path.suffix.casefold() == ".zip" for path in assets))

    def test_installer_script_preserves_user_state_and_existing_ytdlp(self):
        script_path = publish.REPO_ROOT / "installer.iss"
        self.assertTrue(script_path.is_file(), "installer.iss must exist")
        script = script_path.read_text(encoding="utf-8")

        for protected in (
            "downloader_settings",
            "download_history",
            "token",
            "credentials",
            "proxy_settings",
            "cookies",
        ):
            self.assertIn(protected, script)
        self.assertIn("yt-dlp", script)
        self.assertIn("onlyifdoesntexist", script)

    def test_inno_compiler_is_found_in_per_user_install(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            compiler = (
                Path(temp_dir) / "Programs" / "Inno Setup 6" / "ISCC.exe"
            )
            compiler.parent.mkdir(parents=True)
            compiler.write_bytes(b"")

            with mock.patch.dict(
                publish.os.environ,
                {
                    "LOCALAPPDATA": temp_dir,
                    "ProgramFiles": "",
                    "ProgramFiles(x86)": "",
                    "INNO_SETUP_COMPILER": "",
                },
                clear=False,
            ):
                with mock.patch.object(publish.shutil, "which", return_value=None):
                    self.assertEqual(publish._find_inno_compiler(), compiler)

    def test_main_app_build_collects_ytdlp_modules(self):
        updater_outputs = (Path("launcher.exe"), Path("worker.exe"), {})

        with mock.patch.object(publish, "_run_pyinstaller") as run:
            with mock.patch.object(
                publish, "DIST_DIR", Path("missing-dist-for-test")
            ):
                with self.assertRaises(FileNotFoundError):
                    publish.build_main_app("1.0.13", updater_outputs)

        self.assertIn("--collect-all", run.call_args.kwargs["extra_args"])
        self.assertIn("yt_dlp", run.call_args.kwargs["extra_args"])

    def test_build_command_restores_source_version_when_build_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            source = root / "ui_script.py"
            original = 'APP_VERSION = "1.0.12"\n'
            source.write_text(original, encoding="utf-8")

            with mock.patch.object(publish, "REPO_ROOT", root):
                with mock.patch.object(
                    publish, "build_release_assets", side_effect=RuntimeError("boom")
                ):
                    with mock.patch.object(
                        publish.sys, "argv", ["publish.py", "build", "1.0.13"]
                    ):
                        with self.assertRaisesRegex(RuntimeError, "boom"):
                            publish.main()

            self.assertEqual(source.read_text(encoding="utf-8"), original)


if __name__ == "__main__":
    unittest.main()
