import hashlib
import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

class UpdaterLauncherTests(unittest.TestCase):
    def setUp(self):
        spec = importlib.util.find_spec("updater_launcher")
        self.assertIsNotNone(spec, "updater_launcher module must exist")
        self.launcher = __import__("updater_launcher")

    def _write_worker_manifest(self, install_dir: Path, worker_bytes=b"worker"):
        worker_path = install_dir / "updater" / "UpdaterWorker-2.0.0.exe"
        worker_path.parent.mkdir(parents=True)
        worker_path.write_bytes(worker_bytes)
        manifest = {
            "schema_version": 1,
            "protocol_version": 2,
            "worker": {
                "path": "updater/UpdaterWorker-2.0.0.exe",
                "sha256": hashlib.sha256(worker_bytes).hexdigest(),
                "release_tag": "1.0.13",
            },
        }
        manifest_path = install_dir / "data" / "updater-manifest.json"
        manifest_path.parent.mkdir(parents=True)
        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        return worker_path

    def test_load_worker_validates_protocol_path_and_hash(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = Path(temp_dir)
            worker_path = self._write_worker_manifest(install_dir)

            selected = self.launcher.load_worker(install_dir)

            self.assertEqual(selected, worker_path)

    def test_load_worker_rejects_hash_mismatch(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = Path(temp_dir)
            worker_path = self._write_worker_manifest(install_dir)
            worker_path.write_bytes(b"tampered")

            with self.assertRaisesRegex(ValueError, "SHA256"):
                self.launcher.load_worker(install_dir)

    def test_launcher_runs_worker_and_removes_superseded_worker(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            install_dir = Path(temp_dir)
            old_worker = self._write_worker_manifest(install_dir, b"old-worker")
            package = install_dir / "app-update-v2.pkg"
            package.write_bytes(b"package")
            new_worker = install_dir / "updater" / "UpdaterWorker-2.1.0.exe"
            new_worker.write_bytes(b"new-worker")
            new_manifest = {
                "schema_version": 1,
                "protocol_version": 2,
                "worker": {
                    "path": "updater/UpdaterWorker-2.1.0.exe",
                    "sha256": hashlib.sha256(b"new-worker").hexdigest(),
                    "release_tag": "1.0.14",
                },
            }

            def run_worker(command, **_kwargs):
                manifest_path = install_dir / "data" / "updater-manifest.json"
                manifest_path.write_text(json.dumps(new_manifest), encoding="utf-8")
                return subprocess.CompletedProcess(command, 0)

            with mock.patch.object(self.launcher.subprocess, "run", side_effect=run_worker):
                result = self.launcher.launch_update(
                    package,
                    install_dir,
                    "YouTube Downloader Pro.exe",
                )

            self.assertEqual(result, 0)
            self.assertFalse(old_worker.exists())
            self.assertTrue(new_worker.exists())


if __name__ == "__main__":
    unittest.main()
