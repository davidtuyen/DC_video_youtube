import hashlib
import importlib.util
import json
import stat
import subprocess
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock


class UpdateManagerTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.find_spec("update_manager")
        self.assertIsNotNone(spec, "update_manager module must exist")
        self.module = __import__("update_manager")

    def test_legacy_embedded_browser_data_is_never_removed_as_stale(self):
        self.assertTrue(
            self.module._is_stale_protected("data/browser/profile/Cookies")
        )

    @staticmethod
    def _write_manifest(base_dir, node_bytes, asset_bytes=b"runtime archive"):
        manifest = {
            "schema_version": 1,
            "release_tag": "v1.0.13",
            "node": {
                "version": "24.12.0",
                "minimum_version": "22.0.0",
                "relative_path": "data/node/node.exe",
                "sha256": hashlib.sha256(node_bytes).hexdigest(),
                "asset_name": "node-runtime-win-x64.zip",
                "asset_sha256": hashlib.sha256(asset_bytes).hexdigest(),
            },
        }
        path = Path(base_dir) / "data" / "runtime-manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path

    @staticmethod
    def _write_v2_manifest(base_dir, node_bytes, license_bytes, asset_bytes=b"runtime archive"):
        manifest = {
            "schema_version": 2,
            "release_tag": "1.0.13",
            "asset": {
                "name": "node-runtime-win-x64.pkg",
                "sha256": hashlib.sha256(asset_bytes).hexdigest(),
                "size": len(asset_bytes),
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
        }
        path = Path(base_dir) / "data" / "runtime-manifest.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(manifest), encoding="utf-8")
        return path

    @staticmethod
    def _successful_runner(command, **_kwargs):
        executable = Path(command[0]).name.lower()
        if executable == "node.exe":
            return subprocess.CompletedProcess(command, 0, "v24.12.0\n", "")
        if "--version" in command:
            return subprocess.CompletedProcess(command, 0, "2026.07.01\n", "")
        return subprocess.CompletedProcess(
            command,
            0,
            "",
            "[debug] JS runtimes: node-24.12.0\n",
        )

    def test_check_runtime_reports_healthy_for_matching_node(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            node_bytes = b"portable-node"
            self._write_manifest(temp_dir, node_bytes)
            node_path = Path(temp_dir) / "data" / "node" / "node.exe"
            node_path.parent.mkdir(parents=True)
            node_path.write_bytes(node_bytes)
            manager = self.module.UpdateManager(
                base_dir=temp_dir,
                repo_owner="owner",
                repo_name="repo",
                command_runner=self._successful_runner,
            )

            status = manager.check_runtime()

            self.assertEqual(status.state, self.module.RuntimeState.HEALTHY)
            self.assertEqual(status.current_version, "24.12.0")

    def test_check_runtime_reports_corrupt_when_v2_license_is_missing_or_changed(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            node_bytes = b"portable-node"
            license_bytes = b"official license"
            self._write_v2_manifest(temp_dir, node_bytes, license_bytes)
            node_dir = Path(temp_dir) / "data" / "node"
            node_dir.mkdir(parents=True)
            (node_dir / "node.exe").write_bytes(node_bytes)
            manager = self.module.UpdateManager(
                base_dir=temp_dir,
                repo_owner="owner",
                repo_name="repo",
                command_runner=self._successful_runner,
            )

            missing = manager.check_runtime()
            (node_dir / "LICENSE").write_bytes(b"tampered")
            changed = manager.check_runtime()

            self.assertEqual(missing.state, self.module.RuntimeState.CORRUPT)
            self.assertIn("license", missing.error.lower())
            self.assertEqual(changed.state, self.module.RuntimeState.CORRUPT)
            self.assertIn("license", changed.error.lower())

    def test_runtime_manifest_v2_requires_complete_file_metadata(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            manifest_path = self._write_v2_manifest(
                temp_dir, b"portable-node", b"official license"
            )
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            manifest["files"] = [manifest["files"][0]]
            manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "LICENSE"):
                self.module.RuntimeManifest.load(manifest_path)

    def test_version_comparison_handles_v_prefix_and_numeric_segments(self):
        self.assertGreater(
            self.module._version_tuple("v24.12.0"),
            self.module._version_tuple("22.0.0"),
        )
        self.assertLess(
            self.module._version_tuple("21.99.99"),
            self.module._version_tuple("22.0.0"),
        )

    def test_check_runtime_reports_missing_and_incompatible(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write_manifest(temp_dir, b"portable-node")
            manager = self.module.UpdateManager(
                base_dir=temp_dir,
                repo_owner="owner",
                repo_name="repo",
                command_runner=self._successful_runner,
            )
            self.assertEqual(manager.check_runtime().state, self.module.RuntimeState.MISSING)

            node_path = Path(temp_dir) / "data" / "node" / "node.exe"
            node_path.parent.mkdir(parents=True)
            node_path.write_bytes(b"portable-node")

            def old_node_runner(command, **_kwargs):
                return subprocess.CompletedProcess(command, 0, "v20.0.0\n", "")

            manager.command_runner = old_node_runner
            self.assertEqual(manager.check_runtime().state, self.module.RuntimeState.INCOMPATIBLE)

    def test_repair_runtime_verifies_archive_and_installs_atomically(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = Path(temp_dir) / "runtime.zip"
            node_bytes = b"repaired-node"
            with zipfile.ZipFile(archive_path, "w") as zf:
                zf.writestr("node.exe", node_bytes)
                zf.writestr("LICENSE", "license")
            archive_bytes = archive_path.read_bytes()
            self._write_manifest(temp_dir, node_bytes, archive_bytes)

            def downloader(_url, destination, **_kwargs):
                Path(destination).write_bytes(archive_bytes)

            manager = self.module.UpdateManager(
                base_dir=temp_dir,
                repo_owner="owner",
                repo_name="repo",
                command_runner=self._successful_runner,
                downloader=downloader,
            )

            result = manager.repair_runtime()

            self.assertTrue(result.success, result.error)
            self.assertEqual(result.changed_components, ("node",))
            self.assertEqual(
                (Path(temp_dir) / "data" / "node" / "node.exe").read_bytes(),
                node_bytes,
            )

    def test_repair_runtime_rejects_v2_asset_without_license(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_path = Path(temp_dir) / "runtime.pkg"
            node_bytes = b"repaired-node"
            license_bytes = b"official license"
            with zipfile.ZipFile(archive_path, "w") as archive:
                archive.writestr("node.exe", node_bytes)
            archive_bytes = archive_path.read_bytes()
            self._write_v2_manifest(
                temp_dir, node_bytes, license_bytes, archive_bytes
            )

            def downloader(_url, destination, **_kwargs):
                Path(destination).write_bytes(archive_bytes)

            manager = self.module.UpdateManager(
                base_dir=temp_dir,
                repo_owner="owner",
                repo_name="repo",
                command_runner=self._successful_runner,
                downloader=downloader,
            )

            result = manager.repair_runtime()

            self.assertFalse(result.success)
            self.assertIn("exactly node.exe and LICENSE", result.error)
            self.assertFalse((Path(temp_dir) / "data" / "node" / "node.exe").exists())

    def test_repair_runtime_bad_checksum_preserves_existing_node(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            old_node = b"old-node"
            self._write_manifest(temp_dir, b"expected-node", b"expected-archive")
            node_path = Path(temp_dir) / "data" / "node" / "node.exe"
            node_path.parent.mkdir(parents=True)
            node_path.write_bytes(old_node)

            def downloader(_url, destination, **_kwargs):
                Path(destination).write_bytes(b"tampered")

            manager = self.module.UpdateManager(
                base_dir=temp_dir,
                repo_owner="owner",
                repo_name="repo",
                command_runner=self._successful_runner,
                downloader=downloader,
            )

            result = manager.repair_runtime()

            self.assertFalse(result.success)
            self.assertEqual(node_path.read_bytes(), old_node)

    def test_update_yt_dlp_repairs_runtime_then_replaces_binary(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            runtime_archive = Path(temp_dir) / "runtime.zip"
            node_bytes = b"portable-node"
            with zipfile.ZipFile(runtime_archive, "w") as zf:
                zf.writestr("node.exe", node_bytes)
            archive_bytes = runtime_archive.read_bytes()
            self._write_manifest(temp_dir, node_bytes, archive_bytes)
            yt_dlp_path = Path(temp_dir) / "yt-dlp" / "yt-dlp.exe"
            yt_dlp_path.parent.mkdir(parents=True)
            yt_dlp_path.write_bytes(b"old-yt-dlp")

            def downloader(url, destination, **_kwargs):
                payload = archive_bytes if "node-runtime" in url else b"new-yt-dlp"
                Path(destination).write_bytes(payload)

            manager = self.module.UpdateManager(
                base_dir=temp_dir,
                repo_owner="owner",
                repo_name="repo",
                command_runner=self._successful_runner,
                downloader=downloader,
            )

            result = manager.update_yt_dlp(
                download_url="https://example.test/yt-dlp.exe",
            )

            self.assertTrue(result.success, result.error)
            self.assertEqual(result.changed_components, ("node", "yt-dlp"))
            self.assertEqual(yt_dlp_path.read_bytes(), b"new-yt-dlp")

    def test_update_yt_dlp_uses_official_checksum_and_offline_smoke(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            node_bytes = b"portable-node"
            self._write_manifest(temp_dir, node_bytes)
            node_path = Path(temp_dir) / "data" / "node" / "node.exe"
            node_path.parent.mkdir(parents=True)
            node_path.write_bytes(node_bytes)
            yt_dlp_bytes = b"verified-yt-dlp"
            smoke_commands = []

            def downloader(url, destination, **_kwargs):
                if url.endswith("SHA2-256SUMS"):
                    checksum = hashlib.sha256(yt_dlp_bytes).hexdigest()
                    Path(destination).write_text(f"{checksum}  yt-dlp.exe\n", encoding="utf-8")
                else:
                    Path(destination).write_bytes(yt_dlp_bytes)

            def runner(command, **_kwargs):
                executable = Path(command[0]).name.lower()
                if executable == "node.exe":
                    return subprocess.CompletedProcess(command, 0, "v24.12.0\n", "")
                if "--version" in command:
                    return subprocess.CompletedProcess(command, 0, "2026.07.01\n", "")
                smoke_commands.append(command)
                return subprocess.CompletedProcess(
                    command,
                    0,
                    "[debug] JS runtimes: node-24.12.0\n",
                    "",
                )

            manager = self.module.UpdateManager(
                base_dir=temp_dir,
                repo_owner="owner",
                repo_name="repo",
                command_runner=runner,
                downloader=downloader,
                proxy_url="http://127.0.0.1:8080",
            )

            result = manager.update_yt_dlp()

            self.assertTrue(result.success, result.error)
            self.assertEqual(
                (Path(temp_dir) / "yt-dlp" / "yt-dlp.exe").read_bytes(),
                yt_dlp_bytes,
            )
            self.assertEqual(len(smoke_commands), 1)
            self.assertIn("--ignore-config", smoke_commands[0])
            self.assertEqual(smoke_commands[0][-2:], ["--", "test:"])
            self.assertNotIn("--proxy", smoke_commands[0])
            self.assertNotIn("--no-update", smoke_commands[0])
            self.assertFalse(any("youtube.com" in argument for argument in smoke_commands[0]))

    def test_update_yt_dlp_rejects_unrelated_nonzero_smoke_failure(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            node_bytes = b"portable-node"
            self._write_manifest(temp_dir, node_bytes)
            node_path = Path(temp_dir) / "data" / "node" / "node.exe"
            node_path.parent.mkdir(parents=True)
            node_path.write_bytes(node_bytes)
            target = Path(temp_dir) / "yt-dlp" / "yt-dlp.exe"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"old-yt-dlp")
            new_bytes = b"new-yt-dlp"

            def downloader(_url, destination, **_kwargs):
                Path(destination).write_bytes(new_bytes)

            def runner(command, **_kwargs):
                if Path(command[0]).name.lower() == "node.exe":
                    return subprocess.CompletedProcess(command, 0, "v24.12.0\n", "")
                if "--version" in command:
                    return subprocess.CompletedProcess(command, 0, "2026.07.01\n", "")
                return subprocess.CompletedProcess(
                    command, 99, "", "[debug] JS runtimes: node-24.12.0\nFATAL internal crash\n"
                )

            manager = self.module.UpdateManager(
                base_dir=temp_dir,
                repo_owner="owner",
                repo_name="repo",
                command_runner=runner,
                downloader=downloader,
            )

            result = manager.update_yt_dlp(
                download_url="https://example.test/yt-dlp.exe",
                expected_sha256=hashlib.sha256(new_bytes).hexdigest(),
            )

            self.assertFalse(result.success)
            self.assertEqual(target.read_bytes(), b"old-yt-dlp")

    def test_update_yt_dlp_rolls_back_runtime_and_license_when_commit_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            old_node = b"corrupt-old-node"
            old_license = b"old-license"
            new_node = b"portable-node"
            runtime_archive_path = Path(temp_dir) / "runtime.zip"
            with zipfile.ZipFile(runtime_archive_path, "w") as archive:
                archive.writestr("node.exe", new_node)
                archive.writestr("LICENSE", b"new-license")
            runtime_archive = runtime_archive_path.read_bytes()
            self._write_manifest(temp_dir, new_node, runtime_archive)
            node_path = Path(temp_dir) / "data" / "node" / "node.exe"
            license_path = node_path.parent / "LICENSE"
            node_path.parent.mkdir(parents=True)
            node_path.write_bytes(old_node)
            license_path.write_bytes(old_license)
            target = Path(temp_dir) / "yt-dlp" / "yt-dlp.exe"
            target.parent.mkdir(parents=True)
            target.write_bytes(b"old-yt-dlp")
            new_yt_dlp = b"new-yt-dlp"

            def downloader(url, destination, **_kwargs):
                payload = runtime_archive if "node-runtime" in url else new_yt_dlp
                Path(destination).write_bytes(payload)

            manager = self.module.UpdateManager(
                base_dir=temp_dir,
                repo_owner="owner",
                repo_name="repo",
                command_runner=self._successful_runner,
                downloader=downloader,
            )
            real_replace = self.module.os.replace
            failed = False

            def fail_yt_dlp_commit(source, destination):
                nonlocal failed
                if not failed and Path(destination) == target and Path(source) != target:
                    failed = True
                    raise OSError("simulated yt-dlp lock")
                return real_replace(source, destination)

            with mock.patch.object(self.module.os, "replace", side_effect=fail_yt_dlp_commit):
                result = manager.update_yt_dlp(
                    download_url="https://example.test/yt-dlp.exe",
                    expected_sha256=hashlib.sha256(new_yt_dlp).hexdigest(),
                )

            self.assertFalse(result.success)
            self.assertTrue(result.rollback_performed)
            self.assertEqual(node_path.read_bytes(), old_node)
            self.assertEqual(license_path.read_bytes(), old_license)
            self.assertEqual(target.read_bytes(), b"old-yt-dlp")

    def test_update_mutex_rejects_a_second_writer(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            first = self.module.UpdateMutex(temp_dir)
            second = self.module.UpdateMutex(temp_dir)
            with first:
                with self.assertRaises(self.module.UpdateBusyError):
                    with second:
                        pass

    def test_update_app_prepares_missing_runtime_without_mutating_install(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            node_bytes = b"portable-node"
            runtime_archive_path = Path(temp_dir) / "runtime.zip"
            with zipfile.ZipFile(runtime_archive_path, "w") as archive:
                archive.writestr("node.exe", node_bytes)
            runtime_archive = runtime_archive_path.read_bytes()
            self._write_manifest(temp_dir, node_bytes, runtime_archive)

            app_payload = b"new-app"
            app_manifest = {
                "schema_version": 1,
                "app_version": "1.0.14",
                "files": [{
                    "path": "app.exe",
                    "sha256": hashlib.sha256(app_payload).hexdigest(),
                    "size": len(app_payload),
                    "required": True,
                }],
            }
            app_zip_path = Path(temp_dir) / "app-update.zip"
            with zipfile.ZipFile(app_zip_path, "w") as archive:
                archive.writestr("app.exe", app_payload)
                archive.writestr("update-manifest.json", json.dumps(app_manifest))
            app_archive = app_zip_path.read_bytes()

            def downloader(url, destination, **_kwargs):
                payload = runtime_archive if "node-runtime" in url else app_archive
                Path(destination).write_bytes(payload)

            manager = self.module.UpdateManager(
                base_dir=temp_dir,
                repo_owner="owner",
                repo_name="repo",
                command_runner=self._successful_runner,
                downloader=downloader,
            )

            result = manager.update_app(
                download_url="https://example.test/update.zip",
                expected_sha256=hashlib.sha256(app_archive).hexdigest(),
                expected_size=len(app_archive),
            )

            self.assertTrue(result.success, result.error)
            self.assertEqual(result.new_version, "1.0.14")
            self.assertEqual(result.changed_components, ("node", "app"))
            self.assertFalse((Path(temp_dir) / "data" / "node" / "node.exe").is_file())
            self.assertTrue(Path(result.runtime_artifact_path).is_file())
            Path(result.artifact_path).unlink()
            Path(result.runtime_artifact_path).unlink()

    def test_update_app_requires_outer_digest_and_size(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            self._write_manifest(temp_dir, b"portable-node")
            manager = self.module.UpdateManager(
                base_dir=temp_dir,
                repo_owner="owner",
                repo_name="repo",
                command_runner=self._successful_runner,
                downloader=mock.Mock(),
            )

            result = manager.update_app(download_url="https://example.test/app.pkg")

            self.assertFalse(result.success)
            self.assertIn("SHA256", result.error)
            manager.downloader.assert_not_called()


class UpdatePackageApplierTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.find_spec("update_manager")
        self.assertIsNotNone(spec, "update_manager module must exist")
        self.module = __import__("update_manager")

    @staticmethod
    def _make_update_zip(zip_path, files, manifest_override=None):
        entries = []
        for relative_path, content in files.items():
            entries.append({
                "path": relative_path,
                "sha256": hashlib.sha256(content).hexdigest(),
                "size": len(content),
                "required": True,
            })
        manifest = manifest_override or {
            "schema_version": 1,
            "app_version": "1.0.13",
            "files": entries,
        }
        with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for relative_path, content in files.items():
                zf.writestr(relative_path, content)
            zf.writestr("update-manifest.json", json.dumps(manifest))

    def test_apply_rejects_partial_runtime_and_preserves_user_json(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = Path(temp_dir) / "install"
            install_dir.mkdir()
            settings_path = install_dir / "data" / "downloader_settings_qt.json"
            settings_path.parent.mkdir()
            settings_path.write_text('{"user": true}', encoding="utf-8")
            zip_path = Path(temp_dir) / "update.zip"
            self._make_update_zip(zip_path, {
                "data/node/node.exe": b"portable-node",
                "data/downloader_settings_qt.json": b'{"user": false}',
                "app.exe": b"new-app",
            })
            applier = self.module.UpdatePackageApplier(
                install_dir=install_dir,
                preserve_relative_paths={"data/downloader_settings_qt.json"},
            )

            result = applier.apply(zip_path)

            self.assertFalse(result.success)
            self.assertIn("runtime is incomplete", result.error)
            self.assertFalse((install_dir / "data" / "node" / "node.exe").exists())
            self.assertEqual(settings_path.read_text(encoding="utf-8"), '{"user": true}')

    def _make_v2_runtime_package(
        self,
        root: Path,
        *,
        node_bytes: bytes,
        license_bytes: bytes,
        app_bytes: bytes = b"new-app",
        minimum_app_version: str = "1.0.15",
    ) -> Path:
        runtime_manifest = {
            "schema_version": 2,
            "release_tag": "1.0.15",
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
        }
        files = {
            "app.exe": app_bytes,
            "data/node/node.exe": node_bytes,
            "data/node/LICENSE": license_bytes,
            "data/runtime-manifest.json": json.dumps(runtime_manifest).encode("utf-8"),
        }
        manifest = {
            "schema_version": 2,
            "app_version": "1.0.16",
            "minimum_app_version": minimum_app_version,
            "files": [
                {
                    "path": path,
                    "sha256": hashlib.sha256(content).hexdigest(),
                    "size": len(content),
                    "required": True,
                    "component": "runtime" if path.startswith("data/") else "app",
                }
                for path, content in files.items()
            ],
        }
        package = root / "app-update-v2.pkg"
        self._make_update_zip(package, files, manifest)
        return package

    def test_apply_rejects_packaged_node_that_cannot_run_before_writing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = Path(temp_dir) / "install"
            install_dir.mkdir()
            (install_dir / "app.exe").write_bytes(b"old-app")
            installed_manifest = install_dir / "data" / "installed-app-manifest.json"
            installed_manifest.parent.mkdir(parents=True)
            installed_manifest.write_text(json.dumps({
                "schema_version": 2,
                "app_version": "1.0.15",
                "minimum_app_version": "1.0.13",
                "files": [{"path": "app.exe", "component": "app"}],
            }), encoding="utf-8")
            package = self._make_v2_runtime_package(
                Path(temp_dir), node_bytes=b"not-an-executable", license_bytes=b"license"
            )

            result = self.module.UpdatePackageApplier(
                install_dir=install_dir,
                command_runner=lambda command, **kwargs: subprocess.CompletedProcess(
                    command, 1, "", "invalid executable"
                ),
            ).apply(package)

            self.assertFalse(result.success)
            self.assertFalse(result.rollback_performed)
            self.assertIn("cannot run", result.error.lower())
            self.assertEqual((install_dir / "app.exe").read_bytes(), b"old-app")
            self.assertFalse((install_dir / "data" / "node" / "node.exe").exists())

    def test_apply_rolls_back_all_files_when_packaged_node_fails_post_verify(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = Path(temp_dir) / "install"
            node_dir = install_dir / "data" / "node"
            node_dir.mkdir(parents=True)
            (install_dir / "app.exe").write_bytes(b"old-app")
            (node_dir / "node.exe").write_bytes(b"old-node")
            (node_dir / "LICENSE").write_bytes(b"old-license")
            installed_manifest = install_dir / "data" / "installed-app-manifest.json"
            installed_manifest.write_text(json.dumps({
                "schema_version": 2,
                "app_version": "1.0.15",
                "minimum_app_version": "1.0.13",
                "files": [{"path": "app.exe", "component": "app"}],
            }), encoding="utf-8")
            package = self._make_v2_runtime_package(
                Path(temp_dir), node_bytes=b"new-node", license_bytes=b"new-license"
            )

            def runner(command, **_kwargs):
                executable = Path(command[0])
                if ".update-staging-" in str(executable):
                    return subprocess.CompletedProcess(command, 0, "v24.12.0\n", "")
                return subprocess.CompletedProcess(command, 1, "", "post-check failed")

            result = self.module.UpdatePackageApplier(
                install_dir=install_dir,
                command_runner=runner,
            ).apply(package)

            self.assertFalse(result.success)
            self.assertTrue(result.rollback_performed)
            self.assertEqual((install_dir / "app.exe").read_bytes(), b"old-app")
            self.assertEqual((node_dir / "node.exe").read_bytes(), b"old-node")
            self.assertEqual((node_dir / "LICENSE").read_bytes(), b"old-license")

    def test_apply_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = Path(temp_dir) / "install"
            install_dir.mkdir()
            zip_path = Path(temp_dir) / "update.zip"
            self._make_update_zip(zip_path, {"../outside.exe": b"bad"})
            applier = self.module.UpdatePackageApplier(install_dir=install_dir)

            result = applier.apply(zip_path)

            self.assertFalse(result.success)
            self.assertFalse((Path(temp_dir) / "outside.exe").exists())

    def test_apply_rejects_windows_unsafe_paths(self):
        unsafe_paths = (
            "data/app.exe:stream",
            "data/CON",
            "data/com1.txt",
            "data/file. ",
            "a/C:/outside.exe",
            "//server/share/file.exe",
        )
        for unsafe_path in unsafe_paths:
            with self.subTest(path=unsafe_path), tempfile.TemporaryDirectory() as temp_dir:
                install_dir = Path(temp_dir) / "install"
                install_dir.mkdir()
                zip_path = Path(temp_dir) / "update.pkg"
                self._make_update_zip(zip_path, {unsafe_path: b"bad"})

                result = self.module.UpdatePackageApplier(install_dir=install_dir).apply(zip_path)

                self.assertFalse(result.success)
                self.assertIn("unsafe", result.error.lower())

    def test_apply_rejects_zip_symlink(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = Path(temp_dir) / "install"
            install_dir.mkdir()
            zip_path = Path(temp_dir) / "update.pkg"
            payload = b"target.exe"
            manifest = {
                "schema_version": 1,
                "app_version": "1.0.13",
                "files": [{
                    "path": "link.exe",
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size": len(payload),
                    "required": True,
                }],
            }
            link = zipfile.ZipInfo("link.exe")
            link.create_system = 3
            link.external_attr = (stat.S_IFLNK | 0o777) << 16
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr(link, payload)
                archive.writestr("update-manifest.json", json.dumps(manifest))

            result = self.module.UpdatePackageApplier(install_dir=install_dir).apply(zip_path)

            self.assertFalse(result.success)
            self.assertIn("symlink", result.error.lower())

    def test_apply_rejects_suspicious_compression_ratio(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = Path(temp_dir) / "install"
            install_dir.mkdir()
            zip_path = Path(temp_dir) / "update.pkg"
            self._make_update_zip(zip_path, {"huge.txt": b"0" * (2 * 1024 * 1024)})

            result = self.module.UpdatePackageApplier(install_dir=install_dir).apply(zip_path)

            self.assertFalse(result.success)
            self.assertIn("compression ratio", result.error.lower())

    def test_apply_rejects_case_insensitive_duplicate_paths(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = Path(temp_dir) / "install"
            install_dir.mkdir()
            zip_path = Path(temp_dir) / "update.zip"
            payload = b"app"
            manifest = {
                "schema_version": 1,
                "app_version": "1.0.13",
                "files": [{
                    "path": "App.exe",
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size": len(payload),
                    "required": True,
                }],
            }
            with zipfile.ZipFile(zip_path, "w") as archive:
                archive.writestr("App.exe", payload)
                archive.writestr("app.exe", payload)
                archive.writestr("update-manifest.json", json.dumps(manifest))

            result = self.module.UpdatePackageApplier(install_dir=install_dir).apply(zip_path)

            self.assertFalse(result.success)
            self.assertIn("duplicate", result.error)

    def test_apply_bad_checksum_changes_nothing(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = Path(temp_dir) / "install"
            install_dir.mkdir()
            app_path = install_dir / "app.exe"
            app_path.write_bytes(b"old-app")
            zip_path = Path(temp_dir) / "update.zip"
            manifest = {
                "schema_version": 1,
                "app_version": "1.0.13",
                "files": [{
                    "path": "app.exe",
                    "sha256": "0" * 64,
                    "size": 7,
                    "required": True,
                }],
            }
            self._make_update_zip(zip_path, {"app.exe": b"new-app"}, manifest)
            applier = self.module.UpdatePackageApplier(install_dir=install_dir)

            result = applier.apply(zip_path)

            self.assertFalse(result.success)
            self.assertEqual(app_path.read_bytes(), b"old-app")

    def test_apply_rolls_back_all_files_when_replace_fails_mid_update(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = Path(temp_dir) / "install"
            install_dir.mkdir()
            first_path = install_dir / "first.exe"
            second_path = install_dir / "second.exe"
            first_path.write_bytes(b"old-first")
            second_path.write_bytes(b"old-second")
            zip_path = Path(temp_dir) / "update.zip"
            self._make_update_zip(zip_path, {
                "first.exe": b"new-first",
                "second.exe": b"new-second",
            })
            real_replace = self.module.os.replace
            failed_once = False

            def flaky_replace(source, destination):
                nonlocal failed_once
                source_path = Path(source)
                destination_path = Path(destination)
                if (
                    not failed_once
                    and source_path.name == "second.exe"
                    and destination_path == second_path
                ):
                    failed_once = True
                    raise OSError("simulated locked file")
                return real_replace(source, destination)

            applier = self.module.UpdatePackageApplier(install_dir=install_dir)
            with mock.patch.object(self.module.os, "replace", side_effect=flaky_replace):
                result = applier.apply(zip_path)

            self.assertFalse(result.success)
            self.assertEqual(first_path.read_bytes(), b"old-first")
            self.assertEqual(second_path.read_bytes(), b"old-second")

    def test_apply_removes_only_stale_managed_app_files(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = Path(temp_dir) / "install"
            old_app = install_dir / "_internal" / "old-module.dll"
            old_app.parent.mkdir(parents=True)
            old_app.write_bytes(b"old-module")
            settings = install_dir / "data" / "downloader_settings_qt.json"
            settings.parent.mkdir(parents=True)
            settings.write_bytes(b"user-settings")
            installed_manifest = install_dir / "data" / "installed-app-manifest.json"
            installed_manifest.write_text(json.dumps({
                "schema_version": 2,
                "app_version": "1.0.13",
                "minimum_app_version": "1.0.13",
                "files": [
                    {"path": "_internal/old-module.dll", "component": "app"},
                    {"path": "data/downloader_settings_qt.json", "component": "app"},
                ],
            }), encoding="utf-8")
            package = Path(temp_dir) / "app-update-v2.pkg"
            payload = b"new-app"
            manifest = {
                "schema_version": 2,
                "app_version": "1.0.14",
                "minimum_app_version": "1.0.13",
                "files": [{
                    "path": "app.exe",
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size": len(payload),
                    "required": True,
                    "component": "app",
                }],
            }
            self._make_update_zip(package, {"app.exe": payload}, manifest)

            result = self.module.UpdatePackageApplier(install_dir=install_dir).apply(package)

            self.assertTrue(result.success, result.error)
            self.assertFalse(old_app.exists())
            self.assertEqual(settings.read_bytes(), b"user-settings")
            recorded = json.loads(installed_manifest.read_text(encoding="utf-8"))
            self.assertEqual(recorded["app_version"], "1.0.14")

    def test_apply_preserves_managed_browser_profile_database_and_cache(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = Path(temp_dir) / "install"
            cookie_db = (
                install_dir
                / "data"
                / "browser"
                / "chrome-user-data"
                / "Default"
                / "Network"
                / "Cookies"
            )
            cache_entry = cookie_db.parents[1] / "Cache" / "cache-entry"
            cookie_db.parent.mkdir(parents=True)
            cache_entry.parent.mkdir(parents=True)
            cookie_db.write_bytes(b"login database")
            cache_entry.write_bytes(b"browser cache")

            installed_manifest = install_dir / "data" / "installed-app-manifest.json"
            installed_manifest.write_text(json.dumps({
                "schema_version": 2,
                "app_version": "1.0.13",
                "minimum_app_version": "1.0.13",
                "files": [
                    {
                        "path": "data/browser/chrome-user-data/Default/Network/Cookies",
                        "component": "app",
                    },
                    {
                        "path": "data/browser/chrome-user-data/Default/Cache/cache-entry",
                        "component": "app",
                    },
                ],
            }), encoding="utf-8")

            package = Path(temp_dir) / "app-update-v2.pkg"
            payload = b"new-app"
            manifest = {
                "schema_version": 2,
                "app_version": "1.0.14",
                "minimum_app_version": "1.0.13",
                "files": [{
                    "path": "app.exe",
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size": len(payload),
                    "required": True,
                    "component": "app",
                }],
            }
            self._make_update_zip(package, {"app.exe": payload}, manifest)

            result = self.module.UpdatePackageApplier(
                install_dir=install_dir
            ).apply(package)

            self.assertTrue(result.success, result.error)
            self.assertEqual(cookie_db.read_bytes(), b"login database")
            self.assertEqual(cache_entry.read_bytes(), b"browser cache")

    def test_package_cannot_replace_managed_browser_profile(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = Path(temp_dir) / "install"
            cookie_db = (
                install_dir
                / "data"
                / "browser"
                / "chrome-user-data"
                / "Default"
                / "Network"
                / "Cookies"
            )
            cookie_db.parent.mkdir(parents=True)
            cookie_db.write_bytes(b"real login database")
            installed_manifest = install_dir / "data" / "installed-app-manifest.json"
            installed_manifest.write_text(json.dumps({
                "schema_version": 2,
                "app_version": "1.0.15",
                "minimum_app_version": "1.0.13",
                "files": [],
            }), encoding="utf-8")

            package = Path(temp_dir) / "malicious.pkg"
            replacement = b"package-controlled database"
            manifest = {
                "schema_version": 2,
                "app_version": "1.0.16",
                "minimum_app_version": "1.0.13",
                "files": [{
                    "path": "data/browser/chrome-user-data/Default/Network/Cookies",
                    "sha256": hashlib.sha256(replacement).hexdigest(),
                    "size": len(replacement),
                    "required": True,
                    "component": "app",
                }],
            }
            self._make_update_zip(
                package,
                {"data/browser/chrome-user-data/Default/Network/Cookies": replacement},
                manifest,
            )

            result = self.module.UpdatePackageApplier(
                install_dir=install_dir
            ).apply(package)

            self.assertFalse(result.success)
            self.assertIn("protected", result.error.casefold())
            self.assertEqual(cookie_db.read_bytes(), b"real login database")

    def test_apply_never_removes_stable_updater_launcher_as_stale(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = Path(temp_dir) / "install"
            launcher = install_dir / "UpdaterLauncher.exe"
            launcher.parent.mkdir(parents=True)
            launcher.write_bytes(b"stable-launcher")
            installed_manifest = install_dir / "data" / "installed-app-manifest.json"
            installed_manifest.parent.mkdir(parents=True)
            installed_manifest.write_text(json.dumps({
                "schema_version": 2,
                "app_version": "1.0.13",
                "minimum_app_version": "1.0.13",
                "files": [{"path": "UpdaterLauncher.exe", "component": "app"}],
            }), encoding="utf-8")
            package = Path(temp_dir) / "app-update-v2.pkg"
            payload = b"new-app"
            manifest = {
                "schema_version": 2,
                "app_version": "1.0.14",
                "minimum_app_version": "1.0.13",
                "files": [{
                    "path": "app.exe",
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size": len(payload),
                    "required": True,
                    "component": "app",
                }],
            }
            self._make_update_zip(package, {"app.exe": payload}, manifest)

            result = self.module.UpdatePackageApplier(install_dir=install_dir).apply(package)

            self.assertTrue(result.success, result.error)
            self.assertEqual(launcher.read_bytes(), b"stable-launcher")

    def test_apply_restores_stale_file_when_later_replace_fails(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = Path(temp_dir) / "install"
            stale = install_dir / "old.dll"
            stale.parent.mkdir(parents=True)
            stale.write_bytes(b"old")
            installed_manifest = install_dir / "data" / "installed-app-manifest.json"
            installed_manifest.parent.mkdir(parents=True)
            installed_manifest.write_text(json.dumps({
                "schema_version": 2,
                "app_version": "1.0.13",
                "minimum_app_version": "1.0.13",
                "files": [{"path": "old.dll", "component": "app"}],
            }), encoding="utf-8")
            package = Path(temp_dir) / "app-update-v2.pkg"
            payload = b"new"
            manifest = {
                "schema_version": 2,
                "app_version": "1.0.14",
                "minimum_app_version": "1.0.13",
                "files": [{
                    "path": "app.exe",
                    "sha256": hashlib.sha256(payload).hexdigest(),
                    "size": len(payload),
                    "required": True,
                    "component": "app",
                }],
            }
            self._make_update_zip(package, {"app.exe": payload}, manifest)
            real_replace = self.module.os.replace
            failed = False

            def fail_app(source, destination):
                nonlocal failed
                if not failed and Path(destination) == install_dir / "app.exe":
                    failed = True
                    raise OSError("simulated app lock")
                return real_replace(source, destination)

            with mock.patch.object(self.module.os, "replace", side_effect=fail_app):
                result = self.module.UpdatePackageApplier(install_dir=install_dir).apply(package)

            self.assertFalse(result.success)
            self.assertTrue(result.rollback_performed)
            self.assertEqual(stale.read_bytes(), b"old")

    def test_apply_commits_prepared_runtime_with_app_in_one_transaction(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = Path(temp_dir) / "install"
            node_bytes = b"portable-node"
            runtime_package = Path(temp_dir) / "node-runtime.pkg"
            with zipfile.ZipFile(runtime_package, "w") as archive:
                archive.writestr("node.exe", node_bytes)
                archive.writestr("LICENSE", b"new-license")
            self._make_update_zip(
                Path(temp_dir) / "unused.pkg",
                {"placeholder": b"unused"},
            )
            runtime_manifest = {
                "schema_version": 1,
                "release_tag": "1.0.13",
                "node": {
                    "version": "24.12.0",
                    "minimum_version": "22.0.0",
                    "relative_path": "data/node/node.exe",
                    "sha256": hashlib.sha256(node_bytes).hexdigest(),
                    "asset_name": "node-runtime.pkg",
                    "asset_sha256": hashlib.sha256(runtime_package.read_bytes()).hexdigest(),
                },
            }
            runtime_manifest_path = install_dir / "data" / "runtime-manifest.json"
            runtime_manifest_path.parent.mkdir(parents=True)
            runtime_manifest_path.write_text(json.dumps(runtime_manifest), encoding="utf-8")
            (install_dir / "data" / "installed-app-manifest.json").write_text(json.dumps({
                "schema_version": 2,
                "app_version": "1.0.13",
                "minimum_app_version": "1.0.13",
                "files": [],
            }), encoding="utf-8")
            app_payload = b"new-app"
            package = Path(temp_dir) / "app-update-v2.pkg"
            manifest = {
                "schema_version": 2,
                "app_version": "1.0.14",
                "minimum_app_version": "1.0.13",
                "files": [{
                    "path": "app.exe",
                    "sha256": hashlib.sha256(app_payload).hexdigest(),
                    "size": len(app_payload),
                    "required": True,
                    "component": "app",
                }],
            }
            self._make_update_zip(package, {"app.exe": app_payload}, manifest)

            result = self.module.UpdatePackageApplier(
                install_dir=install_dir,
                command_runner=UpdateManagerTests._successful_runner,
            ).apply(package, runtime_package=runtime_package)

            self.assertTrue(result.success, result.error)
            self.assertEqual((install_dir / "app.exe").read_bytes(), app_payload)
            self.assertEqual((install_dir / "data" / "node" / "node.exe").read_bytes(), node_bytes)
            self.assertEqual((install_dir / "data" / "node" / "LICENSE").read_bytes(), b"new-license")

    def test_create_runtime_asset_is_deterministic_and_writes_manifest(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            node_dir = Path(temp_dir) / "node"
            node_dir.mkdir()
            node_bytes = b"portable-node"
            (node_dir / "node.exe").write_bytes(node_bytes)
            (node_dir / "LICENSE").write_text("license", encoding="utf-8")
            first_zip = Path(temp_dir) / "first.zip"
            second_zip = Path(temp_dir) / "second.zip"
            manifest_path = Path(temp_dir) / "runtime-manifest.json"

            first = self.module.create_runtime_asset(
                node_dir=node_dir,
                output_zip=first_zip,
                manifest_path=manifest_path,
                release_tag="v1.0.13",
                node_version="24.12.0",
            )
            second = self.module.create_runtime_asset(
                node_dir=node_dir,
                output_zip=second_zip,
                manifest_path=manifest_path,
                release_tag="v1.0.13",
                node_version="24.12.0",
            )

            self.assertEqual(first_zip.read_bytes(), second_zip.read_bytes())
            self.assertEqual(first["schema_version"], 2)
            self.assertEqual(first["node"]["sha256"], hashlib.sha256(node_bytes).hexdigest())
            self.assertEqual(first["asset"]["sha256"], second["asset"]["sha256"])
            self.assertEqual(
                {entry["path"] for entry in first["files"]},
                {"node.exe", "LICENSE"},
            )
            self.assertEqual(json.loads(manifest_path.read_text(encoding="utf-8")), second)


if __name__ == "__main__":
    unittest.main()
