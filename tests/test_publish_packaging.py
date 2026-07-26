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
        node_bytes = b"node"
        license_bytes = b"license"
        (app_dir / "data" / "node" / "node.exe").write_bytes(node_bytes)
        (app_dir / "data" / "node" / "LICENSE").write_bytes(license_bytes)
        (app_dir / "data" / "runtime-manifest.json").write_text(json.dumps({
            "schema_version": 2,
            "release_tag": runtime_tag,
            "asset": {
                "name": "node-runtime-win-x64.pkg",
                "sha256": "0" * 64,
                "size": 1,
            },
            "node": {
                "version": "24.12.0",
                "minimum_version": "22.0.0",
                "relative_path": "data/node/node.exe",
                "sha256": hashlib.sha256(node_bytes).hexdigest(),
            },
            "files": [
                {
                    "path": "node.exe",
                    "sha256": hashlib.sha256(node_bytes).hexdigest(),
                    "size": len(node_bytes),
                },
                {
                    "path": "LICENSE",
                    "sha256": hashlib.sha256(license_bytes).hexdigest(),
                    "size": len(license_bytes),
                },
            ],
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

    def test_runtime_smart_package_requires_v1015_and_complete_runtime(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dist_dir = Path(temp_dir) / "dist"
            app_dir = self._make_dist(dist_dir, runtime_tag="1.0.15", updater_tag="1.0.15")
            with mock.patch.object(publish, "DIST_DIR", dist_dir):
                package = publish.create_package("smart", "1.0.15")

            self.assertEqual(package.name, "app-update-v2.pkg")
            manifest = UpdatePackageApplier.validate_package(package)
            self.assertEqual(manifest["schema_version"], 2)
            self.assertEqual(manifest["minimum_app_version"], "1.0.15")
            entries = {entry["path"]: entry for entry in manifest["files"]}
            self.assertIn("data/node/node.exe", entries)
            self.assertIn("data/node/LICENSE", entries)
            self.assertIn("data/runtime-manifest.json", entries)
            self.assertEqual(entries["data/node/node.exe"]["component"], "runtime")
            self.assertIn("updater/UpdaterWorker-2.1.0.exe", entries)
            self.assertEqual(entries["updater/UpdaterWorker-2.1.0.exe"]["component"], "updater")
            self.assertNotIn("yt-dlp/yt-dlp.exe", entries)
            self.assertNotIn("UpdaterLauncher.exe", entries)
            self.assertNotIn("data/downloader_settings_qt.json", entries)

    def test_unchanged_runtime_worker_and_manifests_are_not_reshipped(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dist_dir = Path(temp_dir) / "dist"
            self._make_dist(dist_dir, runtime_tag="1.0.13", updater_tag="1.0.13")

            with mock.patch.object(publish, "DIST_DIR", dist_dir):
                package = publish.create_package("smart", "1.0.15")

            manifest = UpdatePackageApplier.validate_package(package)
            paths = {entry["path"] for entry in manifest["files"]}
            self.assertNotIn("data/node/node.exe", paths)
            self.assertNotIn("updater/UpdaterWorker-2.1.0.exe", paths)
            self.assertNotIn("data/runtime-manifest.json", paths)
            self.assertNotIn("data/updater-manifest.json", paths)

    def test_v1015_smart_package_contains_only_new_worker_and_app_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            dist_dir = Path(temp_dir) / "dist"
            self._make_dist(dist_dir, runtime_tag="1.0.13", updater_tag="1.0.15")

            with mock.patch.object(publish, "DIST_DIR", dist_dir):
                package = publish.create_package("smart", "1.0.15")

            manifest = UpdatePackageApplier.validate_package(package)
            paths = {entry["path"] for entry in manifest["files"]}
            self.assertEqual(manifest["minimum_app_version"], "1.0.13")
            self.assertIn("updater/UpdaterWorker-2.1.0.exe", paths)
            self.assertIn("data/updater-manifest.json", paths)
            self.assertIn(publish.MAIN_EXE_NAME, paths)
            self.assertNotIn("data/node/node.exe", paths)
            self.assertNotIn("data/node/LICENSE", paths)
            self.assertNotIn("data/runtime-manifest.json", paths)
            self.assertNotIn("yt-dlp/yt-dlp.exe", paths)
            self.assertNotIn("UpdaterLauncher.exe", paths)
            self.assertFalse(any("ffmpeg" in path.casefold() for path in paths))
            self.assertFalse(any(path in publish.USER_STATE_PATHS for path in paths))

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
            verify_response = mock.Mock(status_code=200)
            verify_response.json.return_value = {
                "id": 7,
                "draft": True,
                "tag_name": "1.0.14",
                "assets": [{
                    "name": asset.name,
                    "size": asset.stat().st_size,
                    "digest": f"sha256:{digest}",
                    "state": "uploaded",
                }],
            }
            publish_response = mock.Mock(status_code=200)

            with mock.patch.object(publish, "GITHUB_TOKEN", "test-token"):
                with mock.patch.object(
                    publish.requests,
                    "post",
                    side_effect=[create_response, upload_response],
                ) as post:
                    with mock.patch.object(
                        publish.requests, "get", return_value=verify_response
                    ) as get:
                        with mock.patch.object(publish.requests, "patch", return_value=publish_response) as patch:
                            publish.upload_to_github([asset], "1.0.14")

            self.assertTrue(post.call_args_list[0].kwargs["json"]["draft"])
            self.assertIn(asset.name, post.call_args_list[0].kwargs["json"]["body"])
            self.assertIn(digest, post.call_args_list[0].kwargs["json"]["body"])
            self.assertIn("/releases/7", get.call_args.args[0])
            self.assertEqual(patch.call_args.kwargs["json"], {"draft": False})

    def test_release_asset_set_must_match_exactly_before_publish(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            setup = Path(temp_dir) / "setup.exe"
            smart = Path(temp_dir) / "app-update-v2.pkg"
            setup.write_bytes(b"setup")
            smart.write_bytes(b"smart")
            expected = [setup, smart]

            def metadata(path):
                return {
                    "name": path.name,
                    "size": path.stat().st_size,
                    "digest": f"sha256:{hashlib.sha256(path.read_bytes()).hexdigest()}",
                    "state": "uploaded",
                }

            invalid_sets = {
                "extra": [metadata(setup), metadata(smart), {
                    "name": "unexpected.zip", "size": 1,
                    "digest": f"sha256:{'0' * 64}", "state": "uploaded",
                }],
                "duplicate": [metadata(setup), metadata(setup)],
                "missing": [metadata(setup)],
                "bad digest": [metadata(setup), {**metadata(smart), "digest": f"sha256:{'0' * 64}"}],
                "bad state": [metadata(setup), {**metadata(smart), "state": "new"}],
            }

            for reason, assets in invalid_sets.items():
                with self.subTest(reason=reason):
                    with self.assertRaisesRegex(RuntimeError, "asset"):
                        publish._verify_release_assets(
                            {"draft": True, "tag_name": "1.0.15", "assets": assets},
                            expected,
                            "1.0.15",
                        )

    def test_retry_draft_deletes_every_old_asset_before_upload(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            asset = Path(temp_dir) / "app-update-v2.pkg"
            asset.write_bytes(b"package")
            digest = hashlib.sha256(asset.read_bytes()).hexdigest()
            create_response = mock.Mock(status_code=422)
            existing_response = mock.Mock(status_code=200)
            existing_response.json.return_value = {
                "id": 7,
                "draft": True,
                "upload_url": "https://uploads.example/assets{?name,label}",
                "assets": [
                    {"id": 1, "name": asset.name, "url": "https://api.example/assets/1"},
                    {"id": 2, "name": "unexpected.zip", "url": "https://api.example/assets/2"},
                ],
            }
            upload_response = mock.Mock(status_code=201)
            upload_response.json.return_value = {
                "name": asset.name,
                "size": asset.stat().st_size,
                "digest": f"sha256:{digest}",
            }
            verify_response = mock.Mock(status_code=200)
            verify_response.json.return_value = {
                "id": 7,
                "draft": True,
                "tag_name": "1.0.15",
                "assets": [{
                    "name": asset.name,
                    "size": asset.stat().st_size,
                    "digest": f"sha256:{digest}",
                    "state": "uploaded",
                }],
            }
            delete_response = mock.Mock(status_code=204)
            publish_response = mock.Mock(status_code=200)

            with mock.patch.object(publish, "GITHUB_TOKEN", "test-token"):
                with mock.patch.object(
                    publish.requests, "post", side_effect=[create_response, upload_response]
                ):
                    with mock.patch.object(
                        publish.requests, "get", side_effect=[existing_response, verify_response]
                    ):
                        with mock.patch.object(
                            publish.requests, "delete", return_value=delete_response
                        ) as delete:
                            with mock.patch.object(
                                publish.requests, "patch", return_value=publish_response
                            ):
                                publish.upload_to_github([asset], "1.0.15")

            self.assertEqual(delete.call_count, 2)
            self.assertEqual(
                {call.args[0] for call in delete.call_args_list},
                {"https://api.example/assets/1", "https://api.example/assets/2"},
            )

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

    def test_v1014_release_notes_describe_offline_smoke_and_shortcut(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            setup = Path(temp_dir) / "YouTubeDownloaderPro-Setup-v1.0.14.exe"
            smart = Path(temp_dir) / "app-update-v2.pkg"
            setup.write_bytes(b"setup")
            smart.write_bytes(b"smart")

            body = publish._release_body("1.0.14", [setup, smart])

        self.assertIn("Desktop shortcut", body)
        self.assertIn("offline", body)
        self.assertIn("không truy cập YouTube", body)

    def test_v1015_release_metadata_and_notes(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            setup = Path(temp_dir) / "YouTubeDownloaderPro-Setup-v1.0.15.exe"
            smart = Path(temp_dir) / "app-update-v2.pkg"
            setup.write_bytes(b"setup")
            smart.write_bytes(b"smart")

            body = publish._release_body("1.0.15", [setup, smart])
            source_version = publish.get_current_version()
            installer = (publish.REPO_ROOT / "installer.iss").read_text(encoding="utf-8")

        self.assertEqual(source_version, "1.0.15")
        self.assertEqual(publish.UPDATER_WORKER_VERSION, "2.1.0")
        self.assertEqual(publish.UPDATER_WORKER_RELEASE_TAG, "1.0.15")
        self.assertIn('#define MyAppVersion "1.0.15"', installer)
        self.assertIn("LICENSE", body)
        self.assertIn("yt-dlp 2026.07.04", body)
        self.assertIn("UpdaterWorker 2.1.0", body)

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

    def test_installer_ytdlp_comes_from_pinned_verified_release(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            node_path = root / "data" / "node" / "node.exe"
            node_path.parent.mkdir(parents=True)
            node_path.write_bytes(b"node")
            binary = b"official yt-dlp"
            digest = hashlib.sha256(binary).hexdigest()
            checksums = f"{digest}  yt-dlp.exe\n".encode()
            calls = []

            def download(url):
                calls.append(url)
                return checksums if url.endswith("SHA2-256SUMS") else binary

            version_result = subprocess.CompletedProcess(
                ["yt-dlp.exe", "--version"], 0, "2026.07.04\n", ""
            )
            smoke_result = subprocess.CompletedProcess(
                ["yt-dlp.exe", "test:"], 0, "", "[debug] JS runtimes: node-24.12.0\n"
            )
            with mock.patch.object(publish, "REPO_ROOT", root):
                with mock.patch.object(publish, "BUILD_DIR", root / "build"):
                    with mock.patch.object(publish, "_download_bytes", side_effect=download):
                        with mock.patch.object(
                            publish.subprocess, "run", side_effect=[version_result, smoke_result]
                        ) as run:
                            result = publish.prepare_pinned_yt_dlp(node_path)

            self.assertEqual(result.read_bytes(), binary)
            self.assertEqual(
                calls,
                [publish.YT_DLP_SHASUMS_URL, publish.YT_DLP_BINARY_URL],
            )
            self.assertIn("2026.07.04", calls[0])
            smoke_command = run.call_args_list[1].args[0]
            self.assertIn("test:", smoke_command)
            self.assertNotIn("youtube.com", " ".join(smoke_command).casefold())
            self.assertIn(f"node:{node_path}", smoke_command)

    def test_pinned_ytdlp_rejects_bad_hash_version_and_smoke(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            node_path = root / "node.exe"
            node_path.write_bytes(b"node")
            binary = b"official yt-dlp"
            digest = hashlib.sha256(binary).hexdigest()
            valid_checksums = f"{digest}  yt-dlp.exe\n".encode()
            version_ok = subprocess.CompletedProcess([], 0, "2026.07.04\n", "")
            smoke_ok = subprocess.CompletedProcess(
                [], 0, "", "[debug] JS runtimes: node-24.12.0\n"
            )
            cases = (
                (b"0" * 64 + b"  yt-dlp.exe\n", [version_ok, smoke_ok], "SHA256"),
                (valid_checksums, [subprocess.CompletedProcess([], 0, "2026.06.30\n", "")], "version"),
                (valid_checksums, [version_ok, subprocess.CompletedProcess([], 1, "", "failed")], "smoke"),
                (valid_checksums, [version_ok, subprocess.CompletedProcess([], 0, "", "")], "runtime"),
            )
            for checksums, command_results, error in cases:
                with self.subTest(error=error):
                    with mock.patch.object(publish, "BUILD_DIR", root / error):
                        with mock.patch.object(
                            publish, "_download_bytes", side_effect=[checksums, binary]
                        ):
                            with mock.patch.object(
                                publish.subprocess, "run", side_effect=command_results
                            ):
                                with self.assertRaisesRegex(RuntimeError, error):
                                    publish.prepare_pinned_yt_dlp(node_path)

    def test_v1013_release_contains_only_setup_and_pkg_assets(self):
        setup = Path("YouTubeDownloaderPro-Setup-v1.0.13.exe")
        runtime = Path("node-runtime-win-x64.pkg")
        updater_outputs = (Path("launcher.exe"), Path("worker.exe"), {})

        with mock.patch.object(publish, "clean_build"):
            with mock.patch.object(publish, "prepare_runtime_assets", return_value=runtime):
                with mock.patch.object(
                    publish, "prepare_pinned_yt_dlp", return_value=Path("yt-dlp.exe")
                ):
                    with mock.patch.object(publish, "build_updaters", return_value=updater_outputs):
                        with mock.patch.object(publish, "build_main_app", return_value=Path("app")):
                            with mock.patch.object(
                                publish, "build_installer", return_value=setup, create=True
                            ):
                                assets = publish.build_release_assets("1.0.13")

        self.assertEqual(assets, [setup, runtime])
        self.assertFalse(any(path.suffix.casefold() == ".zip" for path in assets))

    def test_v1014_release_contains_setup_and_smart_package_only(self):
        setup = Path("YouTubeDownloaderPro-Setup-v1.0.14.exe")
        runtime = Path("node-runtime-win-x64.pkg")
        smart = Path("app-update-v2.pkg")
        updater_outputs = (Path("launcher.exe"), Path("worker.exe"), {})

        with mock.patch.object(publish, "clean_build"):
            with mock.patch.object(publish, "prepare_runtime_assets", return_value=runtime):
                with mock.patch.object(
                    publish, "prepare_pinned_yt_dlp", return_value=Path("yt-dlp.exe")
                ):
                    with mock.patch.object(publish, "build_updaters", return_value=updater_outputs):
                        with mock.patch.object(publish, "build_main_app", return_value=Path("app")):
                            with mock.patch.object(publish, "build_installer", return_value=setup):
                                with mock.patch.object(publish, "create_package", return_value=smart):
                                    assets = publish.build_release_assets("1.0.14")

        self.assertEqual(assets, [setup, smart])

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

    def test_installer_desktop_shortcut_task_is_checked_by_default(self):
        script = (publish.REPO_ROOT / "installer.iss").read_text(encoding="utf-8")

        self.assertIn("[Tasks]", script)
        task_line = next(line for line in script.splitlines() if 'Name: "desktopicon"' in line)
        self.assertNotIn("unchecked", task_line.casefold())
        self.assertIn('Name: "{autodesktop}\\YouTube Downloader Pro"', script)
        self.assertIn("Tasks: desktopicon", script)

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

    def test_main_app_uses_only_the_verified_ytdlp_binary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            dist_dir = root / "dist"
            (root / "data").mkdir()
            local_ytdlp = root / "yt-dlp" / "yt-dlp.exe"
            local_ytdlp.parent.mkdir()
            local_ytdlp.write_bytes(b"untrusted workspace binary")
            verified = root / "downloads" / "yt-dlp.exe"
            verified.parent.mkdir()
            verified.write_bytes(b"verified official binary")
            launcher = root / "UpdaterLauncher.exe"
            worker = root / "UpdaterWorker.exe"
            launcher.write_bytes(b"launcher")
            worker.write_bytes(b"worker")
            updater_manifest = {
                "schema_version": 1,
                "protocol_version": 2,
                "worker": {
                    "path": "updater/UpdaterWorker.exe",
                    "sha256": hashlib.sha256(b"worker").hexdigest(),
                    "release_tag": "1.0.15",
                },
            }

            def fake_pyinstaller(*_args, **_kwargs):
                app_dir = dist_dir / publish.APP_NAME
                app_dir.mkdir(parents=True)
                (app_dir / publish.MAIN_EXE_NAME).write_bytes(b"app")

            with mock.patch.object(publish, "REPO_ROOT", root):
                with mock.patch.object(publish, "DIST_DIR", dist_dir):
                    with mock.patch.object(publish, "_run_pyinstaller", side_effect=fake_pyinstaller):
                        app_dir = publish.build_main_app(
                            "1.0.15", (launcher, worker, updater_manifest), verified
                        )

            self.assertEqual(
                (app_dir / "yt-dlp" / "yt-dlp.exe").read_bytes(),
                b"verified official binary",
            )

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
