"""Build and publish the Windows x64 application update artifacts."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import zipfile
from pathlib import Path
from typing import Callable, Iterable, Sequence

import requests

from update_manager import create_runtime_asset, sha256_file


APP_NAME = "YouTube Downloader Pro"
MAIN_EXE_NAME = "YouTube Downloader Pro.exe"
MAIN_SCRIPT = "ui_script.py"
ICON_FILE = "data/ico.ico"
GITHUB_TOKEN = os.environ.get("GITHUB_TOKEN", "").strip()
GITHUB_OWNER = "davidtuyen"
GITHUB_REPO = "DC_video_youtube"

NODE_VERSION = "24.12.0"
MINIMUM_NODE_VERSION = "22.0.0"
NODE_DISTRIBUTION_NAME = f"node-v{NODE_VERSION}-win-x64.zip"
NODE_DISTRIBUTION_URL = f"https://nodejs.org/dist/v{NODE_VERSION}/{NODE_DISTRIBUTION_NAME}"
NODE_SHASUMS_URL = f"https://nodejs.org/dist/v{NODE_VERSION}/SHASUMS256.txt"
RUNTIME_ASSET_NAME = "node-runtime-win-x64.pkg"
NODE_RUNTIME_RELEASE_TAG = "1.0.17"
YT_DLP_VERSION = "2026.07.04"
YT_DLP_BINARY_URL = (
    f"https://github.com/yt-dlp/yt-dlp/releases/download/{YT_DLP_VERSION}/yt-dlp.exe"
)
YT_DLP_SHASUMS_URL = (
    f"https://github.com/yt-dlp/yt-dlp/releases/download/{YT_DLP_VERSION}/SHA2-256SUMS"
)
UPDATER_PROTOCOL_VERSION = 2
UPDATER_WORKER_VERSION = "2.1.0"
UPDATER_WORKER_RELEASE_TAG = "1.0.15"
MINIMUM_SMART_UPDATE_VERSION = "1.0.13"
MINIMUM_RUNTIME_SMART_UPDATE_VERSION = "1.0.15"

REPO_ROOT = Path(__file__).parent.resolve()
DIST_DIR = REPO_ROOT / "dist"
BUILD_DIR = REPO_ROOT / "build"

USER_STATE_PATHS = {
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
}
GOOGLE_DRIVE_SOURCE_CLIENT = "credentials.json"
GOOGLE_DRIVE_PACKAGED_CLIENT = "google_drive_client.json"


def _normalize_version(value: str) -> str:
    return value.strip().lstrip("vV")


def get_current_version() -> str:
    content = (REPO_ROOT / MAIN_SCRIPT).read_text(encoding="utf-8")
    match = re.search(r'APP_VERSION\s*=\s*"([^"]+)"', content)
    if not match:
        raise RuntimeError(f"APP_VERSION is missing from {MAIN_SCRIPT}")
    return match.group(1)


def update_version_in_source(new_version: str) -> None:
    target = REPO_ROOT / MAIN_SCRIPT
    content = target.read_text(encoding="utf-8")
    updated, count = re.subn(
        r'APP_VERSION\s*=\s*"[^"]+"',
        f'APP_VERSION = "{new_version}"',
        content,
        count=1,
    )
    if count != 1:
        raise RuntimeError(f"APP_VERSION is missing from {MAIN_SCRIPT}")
    temporary = target.with_suffix(target.suffix + ".version-tmp")
    temporary.write_text(updated, encoding="utf-8")
    os.replace(temporary, target)


def run_release_pipeline(
    version: str,
    *,
    build_callback: Callable[[str], Iterable[Path]],
    upload_callback: Callable[[Iterable[Path], str], None],
) -> list[Path]:
    """Leave the new source version only after build and upload both succeed."""
    source = REPO_ROOT / MAIN_SCRIPT
    original = source.read_bytes()
    try:
        update_version_in_source(version)
        assets = [Path(path) for path in build_callback(version)]
        upload_callback(assets, version)
        return assets
    except Exception:
        temporary = source.with_suffix(source.suffix + ".restore-tmp")
        temporary.write_bytes(original)
        os.replace(temporary, source)
        raise


def clean_build() -> None:
    for path in (DIST_DIR, BUILD_DIR):
        if path.exists():
            shutil.rmtree(path)


def _download_bytes(url: str) -> bytes:
    response = requests.get(url, timeout=60)
    response.raise_for_status()
    return response.content


def ensure_portable_node() -> Path:
    """Download the pinned official Node archive and verify its published SHA256."""
    shasums = _download_bytes(NODE_SHASUMS_URL).decode("utf-8")
    expected_archive_hash = None
    for line in shasums.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == NODE_DISTRIBUTION_NAME:
            expected_archive_hash = parts[0].casefold()
            break
    if not expected_archive_hash or not re.fullmatch(r"[0-9a-f]{64}", expected_archive_hash):
        raise RuntimeError(f"Official SHA256 for {NODE_DISTRIBUTION_NAME} is missing")
    archive_bytes = _download_bytes(NODE_DISTRIBUTION_URL)
    if hashlib.sha256(archive_bytes).hexdigest() != expected_archive_hash:
        raise RuntimeError("Official Node archive SHA256 mismatch")

    destination_dir = REPO_ROOT / "data" / "node"
    destination_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"node-v{NODE_VERSION}-win-x64/"
    with tempfile.TemporaryDirectory(prefix="node_publish_") as temp_dir:
        archive_path = Path(temp_dir) / NODE_DISTRIBUTION_NAME
        archive_path.write_bytes(archive_bytes)
        with zipfile.ZipFile(archive_path) as archive:
            names = {info.filename: info for info in archive.infolist() if not info.is_dir()}
            required = {
                "node.exe": names.get(prefix + "node.exe"),
                "LICENSE": names.get(prefix + "LICENSE"),
            }
            if any(member is None for member in required.values()):
                raise RuntimeError("Official Node archive is missing node.exe or LICENSE")
            for name, member in required.items():
                staged = Path(temp_dir) / name
                with archive.open(member) as source, open(staged, "wb") as output:
                    shutil.copyfileobj(source, output)
                os.replace(staged, destination_dir / name)
    result = subprocess.run(
        [str(destination_dir / "node.exe"), "--version"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0 or result.stdout.strip().lstrip("v") != NODE_VERSION:
        raise RuntimeError(f"Portable Node is not exactly {NODE_VERSION}")
    return destination_dir / "node.exe"


def prepare_runtime_assets(release_tag: str = NODE_RUNTIME_RELEASE_TAG) -> Path:
    ensure_portable_node()
    runtime_asset = DIST_DIR / RUNTIME_ASSET_NAME
    return_path = Path(runtime_asset)
    create_runtime_asset(
        node_dir=REPO_ROOT / "data" / "node",
        output_zip=return_path,
        manifest_path=REPO_ROOT / "data" / "runtime-manifest.json",
        release_tag=_normalize_version(release_tag),
        node_version=NODE_VERSION,
        minimum_version=MINIMUM_NODE_VERSION,
    )
    return return_path


def prepare_pinned_yt_dlp(node_path: Path) -> Path:
    """Download and validate the exact yt-dlp binary shipped by the installer."""
    node_path = Path(node_path).resolve()
    if not node_path.is_file():
        raise FileNotFoundError(f"Portable Node is missing: {node_path}")
    checksums = _download_bytes(YT_DLP_SHASUMS_URL).decode("utf-8")
    expected_hash = None
    for line in checksums.splitlines():
        parts = line.split()
        if len(parts) >= 2 and parts[-1].lstrip("*") == "yt-dlp.exe":
            expected_hash = parts[0].casefold()
            break
    if not expected_hash or not re.fullmatch(r"[0-9a-f]{64}", expected_hash):
        raise RuntimeError("Official SHA256 for yt-dlp.exe is missing")
    binary = _download_bytes(YT_DLP_BINARY_URL)
    if hashlib.sha256(binary).hexdigest() != expected_hash:
        raise RuntimeError("Official yt-dlp SHA256 mismatch")

    download_dir = BUILD_DIR / "downloads"
    download_dir.mkdir(parents=True, exist_ok=True)
    staged = download_dir / f".yt-dlp-{YT_DLP_VERSION}.tmp.exe"
    destination = download_dir / "yt-dlp.exe"
    staged.write_bytes(binary)
    try:
        version_result = subprocess.run(
            [str(staged), "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        actual_version = (version_result.stdout or "").strip()
        if version_result.returncode != 0 or actual_version != YT_DLP_VERSION:
            raise RuntimeError(
                f"Pinned yt-dlp version check failed: expected {YT_DLP_VERSION}, "
                f"got {actual_version or 'no version'}"
            )
        smoke_command = [
            str(staged),
            "--ignore-config",
            "--verbose",
            "--js-runtimes",
            f"node:{node_path}",
            "--simulate",
            "--",
            "test:",
        ]
        smoke_result = subprocess.run(
            smoke_command,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        smoke_output = (smoke_result.stdout or "") + (smoke_result.stderr or "")
        if smoke_result.returncode != 0:
            raise RuntimeError(
                "Pinned yt-dlp smoke test failed: "
                + (smoke_result.stderr or smoke_result.stdout or "unknown error").strip()
            )
        if not re.search(r"JS runtimes:\s*[^\r\n]*node", smoke_output, re.IGNORECASE):
            raise RuntimeError("Pinned yt-dlp runtime detection failed")
        os.replace(staged, destination)
    finally:
        try:
            staged.unlink()
        except FileNotFoundError:
            pass
    return destination


def _resolve_icon_path() -> Path | None:
    for candidate in (
        REPO_ROOT / ICON_FILE,
        REPO_ROOT / "data" / "video-dowload-dc-team.ico",
    ):
        if candidate.is_file():
            return candidate
    return None


def _run_pyinstaller(
    name: str,
    script: Path,
    *,
    onedir: bool,
    extra_args: Sequence[str] = (),
) -> None:
    spec_dir = BUILD_DIR / "specs"
    spec_dir.mkdir(parents=True, exist_ok=True)
    command = [
        "pyinstaller",
        "--noconfirm",
        "--clean",
        "--noconsole",
        "--name",
        name,
        "--specpath",
        str(spec_dir),
        "--distpath",
        str(DIST_DIR),
        "--workpath",
        str(BUILD_DIR / name),
        "--onedir" if onedir else "--onefile",
    ]
    command.extend(extra_args)
    icon = _resolve_icon_path()
    if icon:
        command.extend(["--icon", str(icon)])
    command.append(str(script))
    subprocess.run(command, check=True)


def build_updaters(_release_tag: str) -> tuple[Path, Path, dict]:
    worker_name = f"UpdaterWorker-{UPDATER_WORKER_VERSION}"
    _run_pyinstaller(worker_name, REPO_ROOT / "updater_gui.py", onedir=False)
    _run_pyinstaller("UpdaterLauncher", REPO_ROOT / "updater_launcher.py", onedir=False)
    worker_path = DIST_DIR / f"{worker_name}.exe"
    launcher_path = DIST_DIR / "UpdaterLauncher.exe"
    manifest = {
        "schema_version": 1,
        "protocol_version": UPDATER_PROTOCOL_VERSION,
        "worker": {
            "path": f"updater/{worker_path.name}",
            "sha256": sha256_file(worker_path),
            "release_tag": _normalize_version(UPDATER_WORKER_RELEASE_TAG),
        },
    }
    return launcher_path, worker_path, manifest


def build_main_app(
    version: str,
    updater_outputs: tuple[Path, Path, dict],
    verified_yt_dlp: Path | None = None,
) -> Path:
    if verified_yt_dlp is None or not Path(verified_yt_dlp).is_file():
        raise FileNotFoundError("Verified pinned yt-dlp binary is required")
    _run_pyinstaller(
        APP_NAME,
        REPO_ROOT / MAIN_SCRIPT,
        onedir=True,
        extra_args=("--hidden-import", "PyQt5"),
    )
    app_dir = DIST_DIR / APP_NAME
    source_data = REPO_ROOT / "data"
    shutil.copytree(
        source_data,
        app_dir / "data",
        dirs_exist_ok=True,
        ignore=shutil.ignore_patterns(
            "*.tmp",
            "thumbnails",
            "cookies.txt",
            "token*.json",
            "credentials.json",
            "proxy_settings.json",
            "download_history.json",
            "downloader_settings*.json",
            "browser",
        ),
    )
    oauth_source = source_data / GOOGLE_DRIVE_SOURCE_CLIENT
    if not oauth_source.is_file():
        raise FileNotFoundError(
            f"Google Drive OAuth client is required: {oauth_source}"
        )
    oauth_destination = app_dir / "data" / GOOGLE_DRIVE_PACKAGED_CLIENT
    oauth_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(oauth_source, oauth_destination)
    yt_dlp_destination = app_dir / "yt-dlp" / "yt-dlp.exe"
    yt_dlp_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(verified_yt_dlp, yt_dlp_destination)
    launcher, worker, updater_manifest = updater_outputs
    shutil.copy2(launcher, app_dir / "UpdaterLauncher.exe")
    worker_destination = app_dir / updater_manifest["worker"]["path"]
    worker_destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(worker, worker_destination)
    updater_manifest_path = app_dir / "data" / "updater-manifest.json"
    updater_manifest_path.write_text(
        json.dumps(updater_manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_seed_installed_manifest(app_dir, version)
    return app_dir


def _find_inno_compiler() -> Path:
    configured = os.environ.get("INNO_SETUP_COMPILER", "").strip()
    candidates = [
        Path(configured) if configured else None,
        Path(os.environ.get("LOCALAPPDATA", ""))
        / "Programs"
        / "Inno Setup 6"
        / "ISCC.exe",
        Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
        Path(os.environ.get("ProgramFiles", "")) / "Inno Setup 6" / "ISCC.exe",
    ]
    for candidate in candidates:
        if candidate and candidate.is_file():
            return candidate
    discovered = shutil.which("ISCC.exe")
    if discovered:
        return Path(discovered)
    raise RuntimeError(
        "Inno Setup 6 is required. Install it or set INNO_SETUP_COMPILER to ISCC.exe."
    )


def build_installer(version: str, app_dir: Path) -> Path:
    compiler = _find_inno_compiler()
    installer_script = REPO_ROOT / "installer.iss"
    subprocess.run(
        [
            str(compiler),
            f"/DMyAppVersion={_normalize_version(version)}",
            f"/DMySourceDir={app_dir.resolve()}",
            f"/DMyOutputDir={DIST_DIR.resolve()}",
            str(installer_script),
        ],
        check=True,
    )
    output = DIST_DIR / f"YouTubeDownloaderPro-Setup-v{_normalize_version(version)}.exe"
    if not output.is_file():
        raise RuntimeError(f"Inno Setup did not create {output.name}")
    return output


def _component_for(relative: str) -> str:
    normalized = relative.casefold()
    if normalized.startswith("data/node/") or normalized == "data/runtime-manifest.json":
        return "runtime"
    if normalized.startswith("updater/") or normalized == "data/updater-manifest.json":
        return "updater"
    return "app"


def _write_seed_installed_manifest(app_dir: Path, version: str) -> None:
    files = []
    for path in sorted(app_dir.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(app_dir).as_posix()
        if _component_for(relative) != "app" or relative.casefold() == "updaterlauncher.exe":
            continue
        files.append({"path": relative, "component": "app"})
    destination = app_dir / "data" / "installed-app-manifest.json"
    destination.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "app_version": version,
                "minimum_app_version": MINIMUM_SMART_UPDATE_VERSION,
                "files": files,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _read_release_tags(app_dir: Path) -> tuple[str, str, str]:
    runtime = json.loads((app_dir / "data" / "runtime-manifest.json").read_text(encoding="utf-8"))
    updater = json.loads((app_dir / "data" / "updater-manifest.json").read_text(encoding="utf-8"))
    return (
        _normalize_version(str(runtime["release_tag"])),
        _normalize_version(str(updater["worker"]["release_tag"])),
        str(updater["worker"]["path"]).replace("\\", "/").casefold(),
    )


def should_include_package_path(
    relative_path: Path,
    *,
    version: str,
    runtime_release_tag: str,
    updater_release_tag: str,
    active_worker_path: str,
) -> bool:
    normalized = relative_path.as_posix().casefold()
    if (
        normalized in USER_STATE_PATHS
        or normalized.startswith("data/thumbnails/")
        or normalized.startswith("data/browser/")
    ):
        return False
    if normalized.startswith("yt-dlp/") or normalized == "updaterlauncher.exe":
        return False
    if normalized == "data/installed-app-manifest.json" or "ffmpeg" in normalized.split("/"):
        return False
    if normalized == "data/runtime-manifest.json":
        return runtime_release_tag == _normalize_version(version)
    if normalized == "data/updater-manifest.json":
        return updater_release_tag == _normalize_version(version)
    if normalized.startswith("data/node/"):
        return runtime_release_tag == _normalize_version(version)
    if normalized.startswith("updater/"):
        return (
            updater_release_tag == _normalize_version(version)
            and normalized == active_worker_path
        )
    return True


def create_package(mode: str, version: str) -> Path:
    smart_update = mode in {"smart", "2"}
    if not smart_update:
        raise ValueError("ZIP full packages were replaced by the Inno Setup installer")
    if _normalize_version(version) == "1.0.13":
        raise ValueError("v1.0.13 is installer-only")
    app_dir = DIST_DIR / APP_NAME
    runtime_tag, updater_tag, worker_path = _read_release_tags(app_dir)
    includes_runtime = runtime_tag == _normalize_version(version)
    included: list[tuple[Path, Path]] = []
    for path in app_dir.rglob("*"):
        if not path.is_file():
            continue
        relative = path.relative_to(app_dir)
        if should_include_package_path(
            relative,
            version=version,
            runtime_release_tag=runtime_tag,
            updater_release_tag=updater_tag,
            active_worker_path=worker_path,
        ):
            included.append((path, relative))
    entries = []
    for path, relative in sorted(included, key=lambda item: item[1].as_posix()):
        relative_text = relative.as_posix()
        entries.append({
            "path": relative_text,
            "sha256": sha256_file(path),
            "size": path.stat().st_size,
            "required": True,
            "component": _component_for(relative_text),
        })
    manifest = {
        "schema_version": 2,
        "app_version": _normalize_version(version),
        "minimum_app_version": (
            MINIMUM_RUNTIME_SMART_UPDATE_VERSION
            if includes_runtime
            else MINIMUM_SMART_UPDATE_VERSION
        ),
        "files": entries,
    }
    package = DIST_DIR / "app-update-v2.pkg"
    with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path, relative in included:
            archive.write(path, relative.as_posix())
        archive.writestr(
            "update-manifest.json",
            json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        )
    return package


def _raise_for_api(response, operation: str, expected: set[int]) -> None:
    if response.status_code not in expected:
        raise RuntimeError(f"GitHub {operation} failed: {response.status_code} {response.text}")


def _git_release_commit(version: str) -> str:
    tag_ref = f"refs/tags/{_normalize_version(version)}^{{commit}}"
    result = subprocess.run(
        ["git", "rev-parse", "--verify", tag_ref],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    commit = result.stdout.strip().casefold()
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise RuntimeError("Unable to resolve the release source commit")
    return commit


def _release_body(version: str, assets: Iterable[Path]) -> str:
    normalized_version = _normalize_version(version)
    lines = [f"## YouTube Downloader Pro v{normalized_version}", ""]
    if normalized_version == "1.0.13":
        lines.extend([
            "Đây là bản migration một lần từ updater v1 sang updater v2.",
            "",
            "- Chạy `YouTubeDownloaderPro-Setup-v1.0.13.exe` để cài đè bản cũ.",
            "- Setup giữ nguyên settings, history, cookies, token, proxy, thumbnails và yt-dlp hiện có.",
            "- Bản này không phát hành Smart Update `.zip`; từ v1.0.14 sẽ dùng `app-update-v2.pkg`.",
            "- `node-runtime-win-x64.pkg` dùng cho cơ chế tự sửa Node portable.",
            "",
        ])
    elif normalized_version == "1.0.14":
        lines.extend([
            "- Setup có tùy chọn `Create a Desktop shortcut`, được chọn mặc định.",
            "- Sửa kiểm tra yt-dlp + Node thành smoke test offline bằng extractor nội bộ `test:`.",
            "- Smoke test không truy cập YouTube, không tải video và không phụ thuộc bot-check/cookies.",
            "- Hỗ trợ Smart Update an toàn từ v1.0.13 bằng `app-update-v2.pkg`.",
            "",
        ])
    elif normalized_version == "1.0.15":
        lines.extend([
            "- Runtime validation now covers both `node.exe` and `LICENSE`, including rollback after installation.",
            "- Smart Update ships `UpdaterWorker 2.1.0`; Node 24.12.0 remains unchanged and is not included in this package.",
            "- Setup ships the pinned, checksum-verified yt-dlp 2026.07.04 build.",
            "- Draft releases are published only after the complete asset set, sizes and SHA256 digests match.",
            "",
        ])
    elif normalized_version == "1.0.17":
        lines.extend([
            "- Dọn dead code, import thừa, asset trùng và dữ liệu runtime/cache khỏi repository.",
            "- Sửa đường dẫn FFmpeg/FFprobe trong bản đóng gói để xác minh video hoạt động đúng sau khi cài.",
            "- Build dừng sớm nếu thiếu yt-dlp đã xác minh, tránh tạo thư mục phân phối rác.",
            "- Cài đè vẫn giữ nguyên settings và lịch sử tải của người dùng.",
            "",
        ])
    elif normalized_version == "1.0.18":
        lines.extend([
            "- Sửa bản cài đặt và Smart Update bị thiếu cấu hình OAuth Google Drive.",
            "- Khi dán liên kết Drive/Google Sheets lần đầu, ứng dụng mở trình duyệt mặc định để người dùng cấp quyền.",
            "- Token Drive của từng người dùng và cấu hình `credentials.json` tùy chỉnh vẫn được giữ nguyên khi cập nhật.",
            "",
        ])
    lines.extend(["### SHA256", ""])
    for asset in assets:
        path = Path(asset)
        lines.append(f"- `{path.name}`: `{sha256_file(path)}` ({path.stat().st_size} bytes)")
    return "\n".join(lines)


def _verify_release_assets(release: dict, assets: Sequence[Path], version: str) -> None:
    if not release.get("draft"):
        raise RuntimeError("Release changed state before asset verification")
    if _normalize_version(str(release.get("tag_name", ""))) != _normalize_version(version):
        raise RuntimeError("Release tag changed before asset verification")
    expected = {path.name: path for path in assets}
    if len(expected) != len(assets):
        raise RuntimeError("Local release asset names must be unique")
    remote_assets = release.get("assets")
    if not isinstance(remote_assets, list):
        raise RuntimeError("GitHub release asset metadata is missing")
    remote_names = [str(item.get("name", "")) for item in remote_assets]
    if len(remote_names) != len(set(remote_names)):
        raise RuntimeError("GitHub release contains duplicate asset names")
    if set(remote_names) != set(expected):
        raise RuntimeError("GitHub release asset set does not match the build")
    for metadata in remote_assets:
        path = expected[str(metadata["name"])]
        expected_digest = f"sha256:{sha256_file(path)}"
        if (
            metadata.get("state") != "uploaded"
            or int(metadata.get("size", -1)) != path.stat().st_size
            or str(metadata.get("digest", "")).casefold() != expected_digest
        ):
            raise RuntimeError(f"GitHub release asset verification failed: {path.name}")


def upload_to_github(asset_paths: Iterable[Path], version: str) -> None:
    if not GITHUB_TOKEN:
        raise RuntimeError("GITHUB_TOKEN is required for publishing")
    assets = [Path(path) for path in asset_paths]
    if len({path.name for path in assets}) != len(assets):
        raise RuntimeError("Local release asset names must be unique")
    target_commitish = _git_release_commit(version)
    release_body = _release_body(version, assets)
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    releases_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases"
    create = requests.post(
        releases_url,
        headers=headers,
        json={
            "tag_name": _normalize_version(version),
            "name": f"Release v{_normalize_version(version)}",
            "body": release_body,
            "draft": True,
            "prerelease": False,
            "target_commitish": target_commitish,
        },
    )
    if create.status_code == 422:
        existing = requests.get(
            f"{releases_url}/tags/{_normalize_version(version)}",
            headers=headers,
        )
        if existing.status_code == 404:
            _raise_for_api(create, "create draft release", {201})
        _raise_for_api(existing, "get release", {200})
        release = existing.json()
        if not release.get("draft"):
            raise RuntimeError("Refusing to modify an already published release")
    else:
        _raise_for_api(create, "create draft release", {201})
        release = create.json()

    for existing_asset in release.get("assets", []):
        deletion = requests.delete(existing_asset["url"], headers=headers)
        _raise_for_api(deletion, "delete draft asset", {204})

    upload_url = str(release["upload_url"]).split("{")[0]
    for asset in assets:
        upload_headers = dict(headers)
        upload_headers["Content-Type"] = "application/octet-stream"
        with open(asset, "rb") as handle:
            uploaded = requests.post(
                f"{upload_url}?name={urllib.parse.quote(asset.name)}",
                headers=upload_headers,
                data=handle,
            )
        _raise_for_api(uploaded, f"upload {asset.name}", {201})
        metadata = uploaded.json()
        expected_digest = f"sha256:{sha256_file(asset)}"
        if (
            metadata.get("name") != asset.name
            or int(metadata.get("size", -1)) != asset.stat().st_size
            or str(metadata.get("digest", "")).casefold() != expected_digest
        ):
            raise RuntimeError(f"Uploaded asset verification failed: {asset.name}")

    verified = requests.get(
        f"{releases_url}/{release['id']}",
        headers=headers,
    )
    _raise_for_api(verified, "verify draft release", {200})
    _verify_release_assets(verified.json(), assets, version)

    published = requests.patch(
        f"{releases_url}/{release['id']}",
        headers=headers,
        json={"draft": False},
    )
    _raise_for_api(published, "publish release", {200})


def build_release_assets(version: str) -> list[Path]:
    clean_build()
    runtime_asset = prepare_runtime_assets()
    verified_yt_dlp = prepare_pinned_yt_dlp(REPO_ROOT / "data" / "node" / "node.exe")
    updater_outputs = build_updaters(version)
    app_dir = build_main_app(version, updater_outputs, verified_yt_dlp)
    setup = build_installer(version, app_dir)
    normalized_version = _normalize_version(version)
    if normalized_version == "1.0.13":
        return [setup, runtime_asset]
    assets = [setup, create_package("smart", version)]
    runtime_manifest = json.loads(
        (REPO_ROOT / "data" / "runtime-manifest.json").read_text(encoding="utf-8")
    )
    if _normalize_version(runtime_manifest["release_tag"]) == _normalize_version(version):
        assets.append(runtime_asset)
    return assets


def main() -> int:
    if len(sys.argv) < 3 or sys.argv[1] not in {"build", "release"}:
        print("Usage: python publish.py [build|release] VERSION")
        return 2
    action, version = sys.argv[1], _normalize_version(sys.argv[2])
    if action == "release":
        run_release_pipeline(
            version,
            build_callback=build_release_assets,
            upload_callback=upload_to_github,
        )
    else:
        run_release_pipeline(
            version,
            build_callback=build_release_assets,
            upload_callback=lambda _assets, _version: None,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
