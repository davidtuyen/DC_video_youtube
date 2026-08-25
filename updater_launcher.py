"""Stable bootstrap for selecting and launching a versioned updater worker."""

from __future__ import annotations

import ctypes
import json
import os
import re
import subprocess
import sys
from pathlib import Path

from update_manager import _safe_relative_path, sha256_file


SUPPORTED_PROTOCOL = 2


def load_worker(install_dir: str | os.PathLike[str]) -> Path:
    install_root = Path(install_dir).resolve()
    manifest_path = install_root / "data" / "updater-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported updater manifest schema")
    if manifest.get("protocol_version") != SUPPORTED_PROTOCOL:
        raise ValueError("Unsupported updater protocol")
    worker = manifest.get("worker")
    if not isinstance(worker, dict):
        raise ValueError("Updater worker metadata is missing")
    relative = _safe_relative_path(str(worker.get("path", "")))
    if not relative.parts or relative.parts[0].casefold() != "updater":
        raise ValueError("Updater worker path must be inside updater/")
    worker_path = (install_root / Path(*relative.parts)).resolve()
    if install_root not in worker_path.parents or not worker_path.is_file():
        raise ValueError("Updater worker executable is missing")
    expected_sha256 = str(worker.get("sha256", "")).casefold()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("Updater worker SHA256 is invalid")
    if sha256_file(worker_path) != expected_sha256:
        raise ValueError("Updater worker SHA256 mismatch")
    return worker_path


def launch_update(
    package_path: str | os.PathLike[str],
    install_dir: str | os.PathLike[str],
    main_exe_name: str,
    runtime_package: str | os.PathLike[str] | None = None,
) -> int:
    install_root = Path(install_dir).resolve()
    package = Path(package_path).resolve()
    old_worker = load_worker(install_root)
    command = [str(old_worker), str(package), str(install_root), main_exe_name]
    if runtime_package:
        command.append(str(Path(runtime_package).resolve()))
    completed = subprocess.run(
        command,
        cwd=str(install_root),
        check=False,
    )
    if completed.returncode != 0:
        return int(completed.returncode)
    new_worker = load_worker(install_root)
    if new_worker != old_worker and old_worker.parent == install_root / "updater":
        try:
            old_worker.unlink()
        except OSError:
            pass
    return 0


def _show_error(message: str) -> None:
    if os.name == "nt":
        ctypes.windll.user32.MessageBoxW(None, message, "Updater Launcher", 0x10)
    else:
        print(message, file=sys.stderr)


def main() -> int:
    if len(sys.argv) not in {4, 5}:
        _show_error("Thiếu tham số cập nhật.")
        return 2
    try:
        runtime_package = sys.argv[4] if len(sys.argv) == 5 else None
        return launch_update(sys.argv[1], sys.argv[2], sys.argv[3], runtime_package)
    except Exception as exc:
        _show_error(str(exc))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
