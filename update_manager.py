"""Shared update infrastructure for the app, Node runtime, and yt-dlp."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import stat
import subprocess
import tempfile
import threading
import zipfile
import ctypes
from dataclasses import dataclass
from enum import Enum
from pathlib import Path, PurePosixPath
from typing import Callable, Iterable

import requests


ProgressCallback = Callable[[int, int], None]
StatusCallback = Callable[[str], None]
Downloader = Callable[..., None]
CommandRunner = Callable[..., subprocess.CompletedProcess]


class RuntimeState(str, Enum):
    HEALTHY = "healthy"
    MISSING = "missing"
    CORRUPT = "corrupt"
    INCOMPATIBLE = "incompatible"
    ERROR = "error"


@dataclass(frozen=True)
class RuntimeStatus:
    state: RuntimeState
    path: Path
    current_version: str | None = None
    required_version: str | None = None
    error: str = ""


@dataclass(frozen=True)
class UpdateResult:
    success: bool
    component: str
    old_version: str | None = None
    new_version: str | None = None
    changed_components: tuple[str, ...] = ()
    error: str = ""
    message: str = ""
    artifact_path: str | None = None
    runtime_artifact_path: str | None = None
    stage: str = ""
    rollback_performed: bool = False


@dataclass(frozen=True)
class ReleaseAsset:
    name: str
    url: str
    sha256: str
    size: int


class UpdateBusyError(RuntimeError):
    """Raised when another updater owns the installation mutex."""


_MUTEX_GUARD = threading.Lock()
_HELD_MUTEXES: set[str] = set()


class UpdateMutex:
    """Non-blocking process/thread mutex keyed by the installation directory."""

    def __init__(self, install_dir: str | os.PathLike[str]):
        resolved = str(Path(install_dir).resolve()).casefold()
        token = hashlib.sha256(resolved.encode("utf-8")).hexdigest()[:24]
        self.name = rf"Local\YouTubeDownloaderPro.Update.{token}"
        self._handle = None

    def __enter__(self):
        with _MUTEX_GUARD:
            if self.name in _HELD_MUTEXES:
                raise UpdateBusyError("Another update operation is already running")
            _HELD_MUTEXES.add(self.name)
        try:
            if os.name == "nt":
                kernel32 = ctypes.windll.kernel32
                handle = kernel32.CreateMutexW(None, False, self.name)
                if not handle:
                    raise OSError(ctypes.get_last_error(), "CreateMutexW failed")
                wait_result = kernel32.WaitForSingleObject(handle, 0)
                if wait_result != 0:  # WAIT_OBJECT_0
                    kernel32.CloseHandle(handle)
                    raise UpdateBusyError("Another update process is already running")
                self._handle = handle
            return self
        except Exception:
            with _MUTEX_GUARD:
                _HELD_MUTEXES.discard(self.name)
            raise

    def __exit__(self, _exc_type, _exc, _tb):
        try:
            if self._handle is not None:
                kernel32 = ctypes.windll.kernel32
                kernel32.ReleaseMutex(self._handle)
                kernel32.CloseHandle(self._handle)
                self._handle = None
        finally:
            with _MUTEX_GUARD:
                _HELD_MUTEXES.discard(self.name)


class _TransactionError(RuntimeError):
    def __init__(self, message: str, *, rollback_performed: bool):
        super().__init__(message)
        self.rollback_performed = rollback_performed


@dataclass(frozen=True)
class RuntimeManifest:
    schema_version: int
    release_tag: str
    node_version: str
    minimum_version: str
    relative_path: str
    sha256: str
    asset_name: str
    asset_sha256: str
    asset_size: int | None = None
    node_size: int | None = None
    license_sha256: str | None = None
    license_size: int | None = None

    @classmethod
    def load(cls, path: str | os.PathLike[str]) -> "RuntimeManifest":
        return cls.from_data(json.loads(Path(path).read_text(encoding="utf-8")))

    @classmethod
    def from_data(cls, data: dict) -> "RuntimeManifest":
        schema_version = data.get("schema_version")
        if schema_version not in {1, 2} or not isinstance(data.get("node"), dict):
            raise ValueError("runtime-manifest.json has an unsupported schema")
        node = data["node"]
        required = ("version", "minimum_version", "relative_path", "sha256")
        missing = [key for key in required if not node.get(key)]
        if missing or not data.get("release_tag"):
            raise ValueError(f"runtime manifest is missing: {', '.join(missing)}")
        if schema_version == 1:
            asset_name = str(node.get("asset_name", ""))
            asset_sha256 = str(node.get("asset_sha256", "")).lower()
            asset_size = None
            node_size = None
            license_sha256 = None
            license_size = None
        else:
            asset = data.get("asset")
            files = data.get("files")
            if not isinstance(asset, dict) or not isinstance(files, list):
                raise ValueError("runtime manifest v2 asset metadata is missing")
            asset_name = str(asset.get("name", ""))
            asset_sha256 = str(asset.get("sha256", "")).lower()
            asset_size = int(asset.get("size", 0))
            file_metadata: dict[str, tuple[str, int]] = {}
            for entry in files:
                if not isinstance(entry, dict):
                    raise ValueError("runtime manifest v2 file metadata is invalid")
                relative = str(entry.get("path", ""))
                digest = str(entry.get("sha256", "")).lower()
                try:
                    size = int(entry.get("size", -1))
                except (TypeError, ValueError) as exc:
                    raise ValueError("runtime manifest v2 file size is invalid") from exc
                if (
                    relative in file_metadata
                    or relative not in {"node.exe", "LICENSE"}
                    or not re.fullmatch(r"[0-9a-f]{64}", digest)
                    or size <= 0
                ):
                    raise ValueError("runtime manifest v2 file metadata is invalid")
                file_metadata[relative] = (digest, size)
            missing_files = {"node.exe", "LICENSE"} - set(file_metadata)
            if missing_files:
                raise ValueError(
                    "runtime manifest v2 is missing file metadata: "
                    + ", ".join(sorted(missing_files))
                )
            node_file_sha256, node_size = file_metadata["node.exe"]
            license_sha256, license_size = file_metadata["LICENSE"]
            if node_file_sha256 != str(node.get("sha256", "")).lower():
                raise ValueError("runtime manifest node.exe hashes disagree")
        if (
            not asset_name
            or not re.fullmatch(r"[0-9a-f]{64}", asset_sha256)
            or (schema_version == 2 and (asset_size is None or asset_size <= 0))
        ):
            raise ValueError("runtime manifest asset metadata is invalid")
        return cls(
            schema_version=int(schema_version),
            release_tag=str(data["release_tag"]),
            node_version=str(node["version"]),
            minimum_version=str(node["minimum_version"]),
            relative_path=str(node["relative_path"]).replace("\\", "/"),
            sha256=str(node["sha256"]).lower(),
            asset_name=asset_name,
            asset_sha256=asset_sha256,
            asset_size=asset_size,
            node_size=node_size,
            license_sha256=license_sha256,
            license_size=license_size,
        )


def sha256_file(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _version_tuple(value: str) -> tuple[int, ...]:
    match = re.search(r"(\d+)(?:\.(\d+))?(?:\.(\d+))?", value or "")
    if not match:
        raise ValueError(f"invalid version: {value!r}")
    return tuple(int(part or 0) for part in match.groups())


def _verify_runtime_files(
    manifest: RuntimeManifest,
    node_path: Path,
    license_path: Path,
    command_runner: CommandRunner,
    *,
    context: str,
) -> str:
    if not node_path.is_file():
        raise ValueError(f"{context} is missing node.exe")
    if manifest.node_size is not None and node_path.stat().st_size != manifest.node_size:
        raise ValueError(f"{context} node.exe size mismatch")
    if sha256_file(node_path) != manifest.sha256:
        raise ValueError(f"{context} node.exe SHA256 mismatch")
    if manifest.schema_version == 2:
        if not license_path.is_file():
            raise ValueError(f"{context} is missing LICENSE")
        if manifest.license_size is None or license_path.stat().st_size != manifest.license_size:
            raise ValueError(f"{context} LICENSE size mismatch")
        if not manifest.license_sha256 or sha256_file(license_path) != manifest.license_sha256:
            raise ValueError(f"{context} LICENSE SHA256 mismatch")
    result = command_runner([str(node_path), "--version"])
    if result.returncode != 0:
        detail = (result.stderr or "unknown execution error").strip()
        raise RuntimeError(f"{context} Node cannot run: {detail}")
    current_version = (result.stdout or "").strip().lstrip("v")
    if _version_tuple(current_version) < _version_tuple(manifest.minimum_version):
        raise RuntimeError(
            f"{context} Node {current_version} is below {manifest.minimum_version}"
        )
    if (
        manifest.schema_version == 2
        and _version_tuple(current_version) != _version_tuple(manifest.node_version)
    ):
        raise RuntimeError(
            f"{context} Node version {current_version} does not match {manifest.node_version}"
        )
    return current_version


def _safe_relative_path(value: str) -> PurePosixPath:
    normalized = value.replace("\\", "/")
    if (
        not normalized
        or normalized.startswith("/")
        or any(ord(character) < 32 for character in normalized)
    ):
        raise ValueError(f"unsafe update path: {value}")
    raw_parts = normalized.split("/")
    if any(not part or part in {".", ".."} for part in raw_parts):
        raise ValueError(f"unsafe update path: {value}")
    reserved = {"CON", "PRN", "AUX", "NUL"}
    reserved.update(f"COM{number}" for number in range(1, 10))
    reserved.update(f"LPT{number}" for number in range(1, 10))
    for part in raw_parts:
        if ":" in part or part.endswith((" ", ".")):
            raise ValueError(f"unsafe update path: {value}")
        stem = part.split(".", 1)[0].rstrip(" .").upper()
        if stem in reserved:
            raise ValueError(f"unsafe update path: {value}")
    path = PurePosixPath(normalized)
    if path.is_absolute() or not path.parts:
        raise ValueError(f"unsafe update path: {value}")
    return path


def _canonical_windows_path(value: str) -> str:
    path = _safe_relative_path(value)
    return "/".join(part.casefold() for part in path.parts)


MAX_ARCHIVE_FILES = 10_000
MAX_ARCHIVE_UNCOMPRESSED = 1024 * 1024 * 1024
MAX_ARCHIVE_FILE_SIZE = 512 * 1024 * 1024
MAX_ARCHIVE_RATIO = 100
MAX_MANIFEST_SIZE = 4 * 1024 * 1024


def _validate_zip_members(archive: zipfile.ZipFile) -> dict[str, zipfile.ZipInfo]:
    members: dict[str, zipfile.ZipInfo] = {}
    canonical_names: set[str] = set()
    total_size = 0
    file_count = 0
    for member in archive.infolist():
        if member.is_dir():
            continue
        file_count += 1
        if file_count > MAX_ARCHIVE_FILES:
            raise ValueError("update archive contains too many files")
        name = str(_safe_relative_path(member.filename))
        canonical = _canonical_windows_path(name)
        if canonical in canonical_names:
            raise ValueError(f"duplicate update path: {name}")
        canonical_names.add(canonical)
        unix_mode = member.external_attr >> 16
        if member.create_system == 3 and stat.S_ISLNK(unix_mode):
            raise ValueError(f"ZIP symlink is not allowed: {name}")
        if member.file_size > MAX_ARCHIVE_FILE_SIZE:
            raise ValueError(f"update file is too large: {name}")
        total_size += member.file_size
        if total_size > MAX_ARCHIVE_UNCOMPRESSED:
            raise ValueError("update archive exceeds the uncompressed size limit")
        if (
            member.file_size >= 1024 * 1024
            and member.compress_size > 0
            and member.file_size / member.compress_size > MAX_ARCHIVE_RATIO
        ):
            raise ValueError(f"suspicious compression ratio: {name}")
        members[name] = member
    return members


def _hash_zip_member(archive: zipfile.ZipFile, member: zipfile.ZipInfo) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    with archive.open(member) as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return digest.hexdigest(), size


def _atomic_replace_files(
    replacements: Iterable[tuple[Path, Path]],
    *,
    deletions: Iterable[Path] = (),
    verify: Callable[[], None] | None = None,
) -> None:
    replacements = list(replacements)
    deletions = list(deletions)
    if not replacements and not deletions:
        if verify:
            verify()
        return
    backup_root = Path(tempfile.mkdtemp(prefix="update_transaction_backup_"))
    applied: list[tuple[Path, Path | None]] = []
    try:
        for index, target in enumerate(deletions):
            if not target.exists():
                continue
            backup = backup_root / f"deleted-{index}"
            backup.parent.mkdir(parents=True, exist_ok=True)
            os.replace(target, backup)
            applied.append((target, backup))
        for index, (staged, target) in enumerate(replacements):
            target.parent.mkdir(parents=True, exist_ok=True)
            backup = None
            if target.exists():
                backup = backup_root / f"replaced-{index}"
                os.replace(target, backup)
            applied.append((target, backup))
            os.replace(staged, target)
        if verify:
            verify()
    except Exception as exc:
        rollback_errors = []
        for target, backup in reversed(applied):
            try:
                if target.exists():
                    target.unlink()
                if backup is not None and backup.exists():
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(backup, target)
            except OSError as rollback_exc:
                rollback_errors.append(str(rollback_exc))
        if rollback_errors:
            raise _TransactionError(
                f"{exc}; rollback incomplete: {'; '.join(rollback_errors)}; backup: {backup_root}",
                rollback_performed=False,
            ) from exc
        shutil.rmtree(backup_root, ignore_errors=True)
        raise _TransactionError(str(exc), rollback_performed=True) from exc
    shutil.rmtree(backup_root, ignore_errors=True)


def _default_command_runner(command, **kwargs):
    defaults = {
        "capture_output": True,
        "text": True,
        "encoding": "utf-8",
        "errors": "replace",
        "timeout": 30,
    }
    defaults.update(kwargs)
    if os.name == "nt":
        defaults.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
    return subprocess.run(command, **defaults)


def _default_downloader(
    url: str,
    destination: str | os.PathLike[str],
    *,
    progress_callback: ProgressCallback | None = None,
    proxy_url: str | None = None,
) -> None:
    proxies = {"http": proxy_url, "https": proxy_url} if proxy_url else None
    with requests.get(url, stream=True, timeout=30, proxies=proxies) as response:
        response.raise_for_status()
        total = int(response.headers.get("Content-Length", "0") or 0)
        downloaded = 0
        with open(destination, "wb") as handle:
            for chunk in response.iter_content(chunk_size=256 * 1024):
                if not chunk:
                    continue
                handle.write(chunk)
                downloaded += len(chunk)
                if progress_callback:
                    progress_callback(downloaded, total)


class UpdateManager:
    """Coordinate updates while keeping UI and network concerns injectable."""

    def __init__(
        self,
        *,
        base_dir: str | os.PathLike[str],
        repo_owner: str,
        repo_name: str,
        manifest_path: str | os.PathLike[str] | None = None,
        command_runner: CommandRunner = _default_command_runner,
        downloader: Downloader = _default_downloader,
        status_callback: StatusCallback | None = None,
        progress_callback: ProgressCallback | None = None,
        proxy_url: str | None = None,
    ):
        self.base_dir = Path(base_dir).resolve()
        self.repo_owner = repo_owner
        self.repo_name = repo_name
        self.manifest_path = Path(manifest_path) if manifest_path else self.base_dir / "data" / "runtime-manifest.json"
        self.command_runner = command_runner
        self.downloader = downloader
        self.status_callback = status_callback or (lambda _message: None)
        self.progress_callback = progress_callback
        self.proxy_url = proxy_url

    def _manifest(self) -> RuntimeManifest:
        return RuntimeManifest.load(self.manifest_path)

    def _runtime_path(self, manifest: RuntimeManifest) -> Path:
        relative = _safe_relative_path(manifest.relative_path)
        path = (self.base_dir / Path(*relative.parts)).resolve()
        if self.base_dir != path and self.base_dir not in path.parents:
            raise ValueError("runtime path escapes the application directory")
        return path

    def check_runtime(self) -> RuntimeStatus:
        try:
            manifest = self._manifest()
            node_path = self._runtime_path(manifest)
            if not node_path.is_file():
                return RuntimeStatus(RuntimeState.MISSING, node_path, required_version=manifest.minimum_version)
            if sha256_file(node_path) != manifest.sha256:
                return RuntimeStatus(
                    RuntimeState.CORRUPT,
                    node_path,
                    required_version=manifest.minimum_version,
                    error="Node SHA256 does not match runtime manifest",
                )
            license_path = node_path.parent / "LICENSE"
            if manifest.schema_version == 2 and (
                not license_path.is_file()
                or manifest.license_size is None
                or license_path.stat().st_size != manifest.license_size
                or not manifest.license_sha256
                or sha256_file(license_path) != manifest.license_sha256
            ):
                return RuntimeStatus(
                    RuntimeState.CORRUPT,
                    node_path,
                    required_version=manifest.minimum_version,
                    error="Node LICENSE does not match runtime manifest",
                )
            try:
                current_version = _verify_runtime_files(
                    manifest,
                    node_path,
                    license_path,
                    self.command_runner,
                    context="Installed runtime",
                )
            except RuntimeError as exc:
                error = str(exc)
                state = (
                    RuntimeState.INCOMPATIBLE
                    if "below" in error or "does not match" in error
                    else RuntimeState.ERROR
                )
                return RuntimeStatus(
                    state,
                    node_path,
                    required_version=manifest.minimum_version,
                    error=error,
                )
            return RuntimeStatus(
                RuntimeState.HEALTHY,
                node_path,
                current_version=current_version,
                required_version=manifest.minimum_version,
            )
        except Exception as exc:
            return RuntimeStatus(
                RuntimeState.ERROR,
                self.base_dir / "data" / "node" / "node.exe",
                error=str(exc),
            )

    def _runtime_asset_url(self, manifest: RuntimeManifest) -> str:
        return (
            f"https://github.com/{self.repo_owner}/{self.repo_name}/releases/download/"
            f"{manifest.release_tag}/{manifest.asset_name}"
        )

    def _stage_runtime(
        self,
        temp_dir: Path,
    ) -> tuple[RuntimeManifest, Path, list[tuple[Path, Path]]]:
        manifest = self._manifest()
        target = self._runtime_path(manifest)
        self.status_callback("Đang tải Node portable đã kiểm thử...")
        archive_path = temp_dir / manifest.asset_name
        self.downloader(
            self._runtime_asset_url(manifest),
            archive_path,
            progress_callback=self.progress_callback,
            proxy_url=self.proxy_url,
        )
        if sha256_file(archive_path) != manifest.asset_sha256:
            raise ValueError("Node runtime archive SHA256 mismatch")
        if manifest.asset_size is not None and archive_path.stat().st_size != manifest.asset_size:
            raise ValueError("Node runtime archive size mismatch")

        extract_dir = temp_dir / "runtime"
        extract_dir.mkdir()
        with zipfile.ZipFile(archive_path, "r") as archive:
            members = _validate_zip_members(archive)
            expected_members = {"node.exe", "LICENSE"} if manifest.schema_version == 2 else {"node.exe"}
            if manifest.schema_version == 1 and "LICENSE" in members:
                expected_members.add("LICENSE")
            if set(members) != expected_members:
                raise ValueError("runtime asset must contain exactly node.exe and LICENSE")
            for name, member in members.items():
                destination = extract_dir / name
                with archive.open(member) as source, open(destination, "wb") as output:
                    shutil.copyfileobj(source, output)

        staged_node = extract_dir / "node.exe"
        staged_license = extract_dir / "LICENSE"
        _verify_runtime_files(
            manifest,
            staged_node,
            staged_license,
            self.command_runner,
            context="Downloaded runtime",
        )

        replacements = [(staged_node, target)]
        if staged_license.is_file():
            replacements.append((staged_license, target.parent / "LICENSE"))
        return manifest, staged_node, replacements

    def repair_runtime(self) -> UpdateResult:
        rollback_performed = False
        try:
            with UpdateMutex(self.base_dir):
                with tempfile.TemporaryDirectory(prefix="node_runtime_update_") as temp_dir:
                    manifest, _staged_node, replacements = self._stage_runtime(Path(temp_dir))

                    def verify_runtime() -> None:
                        status = self.check_runtime()
                        if status.state is not RuntimeState.HEALTHY:
                            raise RuntimeError(status.error or "Node verification failed after install")

                    try:
                        _atomic_replace_files(replacements, verify=verify_runtime)
                    except _TransactionError as exc:
                        rollback_performed = exc.rollback_performed
                        raise

            return UpdateResult(
                True,
                "node",
                new_version=manifest.node_version,
                changed_components=("node",),
                message=f"Node {manifest.node_version} is ready",
                stage="complete",
            )
        except Exception as exc:
            return UpdateResult(
                False,
                "node",
                error=str(exc),
                message="Không thể sửa Node portable",
                stage="rollback" if rollback_performed else "prepare_runtime",
                rollback_performed=rollback_performed,
            )

    def _read_binary_version(self, executable: Path) -> str | None:
        if not executable.is_file():
            return None
        try:
            result = self.command_runner([str(executable), "--version"])
            if result.returncode == 0:
                return (result.stdout or "").strip() or None
        except Exception:
            return None
        return None

    def update_yt_dlp(
        self,
        *,
        download_url: str | None = None,
        expected_sha256: str | None = None,
        checksum_url: str | None = None,
    ) -> UpdateResult:
        target = self.base_dir / "yt-dlp" / ("yt-dlp.exe" if os.name == "nt" else "yt-dlp")
        old_version = self._read_binary_version(target)
        url = download_url or "https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp.exe"
        should_fetch_official_checksum = download_url is None and expected_sha256 is None
        rollback_performed = False
        try:
            with UpdateMutex(self.base_dir):
                target.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.TemporaryDirectory(prefix="yt_dlp_update_") as temp_dir_text:
                    temp_dir = Path(temp_dir_text)
                    runtime_status = self.check_runtime()
                    replacements: list[tuple[Path, Path]] = []
                    changed: list[str] = []
                    if runtime_status.state is RuntimeState.HEALTHY:
                        runtime_path = runtime_status.path
                    else:
                        self.status_callback(
                            f"Node chưa sẵn sàng ({runtime_status.state.value}); đang chuẩn bị bản sửa..."
                        )
                        _manifest, runtime_path, runtime_replacements = self._stage_runtime(temp_dir)
                        replacements.extend(runtime_replacements)
                        changed.append("node")

                    staged = temp_dir / target.name
                    if should_fetch_official_checksum:
                        checksum_path = temp_dir / "SHA2-256SUMS"
                        self.status_callback("Đang tải checksum chính thức của yt-dlp...")
                        self.downloader(
                            checksum_url
                            or "https://github.com/yt-dlp/yt-dlp/releases/latest/download/SHA2-256SUMS",
                            checksum_path,
                            proxy_url=self.proxy_url,
                        )
                        for line in checksum_path.read_text(encoding="utf-8").splitlines():
                            parts = line.split()
                            if len(parts) >= 2 and parts[-1].lstrip("*") == target.name:
                                expected_sha256 = parts[0].lower()
                                break
                        if not expected_sha256 or not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
                            raise ValueError(f"Official checksum for {target.name} is missing")

                    self.status_callback("Đang tải yt-dlp mới...")
                    self.downloader(
                        url,
                        staged,
                        progress_callback=self.progress_callback,
                        proxy_url=self.proxy_url,
                    )
                    if expected_sha256 and sha256_file(staged) != expected_sha256.lower():
                        raise ValueError("yt-dlp SHA256 mismatch")
                    if os.name != "nt":
                        staged.chmod(staged.stat().st_mode | stat.S_IXUSR)

                    version_result = self.command_runner([str(staged), "--version"])
                    new_version = (version_result.stdout or "").strip()
                    if version_result.returncode != 0 or not re.fullmatch(
                        r"\d{4}\.\d{2}\.\d{2}(?:\.\d+)?", new_version
                    ):
                        raise RuntimeError(
                            (version_result.stderr or "Downloaded yt-dlp failed version check").strip()
                        )

                    smoke_command = [
                        str(staged),
                        "--ignore-config",
                        "--verbose",
                        "--js-runtimes",
                        f"node:{runtime_path}",
                        "--simulate",
                        "--",
                        "test:",
                    ]
                    smoke_result = self.command_runner(smoke_command, timeout=60)
                    smoke_output = (smoke_result.stdout or "") + (smoke_result.stderr or "")
                    if "No supported JavaScript runtime could be found" in smoke_output:
                        raise RuntimeError("yt-dlp did not recognize the bundled Node runtime")
                    runtime_detected = re.search(
                        r"JS runtimes:\s*[^\r\n]*node", smoke_output, re.IGNORECASE
                    )
                    if not runtime_detected:
                        raise RuntimeError("yt-dlp smoke test did not confirm the bundled Node runtime")
                    if smoke_result.returncode != 0:
                        raise RuntimeError(
                            (smoke_result.stderr or smoke_result.stdout or "yt-dlp smoke test failed").strip()
                        )

                    replacements.append((staged, target))

                    def verify_install() -> None:
                        if changed:
                            status = self.check_runtime()
                            if status.state is not RuntimeState.HEALTHY:
                                raise RuntimeError(status.error or "Node verification failed after install")
                        if self._read_binary_version(target) != new_version:
                            raise RuntimeError("Installed yt-dlp failed verification")

                    try:
                        _atomic_replace_files(replacements, verify=verify_install)
                    except _TransactionError as exc:
                        rollback_performed = exc.rollback_performed
                        raise

            changed.append("yt-dlp")
            return UpdateResult(
                True,
                "yt-dlp",
                old_version=old_version,
                new_version=new_version,
                changed_components=tuple(changed),
                message=f"yt-dlp updated to {new_version}",
                stage="complete",
            )
        except Exception as exc:
            return UpdateResult(
                False,
                "yt-dlp",
                old_version=old_version,
                error=str(exc),
                message="Không thể cập nhật yt-dlp",
                stage="rollback" if rollback_performed else "prepare",
                rollback_performed=rollback_performed,
            )

    def update_app(
        self,
        *,
        download_url: str,
        expected_sha256: str | None = None,
        expected_size: int | None = None,
    ) -> UpdateResult:
        """Download and validate an app update ZIP for the external updater."""
        if not expected_sha256 or not re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256):
            return UpdateResult(
                False,
                "app",
                error="A valid outer SHA256 digest is required",
                message="Không thể tải cập nhật ứng dụng",
                stage="metadata",
            )
        if expected_size is None or expected_size <= 0:
            return UpdateResult(
                False,
                "app",
                error="A positive release asset size is required",
                message="Không thể tải cập nhật ứng dụng",
                stage="metadata",
            )
        fd, temp_name = tempfile.mkstemp(prefix="app_update_", suffix=".pkg")
        os.close(fd)
        changed: list[str] = []
        runtime_temp_name: str | None = None
        try:
            self.status_callback("Đang tải gói cập nhật ứng dụng...")
            self.downloader(
                download_url,
                temp_name,
                progress_callback=self.progress_callback,
                proxy_url=self.proxy_url,
            )
            if expected_size is not None and Path(temp_name).stat().st_size != expected_size:
                raise ValueError("app update size mismatch")
            if expected_sha256 and sha256_file(temp_name) != expected_sha256.lower():
                raise ValueError("app update SHA256 mismatch")
            self.status_callback("Đang xác minh manifest và SHA256...")
            manifest = UpdatePackageApplier.validate_package(Path(temp_name))
            package_paths = {
                str(entry.get("path", "")).replace("\\", "/").lower()
                for entry in manifest["files"]
            }
            package_has_node = "data/node/node.exe" in package_paths
            if package_has_node:
                UpdatePackageApplier.verify_embedded_runtime(
                    Path(temp_name), self.command_runner
                )
            runtime_status = self.check_runtime()
            if runtime_status.state is not RuntimeState.HEALTHY and not package_has_node:
                self.status_callback("Node portable đang thiếu hoặc hỏng; đang chuẩn bị gói sửa...")
                runtime_manifest = self._manifest()
                runtime_fd, runtime_temp_name = tempfile.mkstemp(
                    prefix="node_runtime_", suffix=".pkg"
                )
                os.close(runtime_fd)
                self.downloader(
                    self._runtime_asset_url(runtime_manifest),
                    runtime_temp_name,
                    progress_callback=self.progress_callback,
                    proxy_url=self.proxy_url,
                )
                if sha256_file(runtime_temp_name) != runtime_manifest.asset_sha256:
                    raise ValueError("Node runtime archive SHA256 mismatch")
                if (
                    runtime_manifest.asset_size is not None
                    and Path(runtime_temp_name).stat().st_size != runtime_manifest.asset_size
                ):
                    raise ValueError("Node runtime archive size mismatch")
                with tempfile.TemporaryDirectory(prefix="node_runtime_verify_") as verify_dir:
                    with zipfile.ZipFile(runtime_temp_name, "r") as runtime_archive:
                        runtime_members = _validate_zip_members(runtime_archive)
                        expected_members = (
                            {"node.exe", "LICENSE"}
                            if runtime_manifest.schema_version == 2
                            else {"node.exe"}
                        )
                        if runtime_manifest.schema_version == 1 and "LICENSE" in runtime_members:
                            expected_members.add("LICENSE")
                        if set(runtime_members) != expected_members:
                            raise ValueError(
                                "runtime asset must contain exactly node.exe and LICENSE"
                            )
                        for name, member in runtime_members.items():
                            destination = Path(verify_dir) / name
                            with runtime_archive.open(member) as source, open(
                                destination, "wb"
                            ) as output:
                                shutil.copyfileobj(source, output)
                    _verify_runtime_files(
                        runtime_manifest,
                        Path(verify_dir) / "node.exe",
                        Path(verify_dir) / "LICENSE",
                        self.command_runner,
                        context="Downloaded runtime",
                    )
                changed.append("node")
            elif package_has_node:
                changed.append("node")
            if "updaterv2.exe" in package_paths:
                changed.append("updater")
            changed.append("app")
            return UpdateResult(
                True,
                "app",
                new_version=str(manifest.get("app_version") or ""),
                changed_components=tuple(changed),
                artifact_path=temp_name,
                runtime_artifact_path=runtime_temp_name,
                message="App update package is ready",
                stage="prepared",
            )
        except Exception as exc:
            try:
                os.remove(temp_name)
            except OSError:
                pass
            if runtime_temp_name:
                try:
                    os.remove(runtime_temp_name)
                except OSError:
                    pass
            return UpdateResult(False, "app", error=str(exc), message="Không thể tải cập nhật ứng dụng")


DEFAULT_PRESERVED_PATHS = {
    "data/downloader_settings.json",
    "data/downloader_settings_qt.json",
    "data/download_history.json",
    "data/token.json",
    "data/token_drive.json",
    "data/credentials.json",
    "data/proxy_settings.json",
    "data/cookies.txt",
    "cookies.txt",
    "youtube_cookies.txt",
    "updaterlauncher.exe",
}
STALE_PROTECTED_PREFIXES = ("data/thumbnails/", "data/node/", "yt-dlp/", "updater/")


def _is_stale_protected(relative_text: str) -> bool:
    canonical = _canonical_windows_path(relative_text)
    return canonical in DEFAULT_PRESERVED_PATHS or canonical.startswith(STALE_PROTECTED_PREFIXES)


class UpdatePackageApplier:
    """Validate and atomically overlay a manifest-driven update ZIP."""

    def __init__(
        self,
        *,
        install_dir: str | os.PathLike[str],
        preserve_relative_paths: Iterable[str] = (),
        progress_callback: Callable[[int], None] | None = None,
        command_runner: CommandRunner = _default_command_runner,
    ):
        self.install_dir = Path(install_dir).resolve()
        self.preserve_relative_paths = set(DEFAULT_PRESERVED_PATHS) | {
            str(_safe_relative_path(path)).lower() for path in preserve_relative_paths
        }
        self.progress_callback = progress_callback
        self.command_runner = command_runner

    @staticmethod
    def validate_package(zip_path: str | os.PathLike[str]) -> dict:
        with zipfile.ZipFile(zip_path, "r") as archive:
            file_members = _validate_zip_members(archive)
            manifest_member = file_members.get("update-manifest.json")
            if not manifest_member:
                raise ValueError("update-manifest.json is missing")
            if manifest_member.file_size > MAX_MANIFEST_SIZE:
                raise ValueError("update-manifest.json is too large")
            manifest = json.loads(archive.read(manifest_member).decode("utf-8"))
            schema_version = manifest.get("schema_version")
            if schema_version not in {1, 2} or not isinstance(manifest.get("files"), list):
                raise ValueError("unsupported update manifest schema")
            if schema_version == 2 and (
                not manifest.get("app_version") or not manifest.get("minimum_app_version")
            ):
                raise ValueError("v2 update manifest is missing version constraints")
            expected_paths = set()
            expected_canonical = set()
            entries_by_canonical = {}
            for entry in manifest["files"]:
                relative = str(_safe_relative_path(str(entry.get("path", ""))))
                canonical = _canonical_windows_path(relative)
                if canonical in expected_canonical:
                    raise ValueError(f"duplicate manifest path: {relative}")
                expected_canonical.add(canonical)
                expected_paths.add(relative)
                entries_by_canonical[canonical] = entry
                member = file_members.get(relative)
                if member is None:
                    raise ValueError(f"required update file is missing: {relative}")
                digest, actual_size = _hash_zip_member(archive, member)
                if actual_size != int(entry.get("size", -1)):
                    raise ValueError(f"size mismatch: {relative}")
                expected_digest = str(entry.get("sha256", "")).lower()
                if not re.fullmatch(r"[0-9a-f]{64}", expected_digest) or digest != expected_digest:
                    raise ValueError(f"SHA256 mismatch: {relative}")
                if schema_version == 2 and entry.get("component") not in {
                    "app",
                    "updater",
                    "runtime",
                }:
                    raise ValueError(f"invalid component for {relative}")
            extra = set(file_members) - expected_paths - {"update-manifest.json"}
            if extra:
                raise ValueError(f"unmanifested update files: {', '.join(sorted(extra))}")
            runtime_paths = {
                "data/node/node.exe",
                "data/node/license",
                "data/runtime-manifest.json",
            }
            present_runtime_paths = runtime_paths & set(entries_by_canonical)
            if present_runtime_paths and present_runtime_paths != runtime_paths:
                missing = runtime_paths - present_runtime_paths
                raise ValueError(
                    "smart package runtime is incomplete: " + ", ".join(sorted(missing))
                )
            if present_runtime_paths:
                if _version_tuple(str(manifest["minimum_app_version"])) < (1, 0, 15):
                    raise ValueError("smart package containing runtime requires app 1.0.15")
                for runtime_path in runtime_paths:
                    if entries_by_canonical[runtime_path].get("component") != "runtime":
                        raise ValueError(f"invalid runtime component: {runtime_path}")
                runtime_data = json.loads(
                    archive.read(file_members["data/runtime-manifest.json"]).decode("utf-8")
                )
                runtime_manifest = RuntimeManifest.from_data(runtime_data)
                if runtime_manifest.schema_version != 2:
                    raise ValueError("smart package runtime manifest must use schema v2")
                if runtime_manifest.relative_path.casefold() != "data/node/node.exe":
                    raise ValueError("smart package runtime path is invalid")
                node_entry = entries_by_canonical["data/node/node.exe"]
                license_entry = entries_by_canonical["data/node/license"]
                if (
                    str(node_entry.get("sha256", "")).lower() != runtime_manifest.sha256
                    or int(node_entry.get("size", -1)) != runtime_manifest.node_size
                    or str(license_entry.get("sha256", "")).lower()
                    != runtime_manifest.license_sha256
                    or int(license_entry.get("size", -1)) != runtime_manifest.license_size
                ):
                    raise ValueError("smart package runtime metadata does not match its files")
            return manifest

    @staticmethod
    def verify_embedded_runtime(
        zip_path: str | os.PathLike[str],
        command_runner: CommandRunner = _default_command_runner,
    ) -> RuntimeManifest | None:
        manifest = UpdatePackageApplier.validate_package(zip_path)
        package_paths = {
            _canonical_windows_path(str(entry["path"])) for entry in manifest["files"]
        }
        if "data/node/node.exe" not in package_paths:
            return None
        with tempfile.TemporaryDirectory(prefix="smart_runtime_verify_") as temp_dir:
            staging = Path(temp_dir)
            with zipfile.ZipFile(zip_path, "r") as archive:
                members = _validate_zip_members(archive)
                for relative_text in (
                    "data/node/node.exe",
                    "data/node/LICENSE",
                    "data/runtime-manifest.json",
                ):
                    destination = staging / Path(*PurePosixPath(relative_text).parts)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(members[relative_text]) as source, open(
                        destination, "wb"
                    ) as output:
                        shutil.copyfileobj(source, output)
            runtime_manifest = RuntimeManifest.load(
                staging / "data" / "runtime-manifest.json"
            )
            _verify_runtime_files(
                runtime_manifest,
                staging / "data" / "node" / "node.exe",
                staging / "data" / "node" / "LICENSE",
                command_runner,
                context="Packaged runtime",
            )
            return runtime_manifest

    def apply(
        self,
        zip_path: str | os.PathLike[str],
        *,
        runtime_package: str | os.PathLike[str] | None = None,
    ) -> UpdateResult:
        try:
            manifest = self.validate_package(zip_path)
        except Exception as exc:
            return UpdateResult(False, "app", error=str(exc), message="Gói cập nhật không hợp lệ")

        self.install_dir.mkdir(parents=True, exist_ok=True)
        staging_root = Path(tempfile.mkdtemp(prefix=".update-staging-", dir=self.install_dir.parent))

        def target_for(relative_text: str) -> Path:
            target = (self.install_dir / Path(*PurePosixPath(relative_text).parts)).resolve()
            if target != self.install_dir and self.install_dir not in target.parents:
                raise ValueError(f"update path escapes install directory: {relative_text}")
            return target

        try:
            installed_manifest_path = self.install_dir / "data" / "installed-app-manifest.json"
            previous_manifest = None
            if installed_manifest_path.is_file():
                try:
                    candidate = json.loads(installed_manifest_path.read_text(encoding="utf-8"))
                    if candidate.get("schema_version") == 2 and isinstance(candidate.get("files"), list):
                        previous_manifest = candidate
                except (OSError, ValueError, TypeError):
                    previous_manifest = None

            if manifest.get("schema_version") == 2:
                if previous_manifest is None:
                    raise ValueError("installed app manifest is required for a v2 smart update")
                current_version = str(previous_manifest.get("app_version", ""))
                minimum_version = str(manifest.get("minimum_app_version", ""))
                if _version_tuple(current_version) < _version_tuple(minimum_version):
                    raise ValueError(
                        f"app {current_version} is below the smart-update minimum {minimum_version}"
                    )

            replacements: list[tuple[Path, Path]] = []
            with zipfile.ZipFile(zip_path, "r") as archive:
                archive_members = _validate_zip_members(archive)
                entries = manifest["files"]
                for index, entry in enumerate(entries, start=1):
                    relative_text = str(_safe_relative_path(entry["path"]))
                    target = target_for(relative_text)
                    if relative_text.lower() in self.preserve_relative_paths and target.exists():
                        if self.progress_callback:
                            self.progress_callback(int(index * 100 / max(len(entries), 1)))
                        continue
                    staged = staging_root / Path(*PurePosixPath(relative_text).parts)
                    staged.parent.mkdir(parents=True, exist_ok=True)
                    member = archive_members[relative_text]
                    with archive.open(member) as source, open(staged, "wb") as output:
                        shutil.copyfileobj(source, output)
                    replacements.append((staged, target))

            package_paths = {
                _canonical_windows_path(str(entry["path"])) for entry in manifest["files"]
            }
            packaged_runtime: RuntimeManifest | None = None
            if "data/node/node.exe" in package_paths:
                packaged_runtime = RuntimeManifest.load(
                    staging_root / "data" / "runtime-manifest.json"
                )
                _verify_runtime_files(
                    packaged_runtime,
                    staging_root / "data" / "node" / "node.exe",
                    staging_root / "data" / "node" / "LICENSE",
                    self.command_runner,
                    context="Packaged runtime",
                )

            prepared_runtime: RuntimeManifest | None = None
            if runtime_package is not None:
                prepared_runtime = RuntimeManifest.load(
                    self.install_dir / "data" / "runtime-manifest.json"
                )
                runtime_package_path = Path(runtime_package)
                if sha256_file(runtime_package_path) != prepared_runtime.asset_sha256:
                    raise ValueError("Node runtime archive SHA256 mismatch")
                if (
                    prepared_runtime.asset_size is not None
                    and runtime_package_path.stat().st_size != prepared_runtime.asset_size
                ):
                    raise ValueError("Node runtime archive size mismatch")
                runtime_staging = staging_root / "prepared-runtime"
                runtime_staging.mkdir()
                with zipfile.ZipFile(runtime_package_path, "r") as runtime_archive:
                    runtime_members = _validate_zip_members(runtime_archive)
                    expected_runtime_members = (
                        {"node.exe", "LICENSE"}
                        if prepared_runtime.schema_version == 2
                        else {"node.exe"}
                    )
                    if prepared_runtime.schema_version == 1 and "LICENSE" in runtime_members:
                        expected_runtime_members.add("LICENSE")
                    if set(runtime_members) != expected_runtime_members:
                        raise ValueError("runtime asset must contain exactly node.exe and LICENSE")
                    for name, member in runtime_members.items():
                        destination = runtime_staging / name
                        with runtime_archive.open(member) as source, open(destination, "wb") as output:
                            shutil.copyfileobj(source, output)
                staged_node = runtime_staging / "node.exe"
                staged_license = runtime_staging / "LICENSE"
                _verify_runtime_files(
                    prepared_runtime,
                    staged_node,
                    staged_license,
                    self.command_runner,
                    context="Prepared runtime",
                )
                runtime_relative = _safe_relative_path(prepared_runtime.relative_path)
                replacements.append(
                    (staged_node, target_for(str(runtime_relative)))
                )
                if staged_license.is_file():
                    replacements.append(
                        (staged_license, target_for("data/node/LICENSE"))
                    )

            stale_targets: list[Path] = []
            if previous_manifest is not None:
                old_app_paths = {
                    str(_safe_relative_path(str(entry.get("path", ""))))
                    for entry in previous_manifest["files"]
                    if entry.get("component") == "app"
                }
                new_app_paths = {
                    str(_safe_relative_path(str(entry.get("path", ""))))
                    for entry in manifest["files"]
                    if entry.get("component", "app") == "app"
                }
                stale_targets = [
                    target_for(relative)
                    for relative in sorted(old_app_paths - new_app_paths)
                    if not _is_stale_protected(relative)
                ]

            if manifest.get("schema_version") == 2:
                staged_record = staging_root / "installed-app-manifest.json"
                staged_record.write_text(
                    json.dumps(manifest, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                replacements.append((staged_record, installed_manifest_path))

            def verify_install() -> None:
                for entry in manifest["files"]:
                    relative_text = str(_safe_relative_path(entry["path"]))
                    target = target_for(relative_text)
                    if relative_text.lower() in self.preserve_relative_paths and target.exists():
                        continue
                    if entry.get("required", True) and (
                        not target.is_file()
                        or sha256_file(target) != str(entry["sha256"]).lower()
                    ):
                        raise RuntimeError(f"post-update verification failed: {relative_text}")
                for stale_target in stale_targets:
                    if stale_target.exists():
                        raise RuntimeError(f"stale app file was not removed: {stale_target}")
                if prepared_runtime is not None:
                    runtime_target = target_for(prepared_runtime.relative_path)
                    _verify_runtime_files(
                        prepared_runtime,
                        runtime_target,
                        target_for("data/node/LICENSE"),
                        self.command_runner,
                        context="Installed runtime",
                    )
                if packaged_runtime is not None:
                    _verify_runtime_files(
                        packaged_runtime,
                        target_for(packaged_runtime.relative_path),
                        target_for("data/node/LICENSE"),
                        self.command_runner,
                        context="Installed packaged runtime",
                    )

            _atomic_replace_files(replacements, deletions=stale_targets, verify=verify_install)
            if self.progress_callback:
                self.progress_callback(100)
        except _TransactionError as exc:
            shutil.rmtree(staging_root, ignore_errors=True)
            return UpdateResult(
                False,
                "app",
                error=str(exc),
                message="Cập nhật thất bại và đã rollback",
                stage="rollback",
                rollback_performed=exc.rollback_performed,
            )
        except Exception as exc:
            shutil.rmtree(staging_root, ignore_errors=True)
            return UpdateResult(False, "app", error=str(exc), message="Cập nhật thất bại")

        shutil.rmtree(staging_root, ignore_errors=True)
        return UpdateResult(
            True,
            "app",
            new_version=str(manifest.get("app_version") or ""),
            changed_components=("node", "app")
            if runtime_package is not None or packaged_runtime is not None
            else ("app",),
            message="Cập nhật ứng dụng thành công",
            stage="complete",
        )


def create_update_manifest(package_dir: str | os.PathLike[str], app_version: str) -> dict:
    root = Path(package_dir).resolve()
    files = []
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.name == "update-manifest.json":
            continue
        relative = path.relative_to(root).as_posix()
        files.append({
            "path": relative,
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
            "required": True,
        })
    return {"schema_version": 1, "app_version": app_version, "files": files}


def create_runtime_asset(
    *,
    node_dir: str | os.PathLike[str],
    output_zip: str | os.PathLike[str],
    manifest_path: str | os.PathLike[str],
    release_tag: str,
    node_version: str,
    minimum_version: str = "22.0.0",
) -> dict:
    """Build a deterministic portable Node asset and its runtime manifest."""
    source_dir = Path(node_dir)
    node_path = source_dir / "node.exe"
    if not node_path.is_file():
        raise FileNotFoundError(f"portable Node not found: {node_path}")
    license_path = source_dir / "LICENSE"
    if not license_path.is_file():
        raise FileNotFoundError(f"portable Node LICENSE not found: {license_path}")

    output_path = Path(output_zip)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for source_path in (node_path, license_path):
            info = zipfile.ZipInfo(source_path.name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, source_path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED, compresslevel=9)

    files = []
    for source_path in (node_path, license_path):
        files.append({
            "path": source_path.name,
            "sha256": sha256_file(source_path),
            "size": source_path.stat().st_size,
        })
    manifest = {
        "schema_version": 2,
        "platform": "win-x64",
        "release_tag": release_tag,
        "asset": {
            "name": output_path.name,
            "sha256": sha256_file(output_path),
            "size": output_path.stat().st_size,
        },
        "node": {
            "version": node_version,
            "minimum_version": minimum_version,
            "relative_path": "data/node/node.exe",
            "sha256": sha256_file(node_path),
        },
        "files": files,
    }
    destination = Path(manifest_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".tmp")
    temporary.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    os.replace(temporary, destination)
    return manifest
