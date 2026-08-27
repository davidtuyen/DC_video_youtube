# workers.py - Worker classes extracted from ui_script.py
import google_drive_handler
import gdrive_downloader
from PyQt5.QtCore import Qt, QThread, pyqtSignal as Signal, QObject, pyqtSlot as Slot
from PyQt5.QtGui import QPixmap, QColor, QPainter
import os
import platform
import subprocess
import re
import asyncio
import signal
import urllib.request
import urllib.parse
import urllib.error
import time
import threading
import requests
from enum import Enum
from update_manager import ReleaseAsset, UpdateManager

try:
    import main_logic
    import video_verifier
except ImportError:
    main_logic = None
    video_verifier = None

try:
    import url_handler
except ImportError:
    url_handler = None

# These will be set by ui_script after import
APP_THEME = {}
THUMBNAIL_CACHE_DIR = ""
USER_AGENT = ""
APP_VERSION = ""
GITHUB_OWNER = ""
GITHUB_REPO = ""


class YoutubeAccessMode(Enum):
    NORMAL_NO_COOKIE = "normal_no_cookie"
    CLEAN_ANONYMOUS = "clean_anonymous"
    COOKIE = "cookie"


class YoutubeFailureKind(Enum):
    WORKSPACE_RESTRICTED = "workspace_restricted"
    PERMANENT = "permanent"
    OTHER = "other"


def classify_youtube_failure(error_details: str) -> YoutubeFailureKind:
    """Classify only errors that affect the access-mode fallback decision."""
    details = (error_details or "").lower()
    workspace_markers = (
        "this video is restricted",
        "google workspace administrator",
        "network administrator restrictions",
        "restricted mode",
        "sign in to confirm you're not a bot",
        "sign in to confirm you’re not a bot",
    )
    if any(marker in details for marker in workspace_markers):
        return YoutubeFailureKind.WORKSPACE_RESTRICTED

    permanent_markers = (
        "private video",
        "this video is private",
        "has been removed",
        "video is no longer available",
        "no longer available due to a copyright",
        "copyright claim",
        "account associated with this video has been terminated",
        "invalid url",
        "unsupported url",
    )
    if any(marker in details for marker in permanent_markers):
        return YoutubeFailureKind.PERMANENT
    return YoutubeFailureKind.OTHER


def next_youtube_access_mode(
    current_mode: YoutubeAccessMode,
    failure_kind: YoutubeFailureKind,
    *,
    transfer_started: bool,
    cookies_available: bool,
) -> YoutubeAccessMode | None:
    """Return the one allowed fallback mode, or None when the task must stop."""
    if transfer_started or failure_kind is YoutubeFailureKind.PERMANENT:
        return None
    if (
        current_mode is YoutubeAccessMode.NORMAL_NO_COOKIE
        and failure_kind is YoutubeFailureKind.WORKSPACE_RESTRICTED
    ):
        return YoutubeAccessMode.CLEAN_ANONYMOUS
    if current_mode is YoutubeAccessMode.CLEAN_ANONYMOUS and cookies_available:
        return YoutubeAccessMode.COOKIE
    return None


def build_youtube_access_args(
    mode: YoutubeAccessMode,
    *,
    use_cookies: bool,
    cookies_file_path: str,
    cookies_from_browser: str,
) -> list[str]:
    """Build access-only yt-dlp arguments for a single attempt."""
    if mode is YoutubeAccessMode.NORMAL_NO_COOKIE:
        return ["--no-cookies", "--no-cookies-from-browser"]
    if mode is YoutubeAccessMode.CLEAN_ANONYMOUS:
        return [
            "--ignore-config",
            "--no-cookies",
            "--no-cookies-from-browser",
        ]

    if use_cookies and cookies_file_path and os.path.isfile(cookies_file_path):
        return ["--cookies", cookies_file_path]
    browser = (cookies_from_browser or "").strip()
    if browser:
        return ["--cookies-from-browser", browser]
    return []

def init_worker_config(theme, thumb_cache_dir, user_agent, app_version, github_owner, github_repo):
    global APP_THEME, THUMBNAIL_CACHE_DIR, USER_AGENT, APP_VERSION, GITHUB_OWNER, GITHUB_REPO
    APP_THEME = theme
    THUMBNAIL_CACHE_DIR = thumb_cache_dir
    USER_AGENT = user_agent
    APP_VERSION = app_version
    GITHUB_OWNER = github_owner
    GITHUB_REPO = github_repo

def _normalize_proxy_url(proxy_url: str | None) -> str | None:
    """Return a proxy URL with credentials URL-encoded, or None if invalid/empty."""
    if not proxy_url:
        return None
    raw = proxy_url.strip()
    if not raw:
        return None
    working = raw if "://" in raw else f"http://{raw}"
    parsed = urllib.parse.urlparse(working)
    if not parsed.hostname:
        return None

    hostname = parsed.hostname
    if ':' in hostname and not hostname.startswith('[') and not hostname.endswith(']'):
        hostname = f"[{hostname}]"

    netloc_host = f"{hostname}"
    if parsed.port:
        netloc_host = f"{netloc_host}:{parsed.port}"

    if parsed.username is not None or parsed.password is not None:
        # [FIX-407] Unquote first to prevent double-encoding if input is already encoded
        raw_user = urllib.parse.unquote(parsed.username or "")
        raw_pass = urllib.parse.unquote(parsed.password or "")

        safe_user = urllib.parse.quote(raw_user, safe="")
        safe_pass = urllib.parse.quote(raw_pass, safe="")
        netloc_host = f"{safe_user}:{safe_pass}@{netloc_host}"

    return urllib.parse.urlunparse((
        parsed.scheme or "http",
        netloc_host,
        parsed.path or "",
        "",
        parsed.query,
        parsed.fragment
    ))  # [ZERO-LEAK-FIX]


def _build_proxy_handler(proxy_url: str | None):
    """Create a ProxyHandler with sanitized URL or return None if not usable."""
    safe_proxy = _normalize_proxy_url(proxy_url)
    if not safe_proxy:
        return None
    return urllib.request.ProxyHandler({'http': safe_proxy, 'https': safe_proxy})  # [ZERO-LEAK-FIX]


def _normalize_version_tag(tag: str) -> str:
    """Normalize a GitHub tag (e.g., 'v1.2.3') to a plain version string."""
    return tag.strip().lstrip("vV")


def _simple_version_tuple(version: str) -> tuple:
    """Convert a version string into a tuple for basic comparisons."""
    parts = []
    for part in re.split(r"[.\-_]", version):
        if part.isdigit():
            parts.append(int(part))
        else:
            parts.append(part)
    return tuple(parts)


def _is_version_newer(current_version: str, latest_version: str) -> bool:
    """Return True when latest_version is newer than current_version."""
    current = _normalize_version_tag(current_version or "0")
    latest = _normalize_version_tag(latest_version or "0")
    return _simple_version_tuple(latest) > _simple_version_tuple(current)


def _select_app_update_asset(release_data: dict) -> ReleaseAsset | None:
    """Return the exact v2 package only when GitHub supplied a usable digest."""
    assets = release_data.get("assets") or []
    for asset in assets:
        if str(asset.get("name", "")).casefold() != "app-update-v2.pkg":
            continue
        digest = str(asset.get("digest", "")).casefold()
        url = str(asset.get("browser_download_url", "")).strip()
        try:
            size = int(asset.get("size", 0))
        except (TypeError, ValueError):
            return None
        if (
            asset.get("state") != "uploaded"
            or not url
            or size <= 0
            or not re.fullmatch(r"sha256:[0-9a-f]{64}", digest)
        ):
            return None
        return ReleaseAsset(
            name="app-update-v2.pkg",
            url=url,
            sha256=digest.removeprefix("sha256:"),
            size=size,
        )
    return None

class DriveDownloadWorker(QObject):
    progress_update = Signal(str, int, str, str)  # task_id, percent, speed, eta
    metadata_retrieved = Signal(str, str, str, str)  # task_id, title, duration, resolution("N/A")
    log_message = Signal(str, str)  # task_id, message
    task_finished = Signal(str, str, bool, str, str)  # task_id, message, success, filepath, error_details
    started_processing = Signal(str) # task_id

    def __init__(self, task_id: str, file_id: str, download_dir: str, drive_service_instance):
        super().__init__()
        self.task_id = task_id
        self.file_id = file_id
        self.download_dir = download_dir
        self.drive_service = drive_service_instance
        self._is_running = True
        self._current_file_name = "Đang lấy tên file..."

    def _status_callback_adapter(self, msg_type, data):
        if not self._is_running:
            # Ngắt ngay lập tức để downloader dừng vòng lặp
            raise InterruptedError("User cancelled download")

        if msg_type == "metadata":
            file_name = data.get("name", "Không rõ tên")
            self._current_file_name = file_name
            self.metadata_retrieved.emit(self.task_id, file_name, "N/A", "N/A") # Duration and Resolution not applicable for Drive files
            self.log_message.emit(self.task_id, f"Metadata nhận được: Tên file='{file_name}', Kích thước dự kiến: {data.get('size',0)} bytes")
        elif msg_type == "progress":
            percent = data.get("progress_percent", 0)
            downloaded_bytes = data.get("downloaded_bytes", 0)
            # Speed/ETA might be harder to calculate consistently here, pass N/A
            self.progress_update.emit(self.task_id, percent, "N/A", "N/A")
        elif msg_type == "message":
            self.log_message.emit(self.task_id, f"[DriveDownloaderInternal] {data}")

    @Slot()
    def run(self):
        if not self._is_running:
            self.task_finished.emit(self.task_id, "Đã hủy trước khi bắt đầu (Drive)", False, "", "")
            return

        if not self.drive_service:
            self.log_message.emit(self.task_id, "Lỗi: Drive service không hợp lệ.")
            self.task_finished.emit(self.task_id, "Lỗi dịch vụ Drive", False, "", "Drive service không được khởi tạo.")
            return

        self.started_processing.emit(self.task_id)
        self.log_message.emit(self.task_id, f"Bắt đầu tải file Google Drive ID: {self.file_id}")

        try:
            success, message_or_filepath = gdrive_downloader.download_file_from_drive(
                self.drive_service,
                self.file_id,
                self.download_dir,
                status_callback=self._status_callback_adapter
            )

            if not self._is_running:
                self.task_finished.emit(self.task_id, "Đã hủy (Drive)", False, "", "Người dùng hủy tác vụ")
                return

            if success:
                final_file_path = message_or_filepath
                # Đảm bảo tên file đã được cập nhật nếu metadata callback chạy muộn
                if self._current_file_name == "Đang lấy tên file..." and os.path.exists(final_file_path):
                    self._current_file_name = os.path.basename(final_file_path)
                    self.metadata_retrieved.emit(self.task_id, self._current_file_name, "N/A", "N/A")

                self.task_finished.emit(self.task_id, "Hoàn thành! (Drive)", True, final_file_path, "")
            else:
                self.task_finished.emit(self.task_id, "Lỗi tải Drive", False, "", message_or_filepath)

        except Exception as e:
            if isinstance(e, InterruptedError) or not self._is_running:
                self.log_message.emit(self.task_id, "Đã hủy (Drive) qua ngoại lệ kiểm soát.")
                self.task_finished.emit(self.task_id, "Đã hủy (Drive)", False, "", "Người dùng hủy tác vụ")
            else:
                self.log_message.emit(self.task_id, f"Lỗi Exception trong DriveDownloadWorker: {type(e).__name__} - {e}")
                import traceback
                self.log_message.emit(self.task_id, f"Traceback: {traceback.format_exc()}")
                self.task_finished.emit(self.task_id, f"Lỗi worker Drive: {type(e).__name__}", False, "", str(e))
        finally:
            self._is_running = False

    def stop(self):
        # Hiện tại gdrive_downloader.download_file_from_drive không hỗ trợ hủy giữa chừng một cách trực tiếp.
        # Việc đặt cờ _is_running chỉ ngăn các emit tín hiệu sau khi stop được gọi.
        self.log_message.emit(self.task_id, "Yêu cầu dừng DriveDownloadWorker. (Lưu ý: Tải xuống hiện tại có thể vẫn hoàn tất nếu đã bắt đầu sâu).")
        self._is_running = False

class DriveFolderItemFetcher(QObject):
    """Worker để lấy danh sách các file trong một thư mục Google Drive."""
    finished_fetching = Signal(str, list) # task_id, list_of_files
    error_fetching = Signal(str, str)     # task_id, error_message
    log_message = Signal(str, str)        # task_id, message

    def __init__(self, task_id: str, folder_id: str, drive_service_instance):
        super().__init__()
        self.task_id = task_id
        self.folder_id = folder_id
        self.drive_service = drive_service_instance
        self._is_running = True

    def _status_callback_adapter(self, msg_type, data):
        if not self._is_running:
            raise InterruptedError("User cancelled folder listing")
        self.log_message.emit(self.task_id, data)

    @Slot()
    def run(self):
        if not self._is_running:
            self.error_fetching.emit(self.task_id, "Đã hủy lấy danh sách thư mục Drive.")
            return
        self.log_message.emit(self.task_id, f"Bắt đầu lấy danh sách file từ thư mục ID: {self.folder_id}")
        if not self.drive_service:
            self.error_fetching.emit(self.task_id, "Drive service không hợp lệ.")
            return

        try:
            files, error = gdrive_downloader.list_files_in_drive_folder(
                self.drive_service,
                self.folder_id,
                status_callback=self._status_callback_adapter
            )
        except Exception as exc:
            if not self._is_running or isinstance(exc, InterruptedError):
                self.error_fetching.emit(self.task_id, "Đã hủy lấy danh sách thư mục Drive.")
            else:
                self.error_fetching.emit(self.task_id, str(exc))
            return
        if not self._is_running:
            self.error_fetching.emit(self.task_id, "Đã hủy lấy danh sách thư mục Drive.")
            return
        if error:
            self.error_fetching.emit(self.task_id, error)
        else:
            self.finished_fetching.emit(self.task_id, files)

    def stop(self):
        self._is_running = False

# Thêm Worker cho việc xác thực Google Drive
class GoogleDriveAuthWorker(QObject):
    finished = Signal(object, str) # drive_service, message
    log_signal = Signal(str)

    def __init__(self, proxy_url: str | None = None):
        super().__init__()
        self._proxy_url = _normalize_proxy_url(proxy_url)  # [ZERO-LEAK-FIX]
        self._is_running = True

    @Slot()
    def run(self):
        auth_messages = []
        def _local_auth_status_callback(msg):
            auth_messages.append(msg)
            self.log_signal.emit(f"[DriveAuth] {msg}")

        self.log_signal.emit("Bắt đầu quá trình xác thực Google Drive...")
        try:
            drive_service, auth_error = google_drive_handler.authenticate_gdrive_user_flow(
                status_callback=_local_auth_status_callback,
                proxy_url=self._proxy_url
            )
        except Exception as exc:
            self.finished.emit(None, f"Lỗi xác thực Google Drive: {exc}")
            return
        if not self._is_running:
            self.finished.emit(None, "Đã hủy xác thực Google Drive.")
            return
        # Đảm bảo tất cả log từ authenticate_gdrive_user_flow đều đã được emit
        # QTimer.singleShot(100, lambda: self.log_signal.emit("\n".join(auth_messages)))


        if auth_error:
            self.finished.emit(None, f"Lỗi xác thực Google Drive: {auth_error}\n" + "\n".join(auth_messages))
        elif drive_service:
            self.finished.emit(drive_service, "Xác thực Google Drive thành công.\n" + "\n".join(auth_messages))
        else:
            self.finished.emit(None, "Không thể xác thực Google Drive (lỗi không rõ lý do).\n" + "\n".join(auth_messages))

    def stop(self):
        self._is_running = False

class DownloadWorker(QObject):
    progress_update = Signal(str, int, str, str)
    metadata_retrieved = Signal(str, str, str, str) # task_id, title, duration, resolution
    expected_duration_ready = Signal(str, str) # task_id, duration string HH:MM:SS
    log_message = Signal(str, str)
    task_finished = Signal(str, str, bool, str, str)
    started_processing = Signal(str)
    thumbnail_ready = Signal(str, QPixmap)

    def __init__(self, task_id: str, url: str, quality_format: str, download_dir: str,
                 yt_dlp_path: str, save_thumbnail_with_video: bool,
                 use_aria2c: bool, aria2c_args_str: str,
                 concurrent_fragments: int,
                 use_cookies: bool, cookies_file_path: str,
                 clean_filenames: bool,
                 proxy_url: str | None = None,
                 preferred_audio_format: str = "m4a",
                 cookies_from_browser: str = ""):
        super().__init__()
        self.task_id = task_id
        self.url = url
        self.quality_format = quality_format
        self.download_dir = download_dir
        self.yt_dlp_path = yt_dlp_path
        self._is_running = True
        self._process = None
        self.downloaded_file_path_internal = ""
        self.parsed_title = ""
        self.parsed_duration = ""
        self.parsed_resolution = ""
        self.current_progress = 0
        self.transfer_started = False
        self.save_thumbnail_with_video = save_thumbnail_with_video
        self._original_thumbnail_pixmap_data = None
        self.use_aria2c = use_aria2c
        self.aria2c_args_str = aria2c_args_str
        self.concurrent_fragments = concurrent_fragments
        self.use_cookies = use_cookies
        self.cookies_file_path = cookies_file_path
        self.cookies_from_browser = (cookies_from_browser or "").strip()
        self.clean_filenames = clean_filenames
        self.preferred_audio_format = (preferred_audio_format or "m4a").lower()
        self.proxy_url = _normalize_proxy_url(proxy_url)  # [ZERO-LEAK-FIX]
    def _extract_video_id(self, youtube_url):
        # ... (giữ nguyên) ...
        patterns = [
            r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/watch\?v=([^&]+)',
            r'(?:https?:\/\/)?(?:www\.)?youtu\.be\/([^?]+)',
            r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/embed\/([^?]+)',
            r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/v\/([^?]+)'
        ]
        for pattern in patterns:
            match = re.search(pattern, youtube_url)
            if match: return match.group(1)
        return None

    def _fetch_thumbnail(self, attempt_cache=True):
        # ... (giữ nguyên logic _fetch_thumbnail, đảm bảo nó dùng self.log_message.emit) ...
        self.log_message.emit(self.task_id, f"Bắt đầu _fetch_thumbnail. Save with video: {self.save_thumbnail_with_video}, Attempt cache: {attempt_cache}")
        video_id = self._extract_video_id(self.url)
        thumbnail_pixmap_display = None
        pixmap_data_to_save = None

        if not video_id:
            self.log_message.emit(self.task_id, "Không thể trích xuất video_id từ URL để lấy thumbnail.")
            default_pixmap = QPixmap(120, 90); default_pixmap.fill(QColor(APP_THEME["thumb_bg_alt"]))
            painter = QPainter(default_pixmap); painter.setPen(QColor(APP_THEME["thumb_text_alt"])); painter.drawText(default_pixmap.rect(), Qt.AlignCenter, "No Img"); painter.end()
            self.thumbnail_ready.emit(self.task_id, default_pixmap)
            self._original_thumbnail_pixmap_data = None
            return

        if attempt_cache and not self.save_thumbnail_with_video and os.path.exists(THUMBNAIL_CACHE_DIR):
            possible_cached_filenames = [f"{video_id}_maxres.jpg", f"{video_id}_sd.jpg", f"{video_id}_hq.jpg", f"{video_id}_mq.jpg", f"{video_id}.jpg"]
            for fname in possible_cached_filenames:
                path_to_check = os.path.join(THUMBNAIL_CACHE_DIR, fname)
                if os.path.exists(path_to_check):
                    loaded_pixmap = QPixmap()
                    if loaded_pixmap.load(path_to_check) and not loaded_pixmap.isNull():
                        pixmap_data_to_save = loaded_pixmap
                        thumbnail_pixmap_display = loaded_pixmap.scaled(120, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        self.log_message.emit(self.task_id, f"Thumbnail tải từ cache: {path_to_check}.")
                        break
            if pixmap_data_to_save: self.log_message.emit(self.task_id, "Đã sử dụng thumbnail từ cache.")

        if not pixmap_data_to_save:
            self.log_message.emit(self.task_id, f"Không có cache hoặc yêu cầu tải mới. Thử tải từ mạng cho video_id: {video_id}")
            thumbnail_quality_urls = [
                (f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg", "maxresdefault"),
                (f"https://i.ytimg.com/vi/{video_id}/sddefault.jpg", "sddefault"),
                (f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg", "hqdefault"),
                (f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg", "mqdefault")
            ]
            for thumb_url, quality_name in thumbnail_quality_urls:
                self.log_message.emit(self.task_id, f"Thử tải thumbnail '{quality_name}' từ: {thumb_url}")
                try:
                    headers = {'User-Agent': USER_AGENT}  # [ZERO-LEAK-FIX]
                    req = urllib.request.Request(thumb_url, headers=headers)
                    proxy_handler = _build_proxy_handler(self.proxy_url)
                    opener = urllib.request.build_opener(proxy_handler) if proxy_handler else urllib.request.build_opener()  # [ZERO-LEAK-FIX]
                    with opener.open(req, timeout=8) as response: # Giảm timeout
                        data = response.read()
                        potential_pixmap = QPixmap()
                        if potential_pixmap.loadFromData(data) and not potential_pixmap.isNull():
                            is_placeholder = (quality_name == "maxresdefault" and (potential_pixmap.width() < 640 or potential_pixmap.height() < 480))
                            if not is_placeholder:
                                pixmap_data_to_save = potential_pixmap
                                thumbnail_pixmap_display = potential_pixmap.scaled(120, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                                self.log_message.emit(self.task_id, f"Tải thành công thumbnail '{quality_name}'.")
                                if attempt_cache and not self.save_thumbnail_with_video:
                                    try:
                                        if not os.path.exists(THUMBNAIL_CACHE_DIR): os.makedirs(THUMBNAIL_CACHE_DIR)
                                        cache_filename = f"{video_id}_{quality_name}.jpg"
                                        cache_save_path = os.path.join(THUMBNAIL_CACHE_DIR, cache_filename)
                                        if pixmap_data_to_save.save(cache_save_path, "JPG", 90):
                                            self.log_message.emit(self.task_id, f"Thumbnail '{quality_name}' đã cache tại: {cache_save_path}")
                                    except Exception as e_cache: self.log_message.emit(self.task_id, f"Lỗi cache thumb '{quality_name}': {e_cache}")
                                break
                except urllib.error.HTTPError as e_http:
                    if e_http.code == 404: self.log_message.emit(self.task_id, f"Thumb '{quality_name}' ({thumb_url}) không tồn tại (404).")
                    else: self.log_message.emit(self.task_id, f"Lỗi HTTP {e_http.code} khi tải thumb '{quality_name}': {thumb_url}")
                except urllib.error.URLError as e_url:
                    self.log_message.emit(self.task_id, f"Lỗi URL khi tải thumb '{quality_name}' ({thumb_url}): {e_url.reason}. Dừng thử tải.")
                    break
                except Exception as e: self.log_message.emit(self.task_id, f"Lỗi khác khi tải thumb '{quality_name}' từ {thumb_url}: {e}")
            if not pixmap_data_to_save: self.log_message.emit(self.task_id, "Không thể tải bất kỳ thumbnail nào.")

        if thumbnail_pixmap_display and not thumbnail_pixmap_display.isNull():
            self.thumbnail_ready.emit(self.task_id, thumbnail_pixmap_display)
        else:
            default_pixmap = QPixmap(120, 90); default_pixmap.fill(QColor(APP_THEME["thumb_bg_alt"]))
            painter = QPainter(default_pixmap); painter.setPen(QColor(APP_THEME["thumb_text_alt"])); painter.drawText(default_pixmap.rect(), Qt.AlignCenter, "No Img"); painter.end()
            self.thumbnail_ready.emit(self.task_id, default_pixmap)

        if pixmap_data_to_save and not pixmap_data_to_save.isNull():
            self._original_thumbnail_pixmap_data = pixmap_data_to_save
        else:
            self._original_thumbnail_pixmap_data = None

    def _kill_process_tree(self):
        """Force kill yt-dlp and any children to avoid zombies."""
        if not self._process or self._process.poll() is not None:
            return
        try:
            if platform.system() == "Windows":
                subprocess.run(f"taskkill /F /T /PID {self._process.pid}", shell=True)
            else:
                os.killpg(os.getpgid(self._process.pid), signal.SIGKILL)
        except Exception as e_stop:
            try:
                self._process.kill()
            except Exception:
                pass
            self.log_message.emit(self.task_id, f"Lỗi khi kill tiến trình yt-dlp: {e_stop}")

    def _cookies_available(self) -> bool:
        file_available = bool(
            self.use_cookies
            and self.cookies_file_path
            and os.path.isfile(self.cookies_file_path)
        )
        return file_available or bool(self.cookies_from_browser)

    def _execute_yt_dlp_command(self, command_args: list[str]) -> tuple[int, str]:
        """Run one fresh yt-dlp process and return its code and combined output."""
        popen_kwargs = {
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "text": True,
            "encoding": "utf-8",
            "errors": "replace",
            "bufsize": 1,
            "creationflags": subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
        }
        if platform.system() != "Windows":
            popen_kwargs["start_new_session"] = True

        output_lines = []
        process = subprocess.Popen(command_args, **popen_kwargs)
        self._process = process
        try:
            if process.stdout:
                for line in iter(process.stdout.readline, ""):
                    if not self._is_running:
                        break
                    stripped = line.strip()
                    if stripped:
                        output_lines.append(stripped)
                    self._parse_yt_dlp_output(line)
                    self.log_message.emit(self.task_id, f"YT-DLP: {stripped}")
                process.stdout.close()

            if not self._is_running:
                self._kill_process_tree()
            process.wait()
            return process.returncode, "\n".join(output_lines[-20:])
        finally:
            self._process = None

    def _run_access_attempts(self, base_command: list[str]) -> tuple[int, str]:
        """Run the bounded normal -> clean anonymous -> cookie fallback chain."""
        mode = YoutubeAccessMode.NORMAL_NO_COOKIE
        cookies_available = self._cookies_available()

        while True:
            access_args = build_youtube_access_args(
                mode,
                use_cookies=self.use_cookies,
                cookies_file_path=self.cookies_file_path,
                cookies_from_browser=self.cookies_from_browser,
            )
            command_args = [base_command[0], *access_args, *base_command[1:]]
            self.log_message.emit(
                self.task_id,
                f"Lệnh: yt-dlp ({mode.value})",
            )

            return_code, error_details = self._execute_yt_dlp_command(command_args)
            if return_code == 0 or not self._is_running:
                return return_code, error_details

            failure_kind = classify_youtube_failure(error_details)
            next_mode = next_youtube_access_mode(
                mode,
                failure_kind,
                transfer_started=self.transfer_started,
                cookies_available=cookies_available,
            )
            if next_mode is None:
                return return_code, error_details

            if next_mode is YoutubeAccessMode.CLEAN_ANONYMOUS:
                self.log_message.emit(
                    self.task_id,
                    "Video bị giới hạn Workspace. Đang thử lại ở chế độ ẩn danh sạch...",
                )
            else:
                self.log_message.emit(
                    self.task_id,
                    "Chế độ ẩn danh vẫn thất bại. Đang thử cookie lần cuối...",
                )
            mode = next_mode

    def _cleanup_partial_files(self):
        """Remove partial/temporary files left after cancellation or failed verification."""
        video_id = self._extract_video_id(self.url) or ""
        temp_exts = (".part", ".ytdl", ".aria2", ".temp", ".m4a", ".mp4")
        paths_to_delete = set()

        if video_id and os.path.isdir(self.download_dir):
            try:
                for name in os.listdir(self.download_dir):
                    lower_name = name.lower()
                    if video_id in name and lower_name.endswith(temp_exts):
                        paths_to_delete.add(os.path.join(self.download_dir, name))
            except Exception as e_ls:
                self.log_message.emit(self.task_id, f"Lỗi khi quét file tạm: {e_ls}")

        if self.downloaded_file_path_internal:
            paths_to_delete.add(self.downloaded_file_path_internal)

        for path in paths_to_delete:
            if not path or not os.path.exists(path):
                continue
            try:
                os.remove(path)
                self.log_message.emit(self.task_id, f"Đã xóa file tạm: {path}")
            except PermissionError:
                time.sleep(0.1)
                try:
                    os.remove(path)
                    self.log_message.emit(self.task_id, f"Đã xóa file tạm sau khi chờ khóa: {path}")
                except Exception as e_del:
                    self.log_message.emit(self.task_id, f"Không thể xóa file tạm {path}: {e_del}")
            except Exception as e_del:
                self.log_message.emit(self.task_id, f"Không thể xóa file tạm {path}: {e_del}")

    def _parse_yt_dlp_output(self, line):
        line = line.strip()
        if not line:
            return

        if re.search(r"\[download\]\s+Destination:", line, re.IGNORECASE):
            self.transfer_started = True

        # Cờ để kiểm tra xem có thông tin metadata nào được cập nhật từ dòng log này không
        metadata_changed = False

        # --- 1. Phân tích thông tin Metadata (Title, Duration, Resolution) ---

        # Ưu tiên parse title tường minh trước
        title_match_explicit = re.search(r"\[info\]\s+Title:\s*(.+)", line, re.IGNORECASE)
        if title_match_explicit and not self.parsed_title:
            new_title = title_match_explicit.group(1).strip()
            if new_title != self.parsed_title:
                self.parsed_title = new_title
                metadata_changed = True

        # Parse title từ các dòng log khác nếu chưa có
        if not self.parsed_title:
            title_match_downloading = re.search(r"\[info\]\s+(.+?):\s+Downloading", line, re.IGNORECASE)
            if title_match_downloading:
                new_title = title_match_downloading.group(1).strip()
                if new_title != self.parsed_title:
                    self.parsed_title = new_title
                    metadata_changed = True

        # Parse title từ tên file (ít ưu tiên hơn)
        if not self.parsed_title:
            title_match_dest = re.search(r"\[download\]\s+Destination:\s*(?:.+[/\\])?(.+?)(?:\.\w{2,4})?$", line)
            if title_match_dest:
                # Loại bỏ ID video khỏi tên file nếu có, ví dụ: "My Video [aBcDe123Fg].mp4"
                base_name = re.sub(r'\s*\[[^\]]{11,}\]$', '', os.path.splitext(title_match_dest.group(1).strip())[0])
                if base_name and base_name != self.parsed_title:
                    self.parsed_title = base_name
                    metadata_changed = True

        # Parse duration
        duration_match = re.search(r"\[info\]\s+Duration:\s+(\d{1,2}:\d{2}(?::\d{2})?)", line, re.IGNORECASE)
        if duration_match and not self.parsed_duration:
            new_duration = duration_match.group(1).strip()
            if new_duration != self.parsed_duration:
                self.parsed_duration = new_duration
                metadata_changed = True
                try:
                    self.expected_duration_ready.emit(self.task_id, self.parsed_duration)
                except Exception:
                    pass

        # Parse resolution
        resolution_match = re.search(r'\[info\].*?[Rr]es:\s*(\d{3,4}x\d{3,4})|\[info\].*?\s(\d{3,4}x\d{3,4})\s.*', line)
        if resolution_match and not self.parsed_resolution:
            found_res = resolution_match.group(1) or resolution_match.group(2)
            if found_res:
                new_res = found_res.strip()
                if new_res != self.parsed_resolution:
                    self.parsed_resolution = new_res
                    self.log_message.emit(self.task_id, f"Phát hiện độ phân giải: {self.parsed_resolution}")
                    metadata_changed = True

        # --- Gửi tín hiệu TỔNG HỢP nếu có bất kỳ thay đổi nào ---
        if metadata_changed:
            self.metadata_retrieved.emit(self.task_id, self.parsed_title, self.parsed_duration, self.parsed_resolution)

        # --- 2. Phân tích thông tin Tiến trình (Progress) ---
        # Logic này chỉ cập nhật thanh progress, không liên quan metadata nên có thể return sớm
        progress_regex = re.compile(r"\[download\]\s+(?P<percent>[\d\.]+)%\s+of\s+(?:~)?(?P<size>[\d\.]+\s?\w*iB)(?:\s+at\s+(?P<speed>[\d\.]+\s?\w*iB/s)\s+ETA\s+(?P<eta>[\d:]+))?")
        match_progress = progress_regex.search(line)
        if match_progress:
            self.transfer_started = True
            percent_str = match_progress.group("percent")
            speed = match_progress.group("speed") or "N/A"
            eta = match_progress.group("eta") or "N/A"
            try:
                percent = int(float(percent_str))
            except ValueError:
                percent = self.current_progress
            self.current_progress = percent
            self.progress_update.emit(self.task_id, percent, speed, eta)
            return # Dòng progress không chứa thông tin nào khác, thoát sớm

        # Cập nhật trạng thái hậu kỳ để UI thân thiện hơn
        if "[Merger]" in line:
            self.progress_update.emit(self.task_id, 100, "Đang xử lý...", "")
        elif "[ExtractAudio]" in line or "[ffmpeg]" in line:
            self.progress_update.emit(self.task_id, 100, "Đang chuyển đổi...", "")
        elif "[Fixup" in line:
            self.progress_update.emit(self.task_id, 100, "Đang hoàn tất...", "")

        # --- 3. Phân tích thông tin Đường dẫn file cuối cùng ---
        # Logic này xác định tên file cuối cùng, không cần emit metadata
        merger_regex = re.compile(r"\[Merger\] Merging formats into \"(.+?)\"")
        match_merger = merger_regex.search(line)
        if match_merger:
            path_from_log = match_merger.group(1)
            # Đảm bảo đường dẫn là tuyệt đối
            if os.path.isabs(path_from_log) and path_from_log.startswith(os.path.abspath(self.download_dir)):
                self.downloaded_file_path_internal = path_from_log
            else:
                self.downloaded_file_path_internal = os.path.join(self.download_dir, os.path.basename(path_from_log))
            return # Thoát sớm

        ffmpeg_dest_regex = re.compile(r"\[(?:ffmpeg|ExtractAudio|FixupM3u8|FixupM4a|FixupTimestamp)\] Destination:\s*(.+)")
        match_ffmpeg_dest = ffmpeg_dest_regex.search(line)
        if match_ffmpeg_dest:
            fname_from_log = match_ffmpeg_dest.group(1)
            if not self.downloaded_file_path_internal: # Chỉ gán nếu chưa có từ Merger
                if os.path.isabs(fname_from_log) and fname_from_log.startswith(os.path.abspath(self.download_dir)):
                    self.downloaded_file_path_internal = fname_from_log
                else:
                    self.downloaded_file_path_internal = os.path.join(self.download_dir, os.path.basename(fname_from_log))
            return # Thoát sớm

        already_downloaded_regex = re.compile(r"\[download\]\s*(.+?)\s+has already been downloaded")
        match_already_downloaded = already_downloaded_regex.search(line)
        if match_already_downloaded:
            full_path_from_log = match_already_downloaded.group(1).strip()
            if not os.path.isabs(full_path_from_log):
                full_path_from_log = os.path.join(self.download_dir, os.path.basename(full_path_from_log))

            if full_path_from_log.startswith(os.path.abspath(self.download_dir)):
                 self.downloaded_file_path_internal = full_path_from_log
            self.progress_update.emit(self.task_id, 100, "N/A", "00:00")
            return

    @Slot()
    def run(self):
        if not self._is_running: # ... (giữ nguyên) ...
            self.task_finished.emit(self.task_id, "Đã hủy trước khi bắt đầu", False, "", "")
            return

        self.started_processing.emit(self.task_id)
        self.log_message.emit(self.task_id, f"Worker run: Lưu thumbnail: {self.save_thumbnail_with_video}, Dùng aria2c: {self.use_aria2c}")
        self._fetch_thumbnail(attempt_cache=True)
        # ... (log _original_thumbnail_pixmap_data giữ nguyên) ...

        self.log_message.emit(self.task_id, f"Bắt đầu tải: {self.url} với chất lượng: {self.quality_format}")
        # Output template không đổi, yt-dlp sẽ tự xử lý thư mục con nếu tải playlist với -o TEMPLATE
        # Nhưng vì giờ chỉ tải video đơn lẻ, template này là cho file đơn
        output_filename_template = os.path.join(self.download_dir, '%(title)s.%(ext)s')

        command_args = [
            self.yt_dlp_path,
            '-o', output_filename_template,
            '--progress',
            '--no-colors',
            '--encoding', 'utf-8',
            '--no-playlist', # LUÔN THÊM: Vì worker này chỉ xử lý video đơn
        ]

        command_args.extend(main_logic.get_yt_dlp_js_runtime_args())

        # [UPDATE 1] Global Retry Settings & Audio Logic
        command_args.extend([
            '--retries', '10',           # Retry HTTP errors 10 times
            '--fragment-retries', '10',  # Retry fragments (DASH)
            '--file-access-retries', '3' # Retry file I/O
        ])

        effective_proxy_url = self.proxy_url
        # Add proxy support if available
        if effective_proxy_url:
            command_args.extend(['--proxy', effective_proxy_url])
            self.log_message.emit(self.task_id, "Sử dụng proxy đã cấu hình cho yt-dlp.")  # [ZERO-LEAK-FIX]

        # Cookie arguments are added only by the bounded access fallback loop.
        self.log_message.emit(self.task_id, "Chế độ tải video đơn: Sử dụng --no-playlist.")

        if self.use_aria2c:
            self.log_message.emit(self.task_id, "Sử dụng aria2c làm trình tải bên ngoài.")
            command_args.extend(['--downloader', 'aria2c'])
            aria2c_args_value = (self.aria2c_args_str or "").strip()
            if aria2c_args_value:
                self.log_message.emit(self.task_id, "Đã áp dụng đối số aria2c tùy chỉnh.")
            else: # Có thể thêm args mặc định an toàn cho aria2c nếu người dùng không nhập
                default_aria_args = "-j 5 -x 5 -s 5 -k 1M" # Ví dụ args mặc định nhẹ nhàng
                aria2c_args_value = default_aria_args
                self.log_message.emit(self.task_id, f"Sử dụng aria2c với đối số mặc định: {default_aria_args}")

            if effective_proxy_url:
                aria2c_args_value = f'--all-proxy="{effective_proxy_url}" {aria2c_args_value}'.strip()
                self.log_message.emit(self.task_id, "Đã ép aria2c sử dụng proxy đã cấu hình.")  # [ZERO-LEAK-FIX]

            command_args.extend(['--downloader-args', f'aria2c:{aria2c_args_value}'])  # [ZERO-LEAK-FIX]
        else: # Nếu không dùng aria2c, có thể dùng --concurrent-fragments của yt-dlp
            if self.concurrent_fragments > 1:
                 command_args.extend(['--concurrent-fragments', str(self.concurrent_fragments)])
                 self.log_message.emit(self.task_id, f"Sử dụng --concurrent-fragments {self.concurrent_fragments}")

        # Kiểm tra nếu là yêu cầu tải âm thanh dựa vào mapping "Audio (M4A)"
        is_audio_request = False
        try:
            # self.quality_format đến từ self.quality_options_map["Audio (M4A)"] => chứa 'bestaudio'
            is_audio_request = 'bestaudio' in (self.quality_format or '')
        except Exception:
            is_audio_request = False

        if is_audio_request:
            fmt = (self.preferred_audio_format or "").lower()
            if fmt == 'm4a':
                # [STRATEGY: Native M4A + No Fixup]
                # User requires original Unicode filenames.
                # We MUST disable --fixup because ffmpeg often fails on Unicode paths in Windows,
                # causing 0-byte/corrupt files.
                # Format 140 is already a valid M4A stream, so fixup is optional.
                self.log_message.emit(self.task_id, "Chế độ tải Audio M4A: Format 140 (Nguyên bản) - Bỏ qua Fixup.")
                
                command_args.extend([
                    '-f', '140/bestaudio[ext=m4a]', 
                    #'--fixup', 'never',  # CRITICAL: Prevent ffmpeg execution to avoid corruption
                    '--no-mtime'
                ])
                # Note: NO --restrict-filenames (Keep original name)
                command_args.append(self.url)
            else:
                # Các định dạng khác (mp3, wav) vẫn cần chuyển đổi
                self.log_message.emit(self.task_id, f"Chế độ tải Audio {fmt.upper()}: Có chuyển đổi FFmpeg (-x).")
                command_args.extend(['-x', '--audio-format', fmt, '--audio-quality', '0'])
                command_args.append(self.url)
        else:
            # Video logic
            command_args.extend(['--merge-output-format', 'mp4'])
            if self.quality_format:
                command_args.extend(['-f', self.quality_format])
            command_args.append(self.url)
        try:
            return_code, final_error_details_str = self._run_access_attempts(command_args)

            if not self._is_running:
                try:
                    self._cleanup_partial_files()
                except Exception as cleanup_error:
                    self.log_message.emit(self.task_id, f"Lỗi khi dọn file tạm sau hủy: {cleanup_error}")
                self.task_finished.emit(self.task_id, "Đã hủy", False, "", "Người dùng hủy tác vụ")
                return

            final_file_path = self.downloaded_file_path_internal

            # [UPDATE 2] Manual File Scan Strategy
            if return_code == 0 and not final_file_path:
                self.log_message.emit(self.task_id, "Log không trả về đường dẫn. Tiến hành quét thư mục để tìm file...")
                
                # Strategy: Scan download_dir for the newest file that loosely matches the Title on UI.
                target_title = self.parsed_title
                
                if target_title and os.path.exists(self.download_dir):
                    try:
                        # 1. Get all files
                        files = [f for f in os.listdir(self.download_dir) if os.path.isfile(os.path.join(self.download_dir, f))]
                        
                        # 2. Filter relevant extensions (m4a, mp4, webm, etc.)
                        extensions = ('.m4a', '.mp4', '.webm', '.mkv', '.mp3', '.wav')
                        candidates = [f for f in files if f.lower().endswith(extensions)]
                        
                        # 3. Sort by Modification Time (Newest first) - This is key for picking the just-downloaded file
                        candidates.sort(key=lambda x: os.path.getmtime(os.path.join(self.download_dir, x)), reverse=True)
                        
                        # 4. Fuzzy Match
                        # Simple normalization: Remove special chars to compare Title vs Filename
                        import re
                        def normalize(s): return re.sub(r'[^\w\s]', '', s).lower()
                        norm_title = normalize(target_title)
                        
                        found_candidate = None
                        
                        # Check top 5 newest files
                        for fname in candidates[:5]: 
                            norm_fname = normalize(fname)
                            # Logic: If the UI title contains words present in filename or vice versa
                            # We assume the file starts with the title (yt-dlp default behavior)
                            if norm_title in norm_fname or norm_fname in norm_title:
                                found_candidate = os.path.join(self.download_dir, fname)
                                break
                        
                        if found_candidate:
                            final_file_path = found_candidate
                            self.downloaded_file_path_internal = final_file_path
                            self.log_message.emit(self.task_id, f"Đã tìm thấy file thủ công: '{os.path.basename(final_file_path)}'")
                        else:
                            # Last resort: Take the absolutely newest file if it was created in the last 60 seconds
                            if candidates:
                                newest_file = os.path.join(self.download_dir, candidates[0])
                                if time.time() - os.path.getmtime(newest_file) < 60:
                                    final_file_path = newest_file
                                    self.downloaded_file_path_internal = final_file_path
                                    self.log_message.emit(self.task_id, f"Lấy file mới nhất vừa tạo: '{os.path.basename(final_file_path)}'")

                    except Exception as e_scan:
                        self.log_message.emit(self.task_id, f"Lỗi khi quét tìm file: {e_scan}")


            if return_code == 0 and final_file_path and os.path.exists(final_file_path):
                if self.save_thumbnail_with_video and self._original_thumbnail_pixmap_data and not self._original_thumbnail_pixmap_data.isNull():
                    try:
                        video_filename_no_ext, _ = os.path.splitext(os.path.basename(final_file_path))
                        thumbnail_filename = f"{video_filename_no_ext}.jpg"
                        thumbnail_save_path = os.path.join(os.path.dirname(final_file_path), thumbnail_filename)
                        if self._original_thumbnail_pixmap_data.save(thumbnail_save_path, "JPG", 85):
                            self.log_message.emit(self.task_id, f"Đã lưu thumbnail chung: {thumbnail_save_path}")
                        else: self.log_message.emit(self.task_id, f"Lỗi lưu thumbnail chung tại {thumbnail_save_path}")
                    except Exception as e_save_thumb: self.log_message.emit(self.task_id, f"Lỗi ngoại lệ khi lưu thumbnail chung: {e_save_thumb}")
                elif self.save_thumbnail_with_video : self.log_message.emit(self.task_id, "CẢNH BÁO: Yêu cầu lưu thumbnail chung nhưng không có dữ liệu thumbnail.")

            if final_file_path and os.path.exists(final_file_path): # Tinh chỉnh tiêu đề
                video_id_from_url = self._extract_video_id(self.url)
                is_parsed_title_weak = not self.parsed_title or \
                                   (video_id_from_url and self.parsed_title == video_id_from_url) or \
                                   len(self.parsed_title) < 10 or \
                                   self.parsed_title.startswith("Đang lấy TT:") or \
                                   self.parsed_title == "N/A" or "untitled_video" in self.parsed_title
                if is_parsed_title_weak:
                    title_from_filename_base = os.path.splitext(os.path.basename(final_file_path))[0]
                    title_candidate_from_filename = title_from_filename_base
                    if video_id_from_url:
                        expected_suffix_in_filename = f" [{video_id_from_url}]"
                        if title_from_filename_base.endswith(expected_suffix_in_filename):
                            title_candidate_from_filename = title_from_filename_base[:-len(expected_suffix_in_filename)].strip()
                    if title_candidate_from_filename and title_candidate_from_filename != self.parsed_title:
                        self.log_message.emit(self.task_id, f"Tinh chỉnh tiêu đề từ tên file. Cũ: '{self.parsed_title}', Mới: '{title_candidate_from_filename}'")
                        self.parsed_title = title_candidate_from_filename
                        self.metadata_retrieved.emit(self.task_id, self.parsed_title, self.parsed_duration, self.parsed_resolution)

            if self._is_running:
                if return_code == 0:
                    if final_file_path and os.path.exists(final_file_path) and os.path.getsize(final_file_path) > 100: # Kiểm tra size > 100 bytes
                        self.task_finished.emit(self.task_id, "Hoàn thành!", True, final_file_path, "")
                    elif final_file_path:
                        self.log_message.emit(self.task_id, f"Lỗi file sau tải: path='{final_file_path}' nhưng không qua kiểm tra exists/size.")
                        self.task_finished.emit(self.task_id, "Lỗi file sau tải", False, final_file_path, f"File '{os.path.basename(final_file_path)}' có vấn đề (không tồn tại hoặc size nhỏ).")
                    else:
                        self.log_message.emit(self.task_id, "Lỗi: Không có final_file_path hợp lệ sau khi tải thành công.")
                        self.task_finished.emit(self.task_id, "Lỗi (không rõ file)", False, "", "Không thể xác định đường dẫn tệp video đã tải.")
                else:
                    error_msg_ui = f"Lỗi yt-dlp (mã: {return_code})"
                    self.log_message.emit(self.task_id, f"Lỗi yt-dlp mã {return_code}. Chi tiết stderr: {final_error_details_str}")
                    self.task_finished.emit(self.task_id, error_msg_ui, False, "", final_error_details_str or "Lỗi không xác định từ yt-dlp.")
        except Exception as e:
            import traceback
            if self._is_running:
                self.log_message.emit(self.task_id, f"Lỗi Exception trong worker run: {type(e).__name__} - {e}")
                self.log_message.emit(self.task_id, f"Traceback: {traceback.format_exc()}")
                self.task_finished.emit(self.task_id, f"Lỗi worker: {type(e).__name__}", False, "", str(e))
            else:
                self.log_message.emit(self.task_id, f"Lỗi ngoại lệ xảy ra trong quá trình hủy: {e}")
                self.log_message.emit(self.task_id, f"Traceback: {traceback.format_exc()}")
                self.task_finished.emit(self.task_id, "Đã hủy (có lỗi)", False, "", f"Hủy với lỗi phụ: {e}")
        finally:
            self._is_running = False
            self._process = None

    def stop(self):
        """Yêu cầu dừng tải mà không chặn UI (fire-and-forget)."""
        if not self._is_running:
            return

        self._is_running = False
        self.log_message.emit(self.task_id, "Đang yêu cầu dừng (Gửi lệnh hủy bất đồng bộ)...")

        def _async_kill_task():
            if self._process and self._process.poll() is None:
                self.log_message.emit(self.task_id, "Đang kill process trong luồng phụ...")
                try:
                    self._kill_process_tree()
                except Exception as e_kill:
                    self.log_message.emit(self.task_id, f"Lỗi khi kill tiến trình (async): {e_kill}")
            else:
                self.log_message.emit(self.task_id, "Tiến trình đã kết thúc trước khi kill, bỏ qua.")

        threading.Thread(target=_async_kill_task, daemon=True).start()

class VerificationWorker(QObject):
    verification_started = Signal(str)
    verification_finished = Signal(str, object)
    lifecycle_finished = Signal()

    def __init__(self, task_id: str, file_path: str):
        super().__init__()
        self.task_id = task_id
        self.file_path = file_path
        self._is_running = True
        self._process = None

    def _set_process(self, process):
        self._process = process

    def _kill_ffprobe_process(self):
        if self._process and self._process.poll() is None:
            try:
                if platform.system() == "Windows":
                    subprocess.run(f"taskkill /F /T /PID {self._process.pid}", shell=True)
                else:
                    os.killpg(os.getpgid(self._process.pid), signal.SIGKILL)
            except Exception:
                try:
                    self._process.kill()
                except Exception:
                    pass

    @Slot()
    def run(self):
        try:
            if not self._is_running or not video_verifier or not video_verifier.FFPROBE_CMD_TO_USE:
                if video_verifier and not video_verifier.FFPROBE_CMD_TO_USE :
                    dummy_result = video_verifier.VerificationResult()
                    dummy_result.error_message = "FFprobe không sẵn sàng."
                    self.verification_finished.emit(self.task_id, dummy_result)
                return

            self.verification_started.emit(self.task_id)
            result = video_verifier.verify_video_file(self.file_path, process_callback=self._set_process)
            if self._is_running:
                self.verification_finished.emit(self.task_id, result)
        finally:
            self.lifecycle_finished.emit()

    def stop(self):
        self._is_running = False
        self._kill_ffprobe_process()

class ThumbnailFetcher(QObject):
    thumbnail_ready = Signal(str, QPixmap) # task_id, pixmap
    log_message = Signal(str, str) # task_id, message (tùy chọn)
    lifecycle_finished = Signal()

    def __init__(self, task_id: str, url: str, proxy_url: str | None = None):
        super().__init__()
        self.task_id = task_id
        self.url = url
        self.proxy_url = _normalize_proxy_url(proxy_url)  # [ZERO-LEAK-FIX]
        self._is_running = True

    def _extract_video_id(self, youtube_url): # Copy từ DownloadWorker
        patterns = [
            r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/watch\?v=([^&]+)',
            r'(?:https?:\/\/)?(?:www\.)?youtu\.be\/([^?]+)',
            r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/embed\/([^?]+)',
            r'(?:https?:\/\/)?(?:www\.)?youtube\.com\/v\/([^?]+)'
        ]
        for pattern in patterns:
            match = re.search(pattern, youtube_url)
            if match: return match.group(1)
        return None

    @Slot()
    def fetch(self):
        try:
            if self._is_running:
                self._fetch()
        finally:
            self.lifecycle_finished.emit()

    def _fetch(self, attempt_cache=True): # Tương tự _fetch_thumbnail của DownloadWorker
        video_id = self._extract_video_id(self.url)
        thumbnail_pixmap = None

        if video_id and attempt_cache and os.path.exists(THUMBNAIL_CACHE_DIR):
            cached_thumb_path = os.path.join(THUMBNAIL_CACHE_DIR, f"{video_id}.jpg")
            if os.path.exists(cached_thumb_path):
                pixmap = QPixmap()
                if pixmap.load(cached_thumb_path):
                    thumbnail_pixmap = pixmap.scaled(120, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation)

        if not thumbnail_pixmap and video_id:
            thumbnail_url = f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"
            try:
                proxy_handler = _build_proxy_handler(self.proxy_url)
                opener = urllib.request.build_opener(proxy_handler) if proxy_handler else urllib.request.build_opener()  # [ZERO-LEAK-FIX]
                req = urllib.request.Request(thumbnail_url, headers={'User-Agent': USER_AGENT})  # [ZERO-LEAK-FIX]
                with opener.open(req, timeout=10) as response:
                    data = response.read()
                    pixmap = QPixmap()
                    if pixmap.loadFromData(data):
                        thumbnail_pixmap = pixmap.scaled(120, 90, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                        if attempt_cache:
                            try:
                                if not os.path.exists(THUMBNAIL_CACHE_DIR): os.makedirs(THUMBNAIL_CACHE_DIR)
                                cached_thumb_path_to_save = os.path.join(THUMBNAIL_CACHE_DIR, f"{video_id}.jpg")
                                pixmap.save(cached_thumb_path_to_save, "JPG", 85)
                            except Exception as e_cache:
                                if self.log_message: self.log_message.emit(self.task_id, f"Lỗi lưu cache thumb: {e_cache}")
            except Exception as e:
                if self.log_message: self.log_message.emit(self.task_id, f"Lỗi tải thumb từ mạng: {e}")

        if thumbnail_pixmap:
            self.thumbnail_ready.emit(self.task_id, thumbnail_pixmap)
        else:
            default_pixmap = QPixmap(120, 90); default_pixmap.fill(QColor(APP_THEME["thumb_bg_alt"]))
            painter = QPainter(default_pixmap); painter.setPen(QColor(APP_THEME["thumb_text_alt"])); painter.drawText(default_pixmap.rect(), Qt.AlignCenter, "No Img"); painter.end()
            self.thumbnail_ready.emit(self.task_id, default_pixmap)

    def stop(self):
        self._is_running = False


class PlaylistFetchWorker(QObject):
    """Worker để lấy danh sách video từ playlist/channel YouTube."""
    finished_fetching = Signal(str, list)  # task_id, list_of_urls
    error_fetching = Signal(str, str)      # task_id, error_message
    log_message = Signal(str, str)         # task_id, message

    def __init__(self, task_id: str, url: str, yt_dlp_path: str, proxy_url: str | None = None):
        super().__init__()
        self.task_id = task_id
        self.url = url
        self.yt_dlp_path = yt_dlp_path
        self.proxy_url = _normalize_proxy_url(proxy_url)  # [ZERO-LEAK-FIX]
        self._is_running = True

    @Slot()
    def run(self):
        if not self._is_running:
            self.error_fetching.emit(self.task_id, "Đã hủy lấy danh sách video.")
            return
        self.log_message.emit(self.task_id, f"Bắt đầu lấy danh sách video từ: {self.url}")
        
        try:
            # Khởi tạo YTdlpInfoFetcher với proxy support
            fetcher = url_handler.YTdlpInfoFetcher(
                yt_dlp_path=self.yt_dlp_path,
                cookies_options=[],  # Có thể mở rộng sau
                proxy_url=self.proxy_url
            )
            
            # Lấy danh sách URL video
            video_urls = fetcher.get_playlist_item_urls(
                playlist_or_channel_url=self.url,
                log_callback=lambda msg: self.log_message.emit(self.task_id, f"[YTdlpInfoFetcher] {msg}")
            )

            if not self._is_running:
                self.error_fetching.emit(self.task_id, "Đã hủy lấy danh sách video.")
                return
            
            if video_urls and len(video_urls) > 0:
                self.log_message.emit(self.task_id, f"Tìm thấy {len(video_urls)} video trong playlist/channel")
                self.finished_fetching.emit(self.task_id, video_urls)
            else:
                error_msg = "Không thể lấy danh sách video. Vui lòng kiểm tra URL và kết nối."
                self.log_message.emit(self.task_id, error_msg)
                self.error_fetching.emit(self.task_id, error_msg)
                
        except Exception as e:
            error_msg = f"Lỗi khi lấy danh sách video: {str(e)}"
            self.log_message.emit(self.task_id, error_msg)
            self.error_fetching.emit(self.task_id, error_msg)

    def stop(self):
        self._is_running = False


class YTDLPInitializer(QObject):
    finished = Signal(str, str)
    def __init__(self, proxy_url: str | None = None):
        super().__init__()
        self.proxy_url = _normalize_proxy_url(proxy_url)  # [ZERO-LEAK-FIX]
        self._is_running = True
    
    @Slot()
    def run(self):
        messages = []
        def status_callback(message):
            if not self._is_running:
                raise InterruptedError("Yêu cầu khởi tạo yt-dlp đã bị hủy.")
            messages.append(message)
        try:
            yt_dlp_path = main_logic.find_or_download_yt_dlp(status_callback=status_callback, proxy_url=self.proxy_url)
        except Exception as exc:
            messages.append(str(exc))
            yt_dlp_path = ""
        self.finished.emit(yt_dlp_path, "\n".join(messages))

    def stop(self):
        self._is_running = False


class YTDLPUpdateWorker(QObject):
    """Worker để chạy cập nhật yt-dlp trong một luồng riêng."""
    finished = Signal(bool, str, str)  # success, new_version, message
    log_signal = Signal(str)
    progress_signal = Signal(int, int) # downloaded_bytes, total_bytes

    def __init__(self, proxy_url: str | None = None):
        super().__init__()
        self.proxy_url = _normalize_proxy_url(proxy_url)  # [ZERO-LEAK-FIX]
        self._is_running = True

    def _progress_adapter(self, downloaded, total):
        if not self._is_running:
            raise InterruptedError("Yêu cầu cập nhật yt-dlp đã bị hủy.")
        self.progress_signal.emit(downloaded, total)

    @Slot()
    def run(self):
        messages = []
        def _local_status_callback(msg):
            if not self._is_running:
                raise InterruptedError("Yêu cầu cập nhật yt-dlp đã bị hủy.")
            messages.append(msg)
            self.log_signal.emit(msg)
        
        self.log_signal.emit("Bắt đầu worker cập nhật yt-dlp...")
        try:
            success = main_logic.update_yt_dlp_executable(
                status_callback=_local_status_callback,
                progress_callback=self._progress_adapter,
                proxy_url=self.proxy_url
            )
        except Exception as exc:
            messages.append(str(exc))
            success = False
        
        new_version = "N/A"
        if success:
            local_yt_dlp_path = os.path.join(main_logic.LOCAL_YT_DLP_SUBDIR, "yt-dlp.exe" if platform.system() == "Windows" else "yt-dlp")
            new_version = main_logic.get_local_yt_dlp_version(local_yt_dlp_path) or "Không rõ"
        
        final_message = "\n".join(messages)
        self.finished.emit(success, new_version, final_message)

    def stop(self):
        self._is_running = False


class UpdateCheckerWorker(QThread):
    """Worker để kiểm tra/tải cập nhật ứng dụng từ GitHub Releases."""

    update_available = Signal(str, object, str)  # version, ReleaseAsset, body
    no_update = Signal(str, bool)  # latest_version, runtime_repaired
    download_progress = Signal(int)  # percent
    download_finished = Signal(str, str)  # package_path, optional runtime_package_path
    status_signal = Signal(str)
    error = Signal(str)

    def __init__(
        self,
        mode: str = "check",
        release_asset: ReleaseAsset | None = None,
        proxy_url: str | None = None,
        parent: QObject | None = None,
    ):
        super().__init__(parent)
        self.mode = mode
        self.release_asset = release_asset
        self.proxy_url = _normalize_proxy_url(proxy_url)
        self.timeout_seconds = 15
        self.stop_requested = False

    def run(self) -> None:
        if self.stop_requested or self.isInterruptionRequested():
            return
        if self.mode == "check":
            self._check_latest_release()
        elif self.mode == "download":
            self._download_update()
        else:
            self.error.emit(f"Chế độ cập nhật không hợp lệ: {self.mode}")

    def _check_latest_release(self) -> None:
        if self.stop_requested or self.isInterruptionRequested():
            return
        api_url = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": USER_AGENT,
        }
        proxies = {"http": self.proxy_url, "https": self.proxy_url} if self.proxy_url else None
        try:
            response = requests.get(
                api_url,
                headers=headers,
                timeout=self.timeout_seconds,
                proxies=proxies,
            )
            response.raise_for_status()
            data = response.json()
        except requests.exceptions.RequestException as exc:
            self.error.emit(f"Lỗi kết nối kiểm tra cập nhật: {exc}")
            return
        except ValueError as exc:
            self.error.emit(f"Dữ liệu cập nhật không hợp lệ: {exc}")
            return

        if self.stop_requested or self.isInterruptionRequested():
            return

        tag_name = data.get("tag_name") or data.get("name")
        if not tag_name:
            self.error.emit("Không tìm thấy tag phiên bản trên GitHub.")
            return

        latest_version = _normalize_version_tag(str(tag_name))
        if _is_version_newer(APP_VERSION, latest_version):
            release_asset = _select_app_update_asset(data)
            if not release_asset:
                self.error.emit("Release không có app-update-v2.pkg với SHA256 hợp lệ.")
                return
            body = data.get("body") or ""
            self.update_available.emit(latest_version, release_asset, body)
        else:
            manager = UpdateManager(
                base_dir=main_logic.SCRIPT_BASE_DIR,
                repo_owner=GITHUB_OWNER,
                repo_name=GITHUB_REPO,
                status_callback=self.status_signal.emit,
                proxy_url=self.proxy_url,
            )
            runtime_repaired = False
            runtime_status = manager.check_runtime()
            if runtime_status.state.value != "healthy":
                self.status_signal.emit("App đã mới nhất; đang sửa Node portable...")
                repair_result = manager.repair_runtime()
                if not repair_result.success:
                    self.error.emit(f"{repair_result.message}: {repair_result.error}")
                    return
                runtime_repaired = True
            self.no_update.emit(latest_version, runtime_repaired)

    def _download_update(self) -> None:
        if self.release_asset is None:
            self.error.emit("Thiếu metadata asset cập nhật.")
            return

        def progress(downloaded: int, total: int) -> None:
            if self.stop_requested or self.isInterruptionRequested():
                raise InterruptedError("Yêu cầu tải cập nhật đã bị hủy.")
            if total > 0:
                self.download_progress.emit(min(int(downloaded * 100 / total), 100))

        manager = UpdateManager(
            base_dir=main_logic.SCRIPT_BASE_DIR,
            repo_owner=GITHUB_OWNER,
            repo_name=GITHUB_REPO,
            progress_callback=progress,
            status_callback=self.status_signal.emit,
            proxy_url=self.proxy_url,
        )
        result = manager.update_app(
            download_url=self.release_asset.url,
            expected_sha256=self.release_asset.sha256,
            expected_size=self.release_asset.size,
        )
        if self.stop_requested or self.isInterruptionRequested():
            return
        if not result.success or not result.artifact_path:
            self.error.emit(f"{result.message}: {result.error}")
            return
        self.download_progress.emit(100)
        self.download_finished.emit(
            result.artifact_path,
            result.runtime_artifact_path or "",
        )

    def stop(self) -> None:
        self.stop_requested = True
        self.requestInterruption()


class IPChangeWorker(QObject):
    """Worker để xử lý đổi IP proxy trong luồng nền."""
    finished = Signal(bool, str)  # success (True/False), message (str)

    def __init__(self, proxy_manager_instance):
        super().__init__()
        self.proxy_manager = proxy_manager_instance
        self._is_running = True

    @Slot()
    def run(self):
        if not self._is_running:
            return
        if not self.proxy_manager:
            self.finished.emit(False, "Lỗi: Proxy Manager không được khởi tạo.")
            return

        try:
            old_ip = self.proxy_manager.check_public_ip()
            if not self._is_running:
                return

            # Chạy hàm async trong một event loop mới
            change_result = asyncio.run(self.proxy_manager.change_ip_with_cooldown())
            if not change_result:
                current_ip = old_ip or "Không rõ"
                self.finished.emit(False, f"Đổi IP thất bại hoặc bị chặn. IP hiện tại: {current_ip}")
                return

            for _ in range(30):
                if not self._is_running:
                    return
                time.sleep(0.1)  # Chờ cho IP mới được áp dụng
            new_ip = self.proxy_manager.check_public_ip()

            def _fmt(ip_val):
                return ip_val if ip_val else "Không rõ"

            if new_ip and new_ip != old_ip:
                message = f"Đổi IP Thành công!\nIP Cũ: {_fmt(old_ip)}\nIP Mới: {new_ip}"
                self.finished.emit(True, message)
            elif new_ip:
                message = f"Yêu cầu gửi thành công nhưng IP chưa đổi (hoặc trùng IP cũ).\nIP hiện tại: {new_ip}"
                self.finished.emit(False, message)
            else:
                message = "Đã gửi yêu cầu đổi IP, nhưng không thể kiểm tra IP mới (Lỗi kết nối mạng/proxy)."
                self.finished.emit(False, message)
        except Exception as e:
            error_message = f"Đổi IP thất bại: {str(e)}"
            self.finished.emit(False, error_message)

    def stop(self):
        self._is_running = False
