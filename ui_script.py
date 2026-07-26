import google_drive_handler # Thêm import này
import gdrive_downloader  # Thêm import này
try:
    from PyQt5.QtWidgets import (
        QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
        QPushButton, QLabel, QTextEdit, QComboBox, QProgressBar, QProgressDialog,
        QFileDialog, QMessageBox, QScrollArea, QFrame, QStyle,
        QTableView, QStyledItemDelegate, QSizePolicy, QCheckBox,
        QToolButton, QMenu, QToolBar, QStyleOptionViewItem, QGridLayout,
        QStyleOptionProgressBar, QInputDialog, QHeaderView, QAbstractItemView, QStyleOptionButton,
        QAction, QSpacerItem #Thêm QSpacerItem nếu chưa có
    )
    from PyQt5.QtCore import (
        Qt, QThread, pyqtSignal as Signal, QObject, pyqtSlot as Slot,
        QTimer, QSize, QRect, QPoint,
        QAbstractTableModel, QModelIndex, QSortFilterProxyModel, QLockFile, QDir
    )
    from PyQt5.QtGui import (
        QIcon, QPixmap, QPainter, QColor, QFont, QPen, QBrush,
        QStandardItemModel, QStandardItem, QFontMetrics
    )
    from PyQt5.QtWidgets import QDialog, QFormLayout, QSpinBox, QLineEdit, QDialogButtonBox, QGroupBox, QTabWidget
    PYQT5_AVAILABLE = True
except ImportError as e_pyqt:
    PYQT5_AVAILABLE = False
    missing_module = str(e_pyqt).split("'")[-2] if "'" in str(e_pyqt) else "PyQt5"
    error_message_cli = (
        f"LỖI NGHIÊM TRỌNG: Không tìm thấy thư viện {missing_module} (PyQt5).\n"
        f"Đây là thư viện cần thiết để chạy giao diện người dùng của ứng dụng.\n"
        f"Vui lòng cài đặt PyQt5 bằng lệnh: pip install PyQt5\n"
        f"Hoặc đảm bảo môi trường Python của bạn có chứa thư viện này.\n"
        f"Chi tiết lỗi: {e_pyqt}"
    )
    print(error_message_cli)
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("Lỗi Thiếu Thư Viện", error_message_cli.replace("\n", "\n\n"))
        root.destroy()
    except ImportError:
        pass
    import sys
    sys.exit(f"Lỗi: {missing_module} chưa được cài đặt.")
try:
    import url_handler
except ImportError:
    print("LỖI: Không thể import url_handler.py. Đảm bảo file này ở cùng thư mục.")
    class UrlHandlerMock:
        URL_TYPE_VIDEO = "video"
        URL_TYPE_PLAYLIST = "playlist"
        URL_TYPE_CHANNEL = "channel"
        URL_TYPE_UNKNOWN = "unknown"
        def get_url_type_and_id(self, url_string):
            if "playlist?list=" in url_string: return self.URL_TYPE_PLAYLIST, "mock_playlist_id", url_string
            if "/channel/" in url_string or "/user/" in url_string or "/c/" in url_string or "/@" in url_string:
                return self.URL_TYPE_CHANNEL, "mock_channel_id", url_string
            if "youtu" in url_string: return self.URL_TYPE_VIDEO, "mock_video_id", url_string
            return self.URL_TYPE_UNKNOWN, None, url_string
        class YTdlpInfoFetcher: # Mock class
            def __init__(self, yt_dlp_path): self.yt_dlp_path = yt_dlp_path
            def get_playlist_item_urls(self, url, log_callback=print):
                log_callback(f"UrlHandlerMock: get_playlist_item_urls được gọi cho {url}, trả về URL gốc.")
                return [url] # Trả về URL gốc như fallback
    url_handler = UrlHandlerMock()
import json
import base64
import shutil
import tempfile
import string
import sys # Đã import ở trên nhưng để đây cho rõ ràng
import os
import platform
import subprocess
import re
import asyncio
import signal
import urllib.request
import urllib.parse  # [ZERO-LEAK-FIX] encode proxy credentials safely
import json as _json_for_proxy
from pathlib import Path as _Path_for_proxy
import time
import threading
import requests
from datetime import datetime
from proxy_manager_v3 import ProxyManager
try:
    from distutils.version import LooseVersion as _LooseVersion
except ImportError:
    _LooseVersion = None

APP_THEME = {
    # --- Main Colors ---
    "app_bg": "#ECEFF1",
    "text_main": "#333333",
    "text_white": "#FFFFFF",

    # --- Toolbar (Trùng màu Selection) ---
    "toolbar_bg": "#78909C",
    "toolbar_border": "#546E7A",
    "toolbar_btn_hover": "#90A4AE",
    "toolbar_btn_pressed": "#546E7A",

    # --- Table View ---
    "table_bg": "#FFFFFF",
    "table_alt_bg": "#F5F5F5",
    "table_grid": "#E0E0E0",
    "table_header_bg": "#CFD8DC",
    "table_header_border": "#B0BEC5",
    "table_selection_bg": "#78909C",
    "table_selection_text": "#FFFFFF",

    # --- Status Colors (Cho Delegate) ---
    "status_success": "#2e7d32",
    "status_neutral": "#424242",
    "status_error": "#D32F2F",

    # --- Thumbnail Placeholder ---
    "thumb_bg": "#EEEEEE",
    "thumb_text": "#AAAAAA",
    "thumb_bg_alt": "#E0E0E0",
    "thumb_text_alt": "#888888",

    # --- Drive Placeholder ---
    "drive_thumb_bg": "#C5E1A5",
    "drive_thumb_text": "#33691E",

    # --- Progress Bar ---
    "progress_chunk": "#4CAF50",
    "progress_bg": "#ECEFF1",
    "progress_border": "#B0BEC5",

    # --- Menu ---
    "menu_bg": "#FFFFFF",
    "menu_border": "#CCCCCC",
    "menu_item_hover": "#2196F3"
}

# --- Import các module cục bộ ---
# (Giữ nguyên try-except cho main_logic và video_verifier như hiện tại,
# vì chúng là module của bạn, không phải thư viện bên ngoài cần cài qua pip)
try:
    import main_logic
    import video_verifier
except ImportError as e_local_module:
    print(f"LỖI: Không thể import module cục bộ cần thiết: {e_local_module}")
    # Tạo mock tối thiểu để một số phần UI có thể load mà không bị crash ngay lập tức
    # (nếu bạn muốn UI cố gắng hiển thị một thông báo lỗi thay vì crash hoàn toàn)
    class MainLogicMock:
        def get_script_directory(self): return os.getcwd()
        def load_settings_from_file(self, path): return {}
        def save_settings_to_file(self, data, path): pass
        def find_or_download_yt_dlp(self, status_callback, progress_callback_for_downloader=None):
            status_callback("Lỗi: main_logic không khả dụng.")
            return None
    main_logic = MainLogicMock()

    class VideoVerifierMock:
        FFPROBE_CMD_TO_USE = None
        def initialize_ffmpeg_paths(self): return None, None
        class VerificationResult:
            def __init__(self): self.success = False; self.file_readable = False; self.error_message = "video_verifier không khả dụng."
        def verify_video_file(self, file_path): return self.VerificationResult()
    video_verifier = VideoVerifierMock()


SCRIPT_BASE_DIR_UI = main_logic.get_script_directory() # Giả sử main_logic đã được import
DATA_DIR_NAME = "data" # Đã có từ lần trước


# --- THAY ĐỔI ĐƯỜNG DẪN FILE CÀI ĐẶT UI ---
GUI_SETTINGS_FILE_NAME = "downloader_settings_qt.json"
GUI_SETTINGS_FILE_PATH = os.path.join(SCRIPT_BASE_DIR_UI, DATA_DIR_NAME, GUI_SETTINGS_FILE_NAME)
DRIVE_ADD_ICON_PATH = os.path.join(SCRIPT_BASE_DIR_UI, DATA_DIR_NAME, "icons", "google-drive-add.svg")
# --- KẾT THÚC THAY ĐỔI ---

HISTORY_FILE_NAME = "download_history.json"
HISTORY_FILE_PATH = os.path.join(SCRIPT_BASE_DIR_UI, DATA_DIR_NAME, HISTORY_FILE_NAME)
THUMBNAIL_CACHE_DIR = os.path.join(SCRIPT_BASE_DIR_UI, DATA_DIR_NAME, "thumbnails") # Tùy chọn: cho cache thumbnail
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0"  # [ZERO-LEAK-FIX]
APP_VERSION = "1.0.15"
GITHUB_OWNER = "davidtuyen"
GITHUB_REPO = "DC_video_youtube"
APP_MAIN_EXE_NAME = "YouTube Downloader Pro.exe"


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
    if _LooseVersion is not None:
        return _LooseVersion(latest) > _LooseVersion(current)
    return _simple_version_tuple(latest) > _simple_version_tuple(current)


# --- Table constants & delegates (tách ra table_model.py) ---
from table_model import (
    COL_CHECKBOX, COL_THUMBNAIL, COL_TITLE, COL_DURATION,
    COL_PROXY_STATUS, COL_RESOLUTION, COL_STATUS_TEXT,
    COL_VERIFICATION_STATUS, COL_PROGRESS, COL_SPEED_ETA,
    COL_URL, COL_TASK_ID, COL_QUALITY_REQUESTED, COL_FILE_PATH,
    COL_ERROR_DETAILS, COL_TIMESTAMP, COL_ENTITY_ID,
    COL_EXPECTED_DURATION, TOTAL_COLUMNS,
    ProgressBarDelegate, DownloadItemDelegate,
    init_table_config,
)
init_table_config(theme=APP_THEME)



# --- Workers (tách ra workers.py) ---
from workers import (
    DriveDownloadWorker, DriveFolderItemFetcher, GoogleDriveAuthWorker,
    DownloadWorker, VerificationWorker, ThumbnailFetcher,
    PlaylistFetchWorker, YTDLPInitializer, YTDLPUpdateWorker,
    UpdateCheckerWorker, IPChangeWorker,
    init_worker_config,
)
from thread_lifecycle import ManagedThreadRegistry
init_worker_config(
    theme=APP_THEME,
    thumb_cache_dir=THUMBNAIL_CACHE_DIR,
    user_agent=USER_AGENT,
    app_version=APP_VERSION,
    github_owner=GITHUB_OWNER,
    github_repo=GITHUB_REPO,
)



# --- Settings Dialog (tách ra settings_dialog.py) ---
from settings_dialog import SettingsDialog, init_settings_config
init_settings_config(
    theme=APP_THEME,
    app_version=APP_VERSION,
    script_base_dir=SCRIPT_BASE_DIR_UI,
    data_dir_name=DATA_DIR_NAME,
)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self._thread_registry = ManagedThreadRegistry(self)
        self._shutdown_in_progress = False
        self._shutdown_state_saved = False
        self._allow_final_close = False
        self._shutdown_poll_timer = QTimer(self)
        self._shutdown_poll_timer.setSingleShot(True)
        self._shutdown_poll_timer.timeout.connect(self._finish_deferred_close)
        self.setWindowTitle("YouTube Downloader Pro")
        self.setGeometry(50, 50, 1100, 700)

        # THÊM CÁC DÒNG NÀY ĐỂ KHỞI TẠO THUỘC TÍNH
        self.yt_dlp_version = "Chưa rõ"
        self.yt_dlp_update_thread = None
        self.yt_dlp_update_worker = None
        self.app_update_check_worker = None
        self.app_update_download_worker = None
        self.app_update_progress_dialog = None
        self.app_update_manual_request = False
        self.settings_dialog_instance = None # Để tham chiếu đến dialog đang mở
        # IP Change thread attributes
        self.ip_change_thread = None
        self.ip_change_worker = None
        self.ip_change_progress_msgbox = None
        # KẾT THÚC KHỐI CẦN THÊM

        icon_file_name = "video-dowload-dc-team.ico"
        icon_path = os.path.join(SCRIPT_BASE_DIR_UI, DATA_DIR_NAME, icon_file_name)

        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))
        else:
            self.setWindowIcon(self.style().standardIcon(QStyle.SP_DriveDVDIcon))
            print(f"CẢNH BÁO: Không tìm thấy file icon tại: {icon_path}. Sử dụng icon mặc định.")

        self.settings = main_logic.load_settings_from_file(GUI_SETTINGS_FILE_PATH)
        self.current_download_dir = self.settings.get("last_output_directory", SCRIPT_BASE_DIR_UI)

        self.yt_dlp_path = None
        self.ffprobe_path = None

        if video_verifier:
            self.ffprobe_path, _ = video_verifier.initialize_ffmpeg_paths()
            if not self.ffprobe_path:
                print("CẢNH BÁO (UI): ffprobe không tìm thấy. Xác minh video sẽ không hoạt động.")

        self.download_tasks_model = QStandardItemModel(0, TOTAL_COLUMNS, self)
        self.download_tasks_model.setHorizontalHeaderLabels([
            "", "Thumb", "Video Title", "Thời lượng", "Kết nối", "Độ phân giải", "Trạng thái Tải", "Xác minh",
            "Tiến trình", "Tốc độ/ETA",
            "URL", "Task ID", "Quality", "File Path", "Lỗi", "Timestamp", "Entity ID", "Expected Duration"  # [UI-UPDATE]
        ])
        self.sort_filter_proxy_model = QSortFilterProxyModel(self)
        self.sort_filter_proxy_model.setSourceModel(self.download_tasks_model)
        self.sort_filter_proxy_model.setFilterKeyColumn(COL_TITLE)

        self.active_threads = {}
        self.active_verification_threads = {}
        self.active_thumbnail_fetchers = {}
        self.integrity_retry_counts = {}  # Đếm số lần tự động tải lại theo URL
        self.max_concurrent_downloads = self.settings.get("max_concurrent_downloads", 2)
        self.next_task_id_counter = int(time.time())

        self.drive_service = None
        self.drive_auth_pending = False
        self.drive_auth_thread = None # Thêm để quản lý luồng auth
        self.drive_auth_worker = None # Thêm để quản lý worker auth
        self.pending_drive_action_callback = None # Lưu trữ callback sau khi auth thành công

        self._ensure_data_directory()
        self._init_ui()  # Gọi _init_ui() ở đây để toolbar được tạo

        # Các dòng này sẽ được di chuyển vào _init_ui() hoặc sau khi toolbar được tạo trong _init_ui()
        # self.add_drive_link_action = QAction(QIcon.fromTheme("folder-remote", self.style().standardIcon(QStyle.SP_DriveNetIcon)),
        #                                      "Thêm Link Google Drive", self)
        # self.add_drive_link_action.triggered.connect(self._handle_add_drive_link_dialog)
        # toolbar.addAction(self.add_drive_link_action) # Lỗi ở đây nếu toolbar chưa được định nghĩa

        self._load_initial_settings_to_ui()
        self._load_download_history()
        self._apply_qss()
        self.proxy_manager = None
        self._initialize_proxy_manager()
        self._initialize_yt_dlp_non_blocking()

    def _track_thread(
        self,
        thread,
        worker=None,
        *,
        completion_signals=(),
        stop_callback=None,
        cleanup_callback=None,
    ):
        return self._thread_registry.track(
            thread,
            worker,
            completion_signals=completion_signals,
            stop_callback=stop_callback,
            cleanup_callback=cleanup_callback,
        )

    def _clear_managed_thread_refs(self, thread_attr, worker_attr, thread):
        if getattr(self, thread_attr, None) is thread:
            setattr(self, thread_attr, None)
            if worker_attr:
                setattr(self, worker_attr, None)

    def _can_start_update(self, manual: bool, requested: str | None = None) -> bool:
        active_download = any(
            info.get("status") in {"queued", "starting", "downloading"}
            for info in self.active_threads.values()
        )
        yt_update_running = bool(
            self.yt_dlp_update_thread and self.yt_dlp_update_thread.isRunning()
        )
        app_update_running = bool(
            (self.app_update_check_worker and self.app_update_check_worker.isRunning())
            or (self.app_update_download_worker and self.app_update_download_worker.isRunning())
        )
        if active_download or (requested != "yt-dlp" and yt_update_running) or (
            requested != "app" and app_update_running
        ):
            message = "Đang có tác vụ tải hoặc cập nhật khác. Vui lòng chờ tác vụ hoàn tất."
            self.log_to_gui(message)
            if manual:
                QMessageBox.information(self, "Đang bận", message)
            return False
        return True

    def _set_update_controls_enabled(self, enabled: bool) -> None:
        if hasattr(self, "app_update_action"):
            self.app_update_action.setEnabled(enabled)
        if self.settings_dialog_instance:
            self.settings_dialog_instance.set_update_button_enabled(enabled)
            if hasattr(self.settings_dialog_instance, "set_app_update_button_enabled"):
                self.settings_dialog_instance.set_app_update_button_enabled(enabled)

    def _adopt_running_child_threads(self):
        for thread in self.findChildren(QThread):
            if thread.isRunning() and not self._thread_registry.is_tracked(thread):
                self._track_thread(thread)
                if self._shutdown_in_progress:
                    thread.requestInterruption()
                    thread.quit()

    def _request_thread_shutdown(self):
        self._adopt_running_child_threads()
        self._thread_registry.request_shutdown()

    def _initialize_proxy_manager(self):
        try:
            # Support new proxy_mode setting with backward compat
            proxy_mode = self.settings.get("proxy_mode", "")
            if not proxy_mode:
                proxy_mode = "m2proxy" if self.settings.get("use_proxy", False) else "none"
            
            if proxy_mode == "warp":
                self.proxy_manager = None
                warp_port = self.settings.get("warp_port", 40000)
                self.log_to_gui(f"Proxy: WARP (Cloudflare 1.1.1.1) đang bật. SOCKS5 tại 127.0.0.1:{warp_port}")
                return
            
            if proxy_mode != "m2proxy":
                self.proxy_manager = None
                self.log_to_gui("Proxy: Đang tắt.")
                return
            # Use base dir resolved by main_logic to support both source and frozen builds
            config_path = _Path_for_proxy(SCRIPT_BASE_DIR_UI) / DATA_DIR_NAME / "proxy_settings.json"
            with open(config_path, 'r', encoding='utf-8') as f:
                settings_obj = _json_for_proxy.load(f)
            self.proxy_manager = ProxyManager.from_config(settings_obj)
            self.log_to_gui("Proxy: Khởi tạo thành công từ proxy_settings.json.")
            
            # --- BẮT ĐẦU SỬA LỖI THREAD SAFETY ---
            self.log_to_gui("Proxy: Bắt đầu xác thực Username/Password với M2Proxy...")
            
            self.auth_proxy_thread = QThread(self)
            
            # Định nghĩa Worker mới có Signal log riêng
            class ProxyAuthWorker(QObject):
                finished = Signal(bool, str) # success, message
                log_signal = Signal(str)     # [FIX] Signal để gửi log ra UI an toàn

                def __init__(self, manager_instance):
                    super().__init__()
                    self.manager = manager_instance
                    self.messages = []
                    self._is_running = True

                @Slot()
                def run(self):
                    # Callback nội bộ chỉ emit signal, không gọi hàm UI trực tiếp
                    def _local_log(msg):
                        if not self._is_running:
                            raise InterruptedError("Đã hủy xác thực proxy.")
                        self.messages.append(msg)
                        self.log_signal.emit(msg) 

                    try:
                        success = self.manager.authorize_user_pass(log_callback=_local_log)
                    except Exception as exc:
                        self.messages.append(str(exc))
                        success = False
                    self.finished.emit(success, "\n".join(self.messages))

                def stop(self):
                    self._is_running = False
            
            # Khởi tạo worker không truyền log_callback nữa
            self.proxy_auth_worker_obj = ProxyAuthWorker(self.proxy_manager)
            self.proxy_auth_worker_obj.moveToThread(self.auth_proxy_thread)
            
            # Kết nối tín hiệu
            self.proxy_auth_worker_obj.log_signal.connect(self.log_to_gui) # [FIX] Kết nối signal vào slot UI
            self.proxy_auth_worker_obj.finished.connect(self._on_proxy_auth_finished)
            self.auth_proxy_thread.started.connect(self.proxy_auth_worker_obj.run)
            self._track_thread(
                self.auth_proxy_thread,
                self.proxy_auth_worker_obj,
                completion_signals=(self.proxy_auth_worker_obj.finished,),
                cleanup_callback=lambda thread=self.auth_proxy_thread: self._clear_managed_thread_refs(
                    "auth_proxy_thread", "proxy_auth_worker_obj", thread
                ),
            )
            
            self.auth_proxy_thread.start()
            # --- KẾT THÚC SỬA LỖI ---
            
        except FileNotFoundError:
            self.proxy_manager = None
            self.log_to_gui("Lỗi Proxy: Không tìm thấy file proxy_settings.json.")
            QMessageBox.warning(self, "Thiếu cấu hình Proxy", "Không tìm thấy file proxy_settings.json trong thư mục data.\nProxy sẽ bị tắt.")
        except (ValueError, KeyError) as e:
            self.proxy_manager = None
            self.log_to_gui(f"Lỗi Proxy: File proxy_settings.json sai cấu trúc: {e}")
            QMessageBox.warning(self, "Cấu trúc Proxy không hợp lệ", "File proxy_settings.json sai cấu trúc. Proxy sẽ bị tắt.")

        if not self.ffprobe_path:
             self.log_to_gui("CẢNH BÁO: ffprobe không tìm thấy. Tính năng xác minh video sẽ không hoạt động.")
        if hasattr(self, 'item_count_label') and self.item_count_label: # Kiểm tra item_count_label tồn tại
            self._update_item_count_and_controls()
        else:
            print("CẢNH BÁO: item_count_label chưa được khởi tạo khi __init__ hoàn tất.")
    
    
    @Slot(bool, str)
    def _on_proxy_auth_finished(self, success, message_log):
        """Xử lý khi quá trình xác thực proxy bằng USER/PASS hoàn tất."""
        self.log_to_gui(f"--- Log Xác Thực Proxy ---\n{message_log}\n--- Kết thúc Log ---")
        if self._shutdown_in_progress:
            return
        if success:
            self.log_to_gui("Proxy: Xác thực USER/PASS thành công.")
        else:
            self.log_to_gui("Lỗi Proxy: Xác thực USER/PASS thất bại.")
            QMessageBox.warning(self, 
                                "Lỗi Xác Thực Proxy", 
                                "Không thể cấu hình USER/PASS cho proxy.\n"
                                "Các lượt tải qua proxy có thể thất bại.\n"
                                "Vui lòng kiểm tra log và cấu hình proxy_settings.json.")
        
    def _handle_add_drive_link_dialog(self):
        text, ok = QInputDialog.getMultiLineText(self, "Thêm Link Google Drive",
                                                 "Dán một hoặc nhiều link Google Drive (mỗi link một dòng):",
                                                 self.settings.get("last_drive_links_input", ""))
        if ok and text.strip():
            self.settings["last_drive_links_input"] = text # Lưu lại input cho lần sau
            main_logic.save_settings_to_file(self.settings, GUI_SETTINGS_FILE_PATH)
            self.log_to_gui(f"Đã nhận link Google Drive từ dialog:\n{text}")
            self._prepare_downloads_from_text(text, default_type="drive")

    def _ensure_data_directory(self): 
        data_dir = os.path.join(SCRIPT_BASE_DIR_UI, DATA_DIR_NAME)
        if not os.path.exists(data_dir):
            try:
                os.makedirs(data_dir)
                self.log_to_gui(f"Đã tạo thư mục dữ liệu: {data_dir}")
            except OSError as e:
                self.log_to_gui(f"Lỗi tạo thư mục dữ liệu '{data_dir}': {e}")
        
        if not os.path.exists(THUMBNAIL_CACHE_DIR):
            try:
                os.makedirs(THUMBNAIL_CACHE_DIR)
                self.log_to_gui(f"Đã tạo thư mục cache thumbnail: {THUMBNAIL_CACHE_DIR}")
            except OSError as e:
                self.log_to_gui(f"Lỗi tạo thư mục cache thumbnail '{THUMBNAIL_CACHE_DIR}': {e}")


    def _init_ui(self):
        main_widget = QWidget()
        self.main_layout = QVBoxLayout(main_widget)
        self.main_layout.setContentsMargins(0,0,0,0)
        self.main_layout.setSpacing(0)
        self.setCentralWidget(main_widget)

        # --- Toolbar ---
        toolbar = QToolBar("Main Toolbar") # Khởi tạo toolbar ở đây
        toolbar.setMovable(False)
        toolbar.setIconSize(QSize(22,22))
        self.addToolBar(Qt.TopToolBarArea, toolbar)

        self.paste_link_action = QAction(QIcon.fromTheme("edit-paste", self.style().standardIcon(QStyle.SP_ToolBarHorizontalExtensionButton)),
                                         "&Dán Link và Tải", self)
        self.paste_link_action.triggered.connect(self._handle_paste_link_and_download)
        self.paste_link_action.setShortcut("Ctrl+V")
        toolbar.addAction(self.paste_link_action)
        toolbar.addSeparator()

        toolbar.addWidget(QLabel("Chất lượng:"))
        self.quality_main_combo = QComboBox()
        self.quality_options_map = {
            "Tốt nhất (MP4)": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b",
            "1080p (Ưu tiên)": "bv[height=1080][ext=mp4]+ba[ext=m4a]/bv[height=720][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/bv*+ba/b",
            "720p (Ưu tiên)": "bv[height=720][ext=mp4]+ba[ext=m4a]/bv[height=480][ext=mp4]+ba[ext=m4a]/b[height<=720][ext=mp4]/bv*+ba/b",
            "Dọc/Shorts HD": "bv[height>=1080][width<height][ext=mp4]+ba[ext=m4a]/bv[height=1080][ext=mp4]+ba[ext=m4a]/b[height<=1920][ext=mp4]/bv*+ba/b",
            "Audio (M4A)": "bestaudio[ext=m4a]/bestaudio"
        }
        self.quality_main_combo.addItems(self.quality_options_map.keys())
        toolbar.addWidget(self.quality_main_combo)

        self.save_to_button = QToolButton()
        self.save_to_button.clicked.connect(self._select_download_directory)
        self.save_to_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.save_to_button.setIcon(self.style().standardIcon(QStyle.SP_DirIcon))
        toolbar.addWidget(self.save_to_button)

        drive_add_icon = QIcon(DRIVE_ADD_ICON_PATH)
        if drive_add_icon.isNull():
            drive_add_icon = self.style().standardIcon(QStyle.SP_DriveNetIcon)
        self.add_drive_link_action = QAction(drive_add_icon, "Thêm Link Google Drive", self)
        self.add_drive_link_action.setToolTip("Thêm một hoặc nhiều link Google Drive")
        self.add_drive_link_action.triggered.connect(self._handle_add_drive_link_dialog)
        toolbar.addAction(self.add_drive_link_action)

        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        toolbar.addWidget(spacer)

        self.toggle_log_action = QAction(QIcon.fromTheme("view-certificate-server", self.style().standardIcon(QStyle.SP_FileDialogDetailedView)),
                                         "Hiện/Ẩn Log", self)
        self.toggle_log_action.setCheckable(True)
        self.toggle_log_action.setChecked(False)
        self.toggle_log_action.triggered.connect(self._toggle_system_log_visibility)
        toolbar.addAction(self.toggle_log_action)

        # [UI-UPDATE] Nhóm các hành động tải lại/hủy/xóa vào một menu
        self.redownload_selected_action = QAction(QIcon.fromTheme("document-revert", self.style().standardIcon(QStyle.SP_BrowserReload)), "Tải lại mục đã chọn", self)
        self.redownload_selected_action.triggered.connect(self._handle_redownload_selected)

        self.redownload_failed_action = QAction(QIcon.fromTheme("emblem-synchronizing", self.style().standardIcon(QStyle.SP_MessageBoxWarning)), "Tải lại Tất cả Mục lỗi", self)
        self.redownload_failed_action.setToolTip("Tự động tìm và tải lại tất cả các mục có trạng thái bị lỗi hoặc chưa được xác minh.")
        self.redownload_failed_action.triggered.connect(self._handle_redownload_failed_items)

        self.cancel_selected_action = QAction(QIcon.fromTheme("process-stop", self.style().standardIcon(QStyle.SP_DialogCancelButton)), "Hủy mục đã chọn", self)
        self.cancel_selected_action.triggered.connect(self._handle_cancel_selected)

        self.remove_selected_action = QAction(QIcon.fromTheme("edit-delete", self.style().standardIcon(QStyle.SP_DialogCloseButton)), "Xóa mục đã chọn khỏi danh sách", self)
        self.remove_selected_action.triggered.connect(self._handle_remove_selected)

        batch_menu = QMenu(self)
        batch_menu.addAction(self.redownload_selected_action)
        batch_menu.addAction(self.redownload_failed_action)
        batch_menu.addSeparator()
        batch_menu.addAction(self.cancel_selected_action)
        batch_menu.addAction(self.remove_selected_action)

        self.batch_action_button = QToolButton(self)
        self.batch_action_button.setText("Tải lại / Xử lý")
        self.batch_action_button.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.batch_action_button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
        self.batch_action_button.setPopupMode(QToolButton.InstantPopup)  # [UI-UPDATE]
        self.batch_action_button.setMenu(batch_menu)
        toolbar.addWidget(self.batch_action_button)

        clear_history_menu = QMenu(self)
        self.clear_all_history_action = QAction("Xóa Toàn bộ Lịch sử", self)
        self.clear_all_history_action.triggered.connect(self._handle_clear_all_history)
        clear_history_menu.addAction(self.clear_all_history_action)
        self.clear_completed_action = QAction("Xóa Mục Hoàn thành", self)
        self.clear_completed_action.triggered.connect(self._handle_clear_completed_tasks)
        clear_history_menu.addAction(self.clear_completed_action)
        self.clear_failed_action = QAction("Xóa Mục Bị lỗi", self)
        self.clear_failed_action.triggered.connect(self._handle_clear_failed_tasks)
        clear_history_menu.addAction(self.clear_failed_action)
        clear_history_menu.addSeparator()  # [UI-UPDATE]
        self.clear_thumbnails_action = QAction(QIcon.fromTheme("trash-empty", self.style().standardIcon(QStyle.SP_TrashIcon)),
                                               "Dọn dẹp Cache Thumbnail", self)  # [UI-UPDATE]
        self.clear_thumbnails_action.triggered.connect(self._handle_clear_thumbnails)  # [UI-UPDATE]
        clear_history_menu.addAction(self.clear_thumbnails_action)  # [UI-UPDATE]

        self.clear_history_button = QToolButton(self)
        self.clear_history_button.setIcon(QIcon.fromTheme("edit-clear-history", self.style().standardIcon(QStyle.SP_DialogResetButton)))
        self.clear_history_button.setText("Xóa Lịch sử")
        self.clear_history_button.setPopupMode(QToolButton.InstantPopup)  # [UI-UPDATE]
        self.clear_history_button.setMenu(clear_history_menu)
        toolbar.addWidget(self.clear_history_button)

        self.settings_action = QAction(QIcon.fromTheme("preferences-system", self.style().standardIcon(QStyle.SP_FileDialogListView)),
                                        "&Cài đặt", self)
        self.settings_action.setToolTip("Mở hộp thoại cài đặt chương trình")
        self.settings_action.triggered.connect(self._open_settings_dialog)
        toolbar.addAction(self.settings_action)

        # --- Filter Bar ---
        self.filter_bar_widget = QWidget()
        filter_bar_layout = QHBoxLayout(self.filter_bar_widget)
        filter_bar_layout.setContentsMargins(8,5,8,5)
        self.filter_bar_widget.setObjectName("FilterBar")

        # Checkbox Chọn tất cả
        self.select_all_checkbox = QCheckBox("Chọn Tất cả")
        self.select_all_checkbox.stateChanged.connect(self._toggle_select_all)
        filter_bar_layout.addWidget(self.select_all_checkbox)
        filter_bar_layout.addSpacing(15)

        filter_buttons = ["Tất cả", "Video", "Audio", "Đang tải", "Hoàn thành", "Bị lỗi", "Đã xác minh", "Lỗi xác minh", "File đã xóa"]
        self.filter_button_group = {}
        for f_text in filter_buttons:
            btn = QPushButton(f_text)
            btn.setCheckable(True)
            btn.clicked.connect(self.on_filter_button_clicked)
            filter_bar_layout.addWidget(btn)
            self.filter_button_group[f_text.lower().replace(" ","_")] = btn
        if "tất_cả" in self.filter_button_group:
            self.filter_button_group["tất_cả"].setChecked(True)
        filter_bar_layout.addStretch(1)
        self.item_count_label = QLabel("0 mục")
        filter_bar_layout.addWidget(self.item_count_label)
        self.main_layout.addWidget(self.filter_bar_widget)
        
        # --- Downloads Table View ---
        self.downloads_table_view = QTableView()
        self.downloads_table_view.setModel(self.sort_filter_proxy_model)
        self.downloads_table_view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.downloads_table_view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.downloads_table_view.setShowGrid(True)
        self.downloads_table_view.verticalHeader().setVisible(False)
        self.downloads_table_view.setAlternatingRowColors(True)
        self.downloads_table_view.setMouseTracking(True)

        self.item_delegate = DownloadItemDelegate(self)
        self.downloads_table_view.setItemDelegate(self.item_delegate)
        self.downloads_table_view.setItemDelegateForColumn(COL_PROGRESS, ProgressBarDelegate(self))

        header = self.downloads_table_view.horizontalHeader()
        header.setSectionResizeMode(COL_CHECKBOX, QHeaderView.ResizeToContents) # << MỚI
        header.setSectionResizeMode(COL_THUMBNAIL, QHeaderView.Fixed)
        self.downloads_table_view.setColumnWidth(COL_THUMBNAIL, self.item_delegate.thumbnail_target_width + 2 * self.item_delegate.padding + 10)
        header.setSectionResizeMode(COL_TITLE, QHeaderView.Stretch)
        header.setSectionResizeMode(COL_DURATION, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_PROXY_STATUS, QHeaderView.ResizeToContents)  # [UI-UPDATE]
        header.setSectionResizeMode(COL_RESOLUTION, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_PROGRESS, QHeaderView.Interactive)
        self.downloads_table_view.setColumnWidth(COL_PROGRESS, 120)
        
        # [UX-FIX] Thay vì ResizeToContents (gây giật và đôi khi không đủ rộng),
        # hãy dùng Interactive và set độ rộng cố định đủ lớn cho các thông báo dài.
        header.setSectionResizeMode(COL_SPEED_ETA, QHeaderView.Interactive)
        self.downloads_table_view.setColumnWidth(COL_SPEED_ETA, 170) # 170px đủ cho "Đang chuyển đổi..."

        # Tương tự, cột Trạng thái Tải (Status Text) cũng nên cố định để tránh nhảy layout
        header.setSectionResizeMode(COL_STATUS_TEXT, QHeaderView.Interactive)
        self.downloads_table_view.setColumnWidth(COL_STATUS_TEXT, 140) 

        # Cột Xác minh cũng thường có text dài ("Đang tải lại (Lệch TL)...")
        header.setSectionResizeMode(COL_VERIFICATION_STATUS, QHeaderView.Interactive)
        self.downloads_table_view.setColumnWidth(COL_VERIFICATION_STATUS, 150)

        # [UX] Khôi phục độ rộng cột từ cài đặt (nếu có)
        saved_widths = self.settings.get("table_column_widths", {})
        if saved_widths:
            for col_idx_str, width in saved_widths.items():
                try:
                    col_idx = int(col_idx_str)
                    # Chỉ set nếu width hợp lệ (>0)
                    if width > 0:
                        self.downloads_table_view.setColumnWidth(col_idx, width)
                except ValueError:
                    pass

        for col_idx in range(COL_URL, TOTAL_COLUMNS):
            self.downloads_table_view.setColumnHidden(col_idx, True)
        self.downloads_table_view.setColumnHidden(COL_TIMESTAMP, True)

        row_height = self.item_delegate.sizeHint(QStyleOptionViewItem(), QModelIndex()).height()
        self.downloads_table_view.verticalHeader().setDefaultSectionSize(row_height)
        self.downloads_table_view.verticalHeader().setMinimumSectionSize(row_height)
        self.downloads_table_view.setSortingEnabled(True)
        self.sort_filter_proxy_model.setSortRole(Qt.InitialSortOrderRole)
        self.sort_filter_proxy_model.sort(COL_TIMESTAMP, Qt.DescendingOrder)

        self.main_layout.addWidget(self.downloads_table_view, 1)


        self.system_log_widget = QWidget()
        system_log_layout = QVBoxLayout(self.system_log_widget)
        system_log_layout.setContentsMargins(5,0,5,5)

        log_label_container = QHBoxLayout()
        log_label_container.addWidget(QLabel("System Log:"))
        log_label_container.addStretch()

        self.hide_log_button = QToolButton(self)
        self.hide_log_button.setToolTip("Ẩn/Hiện System Log")
        self.hide_log_button.setCheckable(True)
        self.hide_log_button.setChecked(False)
        self.hide_log_button.setText("Hiện")
        self.hide_log_button.clicked.connect(self._toggle_system_log_visibility)
        log_label_container.addWidget(self.hide_log_button)

        system_log_layout.addLayout(log_label_container)

        self.general_log_area = QTextEdit()
        self.general_log_area.setReadOnly(True)
        self.general_log_area.setFixedHeight(100)
        system_log_layout.addWidget(self.general_log_area)

        self.main_layout.addWidget(self.system_log_widget)
        self.system_log_widget.setVisible(False)

        self.downloads_table_view.setContextMenuPolicy(Qt.CustomContextMenu)
        self.downloads_table_view.customContextMenuRequested.connect(self._show_table_context_menu)
        self.downloads_table_view.doubleClicked.connect(self._handle_row_double_clicked)

    @Slot(QModelIndex)
    def _handle_row_double_clicked(self, proxy_index):
        """Bật/tắt trạng thái checkbox của hàng được nháy đúp chuột."""
        if not proxy_index.isValid():
            return

        # Ánh xạ chỉ số từ proxy model (view) về source model (dữ liệu)
        source_index = self.sort_filter_proxy_model.mapToSource(proxy_index)
        source_row = source_index.row()

        # Lấy mục checkbox tại hàng tương ứng
        checkbox_item = self.download_tasks_model.item(source_row, COL_CHECKBOX)

        if checkbox_item:
            # Lấy trạng thái hiện tại và đảo ngược nó
            current_state = checkbox_item.checkState()
            new_state = Qt.Unchecked if current_state == Qt.Checked else Qt.Checked
            checkbox_item.setCheckState(new_state)

    @Slot()
    def _open_settings_dialog(self):
        self.settings_dialog_instance = SettingsDialog(self.settings, self)
        self.settings_dialog_instance.set_yt_dlp_version(self.yt_dlp_version) # Cập nhật phiên bản
        self.settings_dialog_instance.set_yt_dlp_path_display(self.yt_dlp_path or "Chưa xác định") # Cập nhật đường dẫn
        self.settings_dialog_instance.manual_update_requested.connect(
            lambda: self._start_yt_dlp_update(manual=True) # manual=True cho thủ công
        )
        self.settings_dialog_instance.manual_app_update_requested.connect(
            lambda: self.check_for_app_updates(manual=True)
        )
        self.settings_dialog_instance.manual_change_ip_requested.connect(self._handle_manual_ip_change)

        if self.settings_dialog_instance.exec_() == QDialog.Accepted:
            # ... (giữ nguyên logic xử lý cài đặt) ...
            new_settings_from_dialog = self.settings_dialog_instance.get_settings()
                
            if self.settings.get("max_concurrent_downloads") != new_settings_from_dialog.get("max_concurrent_downloads"):
                self.max_concurrent_downloads = new_settings_from_dialog.get("max_concurrent_downloads", 2)
                self.log_to_gui(f"Số lượt tải đồng thời tối đa đã được đặt thành: {self.max_concurrent_downloads}")
                self._process_download_queue() 

            if self.settings.get("save_thumbnail_with_video") != new_settings_from_dialog.get("save_thumbnail_with_video"):
                save_thumb_new = new_settings_from_dialog.get("save_thumbnail_with_video", False)
                self.log_to_gui(f"Tùy chọn lưu thumbnail chung với video: {'Bật' if save_thumb_new else 'Tắt'}")

            if self.settings.get("use_aria2c") != new_settings_from_dialog.get("use_aria2c"):
                use_aria2c_new = new_settings_from_dialog.get("use_aria2c", False)
                self.log_to_gui(f"Tùy chọn sử dụng aria2c: {'Bật' if use_aria2c_new else 'Tắt'}")
                if use_aria2c_new:
                    self._check_aria2c_availability()

            if self.settings.get("aria2c_args") != new_settings_from_dialog.get("aria2c_args"):
                self.log_to_gui(f"Đã cập nhật đối số aria2c: {new_settings_from_dialog.get('aria2c_args')}")

            if self.settings.get("concurrent_fragments") != new_settings_from_dialog.get("concurrent_fragments"):
                self.log_to_gui(f"Số mảnh tải đồng thời (yt-dlp) được đặt thành: {new_settings_from_dialog.get('concurrent_fragments')}")

            # Kiểm tra thay đổi use_proxy
            prev_use_proxy = self.settings.get("use_proxy", False)
            new_use_proxy = new_settings_from_dialog.get("use_proxy", False)
            self.settings.update(new_settings_from_dialog)
            main_logic.save_settings_to_file(self.settings, GUI_SETTINGS_FILE_PATH)
            self.log_to_gui("Đã lưu cài đặt từ hộp thoại.")
            if prev_use_proxy != new_use_proxy:
                self._initialize_proxy_manager()
                # Optionally, you could restart pending queue to apply new proxy
        else:
            self.log_to_gui("Hủy bỏ thay đổi cài đặt.")
        
        self.settings_dialog_instance = None # Xóa tham chiếu sau khi dialog đóng

# Thêm hai hàm mới này vào trong lớp MainWindow
    def _start_yt_dlp_update(self, manual=False):
        """Bắt đầu quá trình cập nhật yt-dlp."""
        if self._shutdown_in_progress:
            return
        if not self._can_start_update(manual, requested="yt-dlp"):
            return
        if self.yt_dlp_update_thread and self.yt_dlp_update_thread.isRunning():
            self.log_to_gui("Quá trình cập nhật yt-dlp đã đang chạy.")
            if manual:
                QMessageBox.information(self, "Đang cập nhật", "Quá trình cập nhật đã đang chạy trong nền.")
            return

        # Only use M2Proxy for yt-dlp binary downloads (WARP not used here)
        proxy_mode = self.settings.get("proxy_mode", "")
        if not proxy_mode:
            proxy_mode = "m2proxy" if self.settings.get("use_proxy", False) else "none"
        proxy_url_for_update = _normalize_proxy_url(self.proxy_manager.get_proxy_url()) if (proxy_mode == "m2proxy" and self.proxy_manager) else None
        if proxy_mode == "m2proxy" and not proxy_url_for_update:
            self.log_to_gui("Proxy đang bật nhưng thiếu cấu hình, không thể cập nhật yt-dlp để tránh lộ IP.")
            if manual:
                QMessageBox.critical(self, "Proxy chưa sẵn sàng", "Proxy đang bật nhưng thiếu cấu hình hợp lệ. Dừng cập nhật yt-dlp để tránh lộ IP.")
            return

        if manual and self.settings_dialog_instance:
            self._set_update_controls_enabled(False)
            self.settings_dialog_instance.show_update_progress(True)

        self.yt_dlp_update_thread = QThread(self)
        proxied_url_for_worker = proxy_url_for_update if proxy_mode == "m2proxy" else None
        self.yt_dlp_update_worker = YTDLPUpdateWorker(proxy_url=proxied_url_for_worker)
        self.yt_dlp_update_worker.moveToThread(self.yt_dlp_update_thread)

        # Kết nối tín hiệu
        self.yt_dlp_update_worker.log_signal.connect(self.log_to_gui)
        # Thêm lambda để phân biệt giữa manual và auto
        self.yt_dlp_update_worker.finished.connect(
            lambda success, new_ver, msg: self._on_yt_dlp_update_finished(success, new_ver, msg, manual)
        )
        if manual and self.settings_dialog_instance:
            self.yt_dlp_update_worker.progress_signal.connect(self.settings_dialog_instance.update_progress_value)


        self.yt_dlp_update_thread.started.connect(self.yt_dlp_update_worker.run)
        self._track_thread(
            self.yt_dlp_update_thread,
            self.yt_dlp_update_worker,
            completion_signals=(self.yt_dlp_update_worker.finished,),
            cleanup_callback=lambda thread=self.yt_dlp_update_thread: self._clear_managed_thread_refs(
                "yt_dlp_update_thread", "yt_dlp_update_worker", thread
            ),
        )
        self.yt_dlp_update_thread.start()

    @Slot(bool, str, str, bool)
    def _on_yt_dlp_update_finished(self, success, new_version, message, is_manual_request):
        """Xử lý khi quá trình cập nhật hoàn tất."""
        self.log_to_gui(f"--- Log cập nhật yt-dlp (Yêu cầu thủ công: {is_manual_request}) ---\n{message}\n--- Kết thúc log ---")
        if self._shutdown_in_progress:
            return
        
        if success:
            old_version = self.yt_dlp_version
            self.yt_dlp_version = new_version
            
            # CẬP NHẬT LẠI ĐƯỜNG DẪN TRONG UI NGAY LẬP TỨC
            self.log_to_gui("Đang làm mới đường dẫn yt-dlp sau khi cập nhật...")
            proxy_url_for_refresh = _normalize_proxy_url(self.proxy_manager.get_proxy_url()) if self.proxy_manager else None  # [ZERO-LEAK-FIX]
            if not self.settings.get("use_proxy", False):
                proxy_url_for_refresh = None
            refreshed_path = main_logic.find_or_download_yt_dlp(status_callback=self.log_to_gui, proxy_url=proxy_url_for_refresh)
            if refreshed_path:
                self.yt_dlp_path = refreshed_path
                self.log_to_gui(f"Đường dẫn yt-dlp đã được cập nhật thành: {self.yt_dlp_path}")
            else:
                self.log_to_gui("CẢNH BÁO: Không thể làm mới đường dẫn yt-dlp sau khi cập nhật.")

            if is_manual_request:
                if old_version == new_version:
                    QMessageBox.information(self, "Đã cập nhật", f"Bạn đang ở phiên bản mới nhất của yt-dlp: {new_version}")
                else:
                    QMessageBox.information(self, "Cập nhật thành công", f"yt-dlp đã được cập nhật thành công.\nPhiên bản cũ: {old_version}\nPhiên bản mới: {new_version}")
        elif is_manual_request: # Chỉ hiển thị lỗi nếu người dùng yêu cầu thủ công
            QMessageBox.warning(self, "Cập nhật thất bại", f"Không thể cập nhật yt-dlp. Vui lòng xem log để biết chi tiết.\n\n{message.splitlines()[-1]}")

        # Cập nhật lại giao diện SettingsDialog nếu nó đang mở
        if self.settings_dialog_instance:
            self.settings_dialog_instance.set_yt_dlp_version(self.yt_dlp_version)
            self.settings_dialog_instance.set_yt_dlp_path_display(self.yt_dlp_path) # Cập nhật cả đường dẫn
            self._set_update_controls_enabled(True)

    def check_for_app_updates(self, manual: bool = True) -> None:
        """Kiểm tra cập nhật ứng dụng từ GitHub Releases."""
        if self._shutdown_in_progress:
            return
        if not self._can_start_update(manual, requested="app"):
            return
        if (self.app_update_check_worker and self.app_update_check_worker.isRunning()) or (
            self.app_update_download_worker and self.app_update_download_worker.isRunning()
        ):
            if manual:
                QMessageBox.information(self, "Đang xử lý", "Đang kiểm tra/tải cập nhật ứng dụng. Vui lòng chờ...")
            return

        self.app_update_manual_request = manual
        self.log_to_gui("Đang kiểm tra cập nhật ứng dụng...")
        if hasattr(self, "app_update_action"):
            self.app_update_action.setEnabled(False)

        proxy_mode = self.settings.get("proxy_mode", "")
        if not proxy_mode:
            proxy_mode = "m2proxy" if self.settings.get("use_proxy", False) else "none"
        self.app_update_proxy_url = (
            _normalize_proxy_url(self.proxy_manager.get_proxy_url())
            if proxy_mode == "m2proxy" and self.proxy_manager
            else None
        )
        if proxy_mode == "m2proxy" and not self.app_update_proxy_url:
            message = "Proxy đang bật nhưng thiếu cấu hình hợp lệ; đã dừng kiểm tra cập nhật ứng dụng."
            self.log_to_gui(message)
            if hasattr(self, "app_update_action"):
                self.app_update_action.setEnabled(True)
            if manual:
                QMessageBox.critical(self, "Proxy chưa sẵn sàng", message)
            return

        self.app_update_check_worker = UpdateCheckerWorker(
            mode="check",
            proxy_url=self.app_update_proxy_url,
            parent=self,
        )
        self.app_update_check_worker.update_available.connect(self._on_app_update_available)
        self.app_update_check_worker.no_update.connect(self._on_no_app_update)
        self.app_update_check_worker.error.connect(self._on_app_update_error)
        self.app_update_check_worker.finished.connect(self._on_app_update_check_finished)
        self._track_thread(
            self.app_update_check_worker,
            self.app_update_check_worker,
        )
        self.app_update_check_worker.start()

    @Slot(str, object, str)
    def _on_app_update_available(self, version: str, release_asset, body: str) -> None:
        if self._shutdown_in_progress:
            return
        notes = body.strip()
        if notes and len(notes) > 800:
            notes = notes[:800] + "\n..."
        notes_block = f"Ghi chú:\n{notes}\n\n" if notes else ""
        message = (
            f"Đã có phiên bản mới: {version}\n\n"
            f"{notes_block}"
            "Bạn có muốn tải về và cập nhật ngay bây giờ không?"
        )
        reply = QMessageBox.question(self, "Cập nhật ứng dụng", message, QMessageBox.Yes | QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.app_update_manual_request = True
            self._start_app_update_download(release_asset)
        else:
            self.log_to_gui("Người dùng bỏ qua cập nhật ứng dụng.")

    @Slot(str, bool)
    def _on_no_app_update(self, latest_version: str, runtime_repaired: bool) -> None:
        runtime_note = " Node portable đã được sửa." if runtime_repaired else ""
        self.log_to_gui(
            f"Không có cập nhật mới. Phiên bản hiện tại: {APP_VERSION}, "
            f"mới nhất: {latest_version}.{runtime_note}"
        )
        if self.app_update_manual_request and not self._shutdown_in_progress:
            QMessageBox.information(
                self,
                "Không có cập nhật",
                f"Bạn đang ở phiên bản mới nhất: {APP_VERSION}.{runtime_note}",
            )

    def _start_app_update_download(self, release_asset) -> None:
        if self.app_update_download_worker and self.app_update_download_worker.isRunning():
            return

        self.log_to_gui("Đang tải bản cập nhật ứng dụng...")
        if hasattr(self, "app_update_action"):
            self.app_update_action.setEnabled(False)

        self._show_app_update_progress_dialog()
        self.app_update_download_worker = UpdateCheckerWorker(
            mode="download",
            release_asset=release_asset,
            proxy_url=getattr(self, "app_update_proxy_url", None),
            parent=self,
        )
        self.app_update_download_worker.download_progress.connect(self._on_app_update_progress)
        self.app_update_download_worker.status_signal.connect(self._on_app_update_status)
        self.app_update_download_worker.download_finished.connect(self._on_app_update_downloaded)
        self.app_update_download_worker.error.connect(self._on_app_update_error)
        self.app_update_download_worker.finished.connect(self._on_app_update_download_finished)
        self._track_thread(
            self.app_update_download_worker,
            self.app_update_download_worker,
        )
        self.app_update_download_worker.start()

    @Slot(int)
    def _on_app_update_progress(self, percent: int) -> None:
        if self.app_update_progress_dialog:
            self.app_update_progress_dialog.setValue(percent)

    @Slot(str)
    def _on_app_update_status(self, message: str) -> None:
        self.log_to_gui(message)
        if self.app_update_progress_dialog:
            self.app_update_progress_dialog.setLabelText(message)

    @Slot(str, str)
    def _on_app_update_downloaded(self, zip_path: str, runtime_path: str) -> None:
        self.log_to_gui(f"Đã tải xong cập nhật: {zip_path}")
        self._close_app_update_progress_dialog()
        if self._shutdown_in_progress:
            return
        self._launch_updater(zip_path, runtime_path or None)

    @Slot()
    def _on_app_update_check_finished(self) -> None:
        self.app_update_check_worker = None
        if hasattr(self, "app_update_action") and not (
            self.app_update_download_worker and self.app_update_download_worker.isRunning()
        ):
            self.app_update_action.setEnabled(True)

    @Slot()
    def _on_app_update_download_finished(self) -> None:
        self.app_update_download_worker = None
        self._close_app_update_progress_dialog()
        if hasattr(self, "app_update_action"):
            self.app_update_action.setEnabled(True)

    @Slot(str)
    def _on_app_update_error(self, message: str) -> None:
        self.log_to_gui(f"Lỗi cập nhật ứng dụng: {message}")
        self._close_app_update_progress_dialog()
        if hasattr(self, "app_update_action"):
            self.app_update_action.setEnabled(True)
        if self.app_update_manual_request and not self._shutdown_in_progress:
            QMessageBox.warning(self, "Cập nhật thất bại", message)

    def _show_app_update_progress_dialog(self) -> None:
        if self.app_update_progress_dialog:
            self.app_update_progress_dialog.close()
        self.app_update_progress_dialog = QProgressDialog("Đang tải bản cập nhật...", "", 0, 100, self)
        self.app_update_progress_dialog.setWindowTitle("Tải cập nhật")
        self.app_update_progress_dialog.setWindowModality(Qt.WindowModal)
        self.app_update_progress_dialog.setAutoClose(False)
        self.app_update_progress_dialog.setAutoReset(False)
        self.app_update_progress_dialog.show()

    def _close_app_update_progress_dialog(self) -> None:
        if self.app_update_progress_dialog:
            self.app_update_progress_dialog.close()
            self.app_update_progress_dialog = None

    def _launch_updater(self, zip_path: str, runtime_path: str | None = None) -> None:
        """Khởi chạy updater ngoài và thoát ứng dụng chính."""
        if getattr(sys, "frozen", False):
            base_dir = os.path.dirname(sys.executable)
        else:
            base_dir = os.path.dirname(os.path.abspath(__file__))

        candidate_paths = [
            os.path.join(base_dir, "UpdaterLauncher.exe"),
            os.path.join(base_dir, "updater_launcher.py"),
        ]

        updater_path = next((p for p in candidate_paths if os.path.exists(p)), None)
        if not updater_path:
            QMessageBox.critical(self, "Không tìm thấy Updater",
                                 "Không tìm thấy UpdaterLauncher.exe để chạy cập nhật an toàn.")
            return

        if updater_path.lower().endswith(".exe"):
            cmd = [updater_path, zip_path, base_dir, APP_MAIN_EXE_NAME]
        else:
            cmd = [sys.executable, updater_path, zip_path, base_dir, APP_MAIN_EXE_NAME]
        if runtime_path:
            cmd.append(runtime_path)

        try:
            subprocess.Popen(cmd, cwd=base_dir)
            QApplication.quit()
        except OSError as exc:
            QMessageBox.critical(self, "Lỗi khởi chạy Updater", f"Không thể khởi chạy updater: {exc}")
    
    def _check_aria2c_availability(self):
        aria2c_exe_name = "aria2c.exe" if platform.system() == "Windows" else "aria2c"
        local_aria2c_dir = os.path.join(SCRIPT_BASE_DIR_UI, DATA_DIR_NAME, "aria2c")
        local_aria2c_path = os.path.join(local_aria2c_dir, aria2c_exe_name)
        aria2c_to_test = None
        if os.path.exists(local_aria2c_path) and os.access(local_aria2c_path, os.X_OK):
            self.log_to_gui(f"Thông báo: Tìm thấy '{aria2c_exe_name}' cục bộ tại: {local_aria2c_path}")
            aria2c_to_test = local_aria2c_path
        else:
            self.log_to_gui(f"Thông báo: Không tìm thấy '{aria2c_exe_name}' tại '{local_aria2c_path}'. Đang kiểm tra PATH hệ thống...")
            system_aria2c_path = shutil.which("aria2c")
            if system_aria2c_path:
                self.log_to_gui(f"Thông báo: Tìm thấy 'aria2c' trong PATH hệ thống: {system_aria2c_path}")
                aria2c_to_test = system_aria2c_path
            else:
                self.log_to_gui(f"CẢNH BÁO: Không tìm thấy '{aria2c_exe_name}' trong thư mục cục bộ ({local_aria2c_dir}) hoặc PATH hệ thống.")
                QMessageBox.warning(self, "Không tìm thấy aria2c",
                                    f"Không tìm thấy '{aria2c_exe_name}' trong thư mục cục bộ:\n{local_aria2c_dir}\n"
                                    f"Hoặc trong PATH hệ thống.\n\n"
                                    f"Để sử dụng tính năng này, vui lòng:\n"
                                    f"1. Cài đặt aria2c và đảm bảo nó có trong PATH, hoặc\n"
                                    f"2. Đặt file '{aria2c_exe_name}' vào thư mục '{local_aria2c_dir}'.\n\n"
                                    "Tùy chọn sử dụng aria2c sẽ được tự động tắt trong cài đặt nếu bạn vừa bật nó.")
                if self.settings.get("use_aria2c", False):
                    self.settings["use_aria2c"] = False
                    self.log_to_gui("Đã tự động tắt tùy chọn 'Dùng aria2c' do không tìm thấy.")
                return False

        if aria2c_to_test:
            try:
                process = subprocess.Popen(
                    [aria2c_to_test, '--version'],
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0,
                    encoding='utf-8', errors='replace'
                )
                stdout, stderr = process.communicate(timeout=5)

                if process.returncode == 0 and stdout and "aria2 version" in stdout.lower():
                    version_line = stdout.splitlines()[0].strip() if stdout.splitlines() else "Không rõ phiên bản"
                    self.log_to_gui(f"'{aria2c_to_test}' hoạt động. Phiên bản: {version_line}")
                    return True
                else:
                    error_log = f"Cảnh báo: Lệnh '{aria2c_to_test} --version' không thành công hoặc output không mong đợi.\n"
                    if stdout: error_log += f"Stdout: {stdout.strip()}\n"
                    if stderr: error_log += f"Stderr: {stderr.strip()}"
                    self.log_to_gui(error_log)
                    QMessageBox.warning(self, "Lỗi kiểm tra aria2c",
                                        f"'{aria2c_to_test}' dường như không hoạt động đúng cách.\n"
                                        f"Vui lòng kiểm tra lại file hoặc cài đặt.\n\nChi tiết:\n{error_log}")
            except FileNotFoundError:
                 self.log_to_gui(f"CẢNH BÁO: Không thể thực thi '{aria2c_to_test}' (FileNotFoundError). Kiểm tra lại đường dẫn và quyền thực thi.")
            except subprocess.TimeoutExpired:
                self.log_to_gui(f"Lỗi: Lệnh '{aria2c_to_test} --version' bị timeout.")
                QMessageBox.warning(self, "Lỗi kiểm tra aria2c", f"Lệnh kiểm tra phiên bản aria2c tại\n'{aria2c_to_test}'\nbị timeout.")
            except Exception as e:
                self.log_to_gui(f"Lỗi khi kiểm tra phiên bản aria2c tại '{aria2c_to_test}': {e}")
                QMessageBox.critical(self, "Lỗi không mong muốn", f"Lỗi khi kiểm tra aria2c:\n{e}")
        
        # Nếu đến đây, có nghĩa là có vấn đề
        if self.settings.get("use_aria2c", False):
            self.settings["use_aria2c"] = False
            self.log_to_gui("Đã tự động tắt tùy chọn 'Dùng aria2c' do kiểm tra không thành công.")
        return False
    #@Slot(int)
    #def _on_save_thumbnail_option_changed(self, state):
        save_with_video = (state == Qt.Checked) 
        self.settings["save_thumbnail_with_video"] = save_with_video
        main_logic.save_settings_to_file(self.settings, GUI_SETTINGS_FILE_PATH)
        self.log_to_gui(f"Tùy chọn lưu thumbnail chung với video: {'Bật' if save_with_video else 'Tắt'}")

    def _load_download_history(self):
        self.log_to_gui("Đang nạp lịch sử tải xuống...")
        if not os.path.exists(HISTORY_FILE_PATH):
            self.log_to_gui("Không tìm thấy file lịch sử.")
            return

        try:
            with open(HISTORY_FILE_PATH, 'r', encoding='utf-8') as f:
                history_data = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            self.log_to_gui(f"Lỗi đọc file lịch sử: {e}. File có thể bị hỏng.")
            QMessageBox.warning(self, "Lỗi Lịch sử", f"Không thể đọc file lịch sử: {e}\n\nFile có thể sẽ được ghi đè nếu bạn thêm tác vụ mới.")
            return

        loaded_count = 0
        for item_data in history_data:
            if not all(k in item_data for k in ["task_id", "url", "title"]):
                self.log_to_gui(f"Mục lịch sử không hợp lệ, bỏ qua: {item_data.get('task_id', 'ID_UNKNOWN')}")
                continue

            task_id = item_data.get("task_id", f"history_{time.time()}_{loaded_count}") 
            url = item_data.get("url", "")
            title = item_data.get("title", "N/A")
            duration = item_data.get("duration", "--:--")
            resolution = item_data.get("resolution", "") # << THÊM MỚI
            proxy_status = item_data.get("proxy_status", "N/A")  # [UI-UPDATE]
            status_text = item_data.get("status_text", "Không rõ")
            verification_status = item_data.get("verification_status", "Chưa xác minh")
            progress = item_data.get("progress", "0")
            speed_eta = item_data.get("speed_eta", "-") 
            quality_requested = item_data.get("quality_requested", "N/A")
            file_path = item_data.get("file_path", "")
            error_details = item_data.get("error_details", "")
            timestamp_str = item_data.get("timestamp", datetime.now().isoformat())
            entity_id = item_data.get("entity_id", "") # << THÊM MỚI 
            expected_duration = item_data.get("expected_duration", "")  # [UI-UPDATE]

            if file_path and (status_text == "Hoàn thành!" or "OK" in verification_status):
                if not os.path.exists(file_path):
                    status_text = "File gốc đã xóa"
                    verification_status = "N/A (file xóa)"
            
            check_item = QStandardItem()
            check_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
            check_item.setCheckState(Qt.Unchecked)

            thumb_item = QStandardItem() 
            row_items = [
                check_item, # << MỚI
                thumb_item, QStandardItem(title), QStandardItem(duration),
                QStandardItem(proxy_status),  # [UI-UPDATE]
                QStandardItem(resolution),
                QStandardItem(status_text), QStandardItem(verification_status),
                QStandardItem(str(progress)), QStandardItem(speed_eta),
                QStandardItem(url), QStandardItem(task_id),
                QStandardItem(quality_requested), QStandardItem(file_path),
                QStandardItem(error_details), QStandardItem(timestamp_str),
                QStandardItem(entity_id), QStandardItem(expected_duration)  # [UI-UPDATE]
            ]
            try:
                dt_obj = datetime.fromisoformat(timestamp_str)
                row_items[COL_TIMESTAMP].setData(dt_obj, Qt.InitialSortOrderRole)
            except ValueError:
                row_items[COL_TIMESTAMP].setData(datetime.min, Qt.InitialSortOrderRole) 


            for item in row_items: item.setEditable(False)
            self.download_tasks_model.appendRow(row_items)
            if url: 
                 QTimer.singleShot(100 + loaded_count * 50, lambda t_id=task_id, u=url: self._request_thumbnail_for_history_item(t_id, u) )


            loaded_count += 1
        self.log_to_gui(f"Đã nạp {loaded_count} mục từ lịch sử.")
        self._update_item_count_and_controls()

        # Chỉ gọi hàm lọc trùng lặp nếu người dùng đã bật cài đặt
        if self.settings.get("auto_deduplicate_history", True):
            QTimer.singleShot(100, self._deduplicate_history_on_startup)


    def _deduplicate_history_on_startup(self):
        """Quét lịch sử đã tải và xóa các URL trùng lặp dựa trên quy tắc."""
        self.log_to_gui("Bắt đầu quá trình lọc trùng lặp URL trong lịch sử...")
        url_map = {}
        
        # 1. Nhóm tất cả các mục theo URL của chúng
        for row in range(self.download_tasks_model.rowCount()):
            url = self.download_tasks_model.data(self.download_tasks_model.index(row, COL_URL))
            if not url or not url.strip():
                continue

            item_data = {
                "row": row,
                "timestamp": self.download_tasks_model.data(self.download_tasks_model.index(row, COL_TIMESTAMP)),
                "status": self.download_tasks_model.data(self.download_tasks_model.index(row, COL_STATUS_TEXT)),
            }
            
            if url not in url_map:
                url_map[url] = []
            url_map[url].append(item_data)

        rows_to_remove = set()

        # 2. Áp dụng quy tắc để quyết định giữ lại mục nào và xóa mục nào
        for url, items in url_map.items():
            if len(items) <= 1:
                continue

            item_to_keep = None
            
            # Quy tắc ưu tiên: Giữ lại mục đã tải thành công
            for item in items:
                if item["status"] == "Hoàn thành!":
                    item_to_keep = item
                    break
            
            # Nếu không có mục nào thành công, giữ lại mục mới nhất (xuất hiện cuối cùng)
            if item_to_keep is None:
                items.sort(key=lambda x: x["timestamp"], reverse=True)
                item_to_keep = items[0]

            # 3. Thêm các mục không được giữ lại vào danh sách xóa
            for item in items:
                if item["row"] != item_to_keep["row"]:
                    rows_to_remove.add(item["row"])

        # 4. Thực hiện xóa
        if rows_to_remove:
            self.log_to_gui(f"Tìm thấy {len(rows_to_remove)} mục trùng lặp cần xóa.")
            
            # Sắp xếp các hàng theo thứ tự giảm dần để xóa an toàn
            sorted_rows = sorted(list(rows_to_remove), reverse=True)
            
            for row in sorted_rows:
                self.download_tasks_model.removeRow(row)

            self.log_to_gui("Đã xóa các mục trùng lặp. Lưu lại lịch sử...")
            self._save_download_history()
            self._update_item_count_and_controls()
        else:
            self.log_to_gui("Không tìm thấy mục nào trùng lặp.")

    def _save_download_history(self):
        history_data = []
        for row in range(self.download_tasks_model.rowCount()):
            item_data = {
                "task_id": self.download_tasks_model.data(self.download_tasks_model.index(row, COL_TASK_ID)) or f"generated_{row}",
                "url": self.download_tasks_model.data(self.download_tasks_model.index(row, COL_URL)) or "",
                "title": self.download_tasks_model.data(self.download_tasks_model.index(row, COL_TITLE)) or "N/A",
                "duration": self.download_tasks_model.data(self.download_tasks_model.index(row, COL_DURATION)) or "--:--",
                "proxy_status": self.download_tasks_model.data(self.download_tasks_model.index(row, COL_PROXY_STATUS)) or "N/A",  # [UI-UPDATE]
                "resolution": self.download_tasks_model.data(self.download_tasks_model.index(row, COL_RESOLUTION)) or "", # << THÊM MỚI
                "status_text": self.download_tasks_model.data(self.download_tasks_model.index(row, COL_STATUS_TEXT)) or "Không rõ",
                "verification_status": self.download_tasks_model.data(self.download_tasks_model.index(row, COL_VERIFICATION_STATUS)) or "Chưa xác minh",
                "progress": self.download_tasks_model.data(self.download_tasks_model.index(row, COL_PROGRESS)) or "0",
                "speed_eta": self.download_tasks_model.data(self.download_tasks_model.index(row, COL_SPEED_ETA)) or "-",
                "quality_requested": self.download_tasks_model.data(self.download_tasks_model.index(row, COL_QUALITY_REQUESTED)) or "N/A",
                "file_path": self.download_tasks_model.data(self.download_tasks_model.index(row, COL_FILE_PATH)) or "",
                "error_details": self.download_tasks_model.data(self.download_tasks_model.index(row, COL_ERROR_DETAILS)) or "",
                "timestamp": self.download_tasks_model.data(self.download_tasks_model.index(row, COL_TIMESTAMP)) or datetime.now().isoformat(),
                "entity_id": self.download_tasks_model.data(self.download_tasks_model.index(row, COL_ENTITY_ID)) or "", # << THÊM MỚI
                "expected_duration": self.download_tasks_model.data(self.download_tasks_model.index(row, COL_EXPECTED_DURATION)) or ""  # [UI-UPDATE]
            }
            history_data.append(item_data)

        try:
            self._ensure_data_directory() 
            with open(HISTORY_FILE_PATH, 'w', encoding='utf-8') as f:
                json.dump(history_data, f, indent=4, ensure_ascii=False)
        except IOError as e:
            self.log_to_gui(f"Lỗi lưu file lịch sử: {e}")
            QMessageBox.warning(self, "Lỗi Lưu Lịch sử", f"Không thể lưu file lịch sử: {e}")

    def _request_thumbnail_for_history_item(self, task_id: str, url: str):
        if not url or not task_id: return
        if task_id in self.active_thumbnail_fetchers and self.active_thumbnail_fetchers[task_id]["thread"].isRunning():
            return

        thread = QThread(self)
        worker = ThumbnailFetcher(task_id, url)
        worker.moveToThread(thread)

        worker.thumbnail_ready.connect(self._on_thumbnail_ready) 
        worker.log_message.connect(self._on_task_log_message) 
        thread.started.connect(worker.fetch)
        self._track_thread(
            thread,
            worker,
            completion_signals=(worker.lifecycle_finished,),
            cleanup_callback=lambda t_id=task_id: self.active_thumbnail_fetchers.pop(t_id, None),
        )

        self.active_thumbnail_fetchers[task_id] = {"thread": thread, "worker": worker}
        thread.start()

    def _handle_clear_all_history(self):
        reply = QMessageBox.question(self, "Xác nhận Xóa Toàn bộ Lịch sử",
                                     "Bạn có chắc muốn xóa toàn bộ lịch sử tải xuống không?\n"
                                     "Hành động này không thể hoàn tác.",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            self.log_to_gui("Đang xóa toàn bộ lịch sử...")
            self.download_tasks_model.removeRows(0, self.download_tasks_model.rowCount())
            self._save_download_history()
            self._update_item_count_and_controls()
            self.log_to_gui("Đã xóa toàn bộ lịch sử.")

    def _handle_clear_completed_tasks(self):
        self.log_to_gui("Đang xóa các mục đã hoàn thành...")
        rows_to_remove = []
        for row in range(self.download_tasks_model.rowCount() -1, -1, -1): 
            status = self.download_tasks_model.data(self.download_tasks_model.index(row, COL_STATUS_TEXT))
            if status == "Hoàn thành!":
                rows_to_remove.append(row)
        
        if not rows_to_remove:
            self.log_to_gui("Không có mục hoàn thành nào để xóa.")
            return

        reply = QMessageBox.question(self, "Xác nhận Xóa Mục Hoàn thành",
                                     f"Tìm thấy {len(rows_to_remove)} mục đã hoàn thành. Bạn có muốn xóa chúng khỏi lịch sử không?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            for row_idx in rows_to_remove:
                self.download_tasks_model.removeRow(row_idx)
            self._save_download_history()
            self._update_item_count_and_controls()
            self.log_to_gui(f"Đã xóa {len(rows_to_remove)} mục hoàn thành.")


    def _handle_clear_failed_tasks(self):
        self.log_to_gui("Đang xóa các mục bị lỗi...")
        rows_to_remove = []
        for row in range(self.download_tasks_model.rowCount() -1, -1, -1):
            status = self.download_tasks_model.data(self.download_tasks_model.index(row, COL_STATUS_TEXT))
            error_statuses = ["Lỗi yt-dlp", "Lỗi file sau tải", "Lỗi worker", "Lỗi (không rõ file)", "Thất bại", "Đã hủy"] 
            if any(err_stat in status for err_stat in error_statuses):
                rows_to_remove.append(row)

        if not rows_to_remove:
            self.log_to_gui("Không có mục bị lỗi nào để xóa.")
            return

        reply = QMessageBox.question(self, "Xác nhận Xóa Mục Bị lỗi",
                                     f"Tìm thấy {len(rows_to_remove)} mục bị lỗi/đã hủy. Bạn có muốn xóa chúng khỏi lịch sử không?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            for row_idx in rows_to_remove:
                self.download_tasks_model.removeRow(row_idx)
            self._save_download_history()
            self._update_item_count_and_controls()
            self.log_to_gui(f"Đã xóa {len(rows_to_remove)} mục bị lỗi/đã hủy.")

    def _handle_clear_thumbnails(self):
        """Xóa cache thumbnail an toàn."""
        if not THUMBNAIL_CACHE_DIR or not os.path.isdir(THUMBNAIL_CACHE_DIR):
            QMessageBox.information(self, "Cache Thumbnail", "Thư mục thumbnail đang trống hoặc không tồn tại.")
            return

        try:
            files = [f for f in os.listdir(THUMBNAIL_CACHE_DIR) if os.path.isfile(os.path.join(THUMBNAIL_CACHE_DIR, f))]
        except OSError as e:
            QMessageBox.warning(self, "Cache Thumbnail", f"Không thể đọc thư mục thumbnail: {e}")
            return

        if not files:
            QMessageBox.information(self, "Cache Thumbnail", "Thư mục thumbnail đang trống.")
            return

        total_size_bytes = 0
        for fname in files:
            fpath = os.path.join(THUMBNAIL_CACHE_DIR, fname)
            try:
                total_size_bytes += os.path.getsize(fpath)
            except OSError:
                continue

        total_mb = total_size_bytes / (1024 * 1024)
        reply = QMessageBox.question(
            self,
            "Dọn dẹp Cache Thumbnail",
            f"Tìm thấy {len(files)} file ảnh (Tổng: {total_mb:.2f} MB).\nBạn có chắc muốn xóa tất cả không?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        removed = 0
        for fname in files:
            fpath = os.path.join(THUMBNAIL_CACHE_DIR, fname)
            try:
                os.remove(fpath)
                removed += 1
            except OSError:
                continue

        QMessageBox.information(self, "Cache Thumbnail", f"Đã xóa {removed}/{len(files)} file thumbnail.")
        self.log_to_gui(f"Dọn dẹp cache thumbnail: đã xóa {removed}/{len(files)} file.")

    def _update_save_to_button_text(self):
        dir_name = os.path.basename(self.current_download_dir)
        if not dir_name: dir_name = self.current_download_dir
        max_len = 30; display_path = self.current_download_dir
        if len(display_path) > max_len: display_path = f".../{dir_name}" if dir_name else f"...{display_path[-max_len+4:]}"
        text = f"Lưu vào: {display_path}"
        self.save_to_button.setText(text)
        self.save_to_button.setToolTip(f"Thư mục lưu hiện tại: {self.current_download_dir}")


    def _toggle_system_log_visibility(self):
        # Xác định trạng thái mới dựa trên trạng thái hiện tại của widget log
        new_visibility_state = not self.system_log_widget.isVisible()
        
        self.system_log_widget.setVisible(new_visibility_state)
        
        # Đồng bộ trạng thái của QAction trên toolbar
        self.toggle_log_action.setChecked(new_visibility_state)
        
        # Đồng bộ trạng thái và text của QToolButton trong system_log_widget
        self.hide_log_button.setChecked(new_visibility_state)
        self.hide_log_button.setText("Ẩn" if new_visibility_state else "Hiện")

    @Slot()
    def _handle_paste_link_and_download(self):
        clipboard = QApplication.clipboard()
        urls_text = clipboard.text()
        if not urls_text or not urls_text.strip():
            self.log_to_gui("Clipboard rỗng hoặc không chứa URL hợp lệ.")
            QMessageBox.information(self, "Clipboard Rỗng", "Không tìm thấy URL nào trong clipboard.")
            return
        self.log_to_gui(f"Đã dán từ clipboard:\n{urls_text}")
        self._prepare_downloads_from_text(urls_text)

    def _confirm_cookie_mode_for_downloads(self, tasks_to_add):
        youtube_tasks = [
            task for task in tasks_to_add
            if str(task.get("type", "")).startswith("youtube")
        ]
        if not youtube_tasks:
            return True

        use_cookie_file = bool(self.settings.get("use_cookies", False))
        cookie_browser = str(self.settings.get("cookies_from_browser", "") or "").strip()
        if not use_cookie_file and not cookie_browser:
            return True

        if cookie_browser:
            extracted_path = str(self.settings.get("extracted_cookies_path", "") or "").strip()
            if extracted_path and os.path.isfile(extracted_path):
                cookie_source = f"file cookie đã trích xuất từ {cookie_browser.title()}"
            else:
                cookie_source = f"trình duyệt {cookie_browser.title()}"
        else:
            cookie_path = str(self.settings.get("cookies_file_path", "") or "").strip()
            cookie_source = f"file cookie {os.path.basename(cookie_path)}" if cookie_path else "file cookie đã chọn"

        preview_limit = 8
        url_lines = [f"• {task['url']}" for task in youtube_tasks[:preview_limit]]
        if len(youtube_tasks) > preview_limit:
            url_lines.append(f"• ... và {len(youtube_tasks) - preview_limit} URL khác")

        message = (
            "Chế độ cookie hiện đang được bật.\n"
            f"Nguồn cookie: {cookie_source}\n\n"
            f"Bạn có muốn tiến hành tải toàn bộ {len(youtube_tasks)} URL sau "
            "trong chế độ cookie không?\n\n"
            + "\n".join(url_lines)
            + "\n\nNhấn Yes hoặc Enter để tiếp tục. Chọn No để hủy toàn bộ lần tải này."
        )
        reply = QMessageBox.question(
            self,
            "Xác nhận tải bằng Cookie",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.Yes,
        )
        if reply == QMessageBox.Yes:
            self.log_to_gui(f"Người dùng xác nhận tải {len(youtube_tasks)} URL trong chế độ cookie.")
            return True

        self.log_to_gui("Người dùng hủy toàn bộ lần tải vì chế độ cookie đang bật.")
        return False

    def _prepare_downloads_from_text(self, urls_text, default_type="youtube"):
        if not self.yt_dlp_path:
            self.log_to_gui("Lỗi: yt-dlp chưa sẵn sàng. Vui lòng chờ quá trình khởi tạo hoàn tất.")
            QMessageBox.warning(self, "yt-dlp Chưa Sẵn Sàng", "yt-dlp chưa sẵn sàng. Vui lòng chờ hoặc kiểm tra log.")
            return
        if not self.current_download_dir or not os.path.isdir(self.current_download_dir):
            self.log_to_gui("Lỗi: Chưa chọn thư mục lưu hợp lệ.")
            QMessageBox.warning(self, "Chưa Chọn Thư Mục", "Vui lòng chọn thư mục lưu trữ hợp lệ trước khi tải.")
            self._select_download_directory()
            if not self.current_download_dir or not os.path.isdir(self.current_download_dir): return

        raw_urls = [url.strip() for url in urls_text.splitlines() if url.strip() and (url.startswith("http://") or url.startswith("https://"))]

        if not raw_urls:
            self.log_to_gui("Không tìm thấy URL hợp lệ nào để tải.")
            QMessageBox.information(self, "Không có URL", "Không tìm thấy URL hợp lệ nào trong nội dung đã dán.")
            return

        tasks_to_add = [] # Danh sách các task sẽ được thêm sau khi xác nhận
        urls_processed_for_playlist_prompt = set()

        for url_str in raw_urls:
            task_info_to_add = None

            # --- Bước 1: Kiểm tra có phải link thư mục Google Drive không ---
            drive_folder_id = gdrive_downloader.extract_folder_id_from_google_drive_url(url_str)
            if drive_folder_id:
                self.log_to_gui(f"URL '{url_str[:70]}...' được nhận diện là Thư mục Google Drive (ID: {drive_folder_id}).")
                task_info_to_add = {"url": url_str, "type": "drive_folder", "id": drive_folder_id}
                tasks_to_add.append(task_info_to_add)
                continue # Chuyển sang URL tiếp theo

            # --- Bước 2: Nếu không phải thư mục, kiểm tra có phải link file Google Drive không ---
            drive_file_id = gdrive_downloader.extract_file_id_from_google_drive_url(url_str)
            if drive_file_id:
                self.log_to_gui(f"URL '{url_str[:70]}...' được nhận diện là File Google Drive (ID: {drive_file_id}).")
                task_info_to_add = {"url": url_str, "type": "drive", "id": drive_file_id}
                tasks_to_add.append(task_info_to_add)
                continue # Chuyển sang URL tiếp theo
            
            # --- Bước 3: Nếu không phải Google Drive, xử lý như link YouTube ---
            url_type, entity_id, original_url = url_handler.get_url_type_and_id(url_str)
            log_msg_type = url_type
            if url_type == url_handler.URL_TYPE_UNKNOWN:
                log_msg_type = "video (hoặc không xác định)"

            self.log_to_gui(f"URL '{url_str[:70]}...' được nhận diện (url_handler) là: {log_msg_type} (ID/Entity: {entity_id})")

            is_potential_list_or_channel = (url_type == url_handler.URL_TYPE_PLAYLIST or \
                                            url_type == url_handler.URL_TYPE_CHANNEL)

            if is_potential_list_or_channel and original_url not in urls_processed_for_playlist_prompt:
                urls_processed_for_playlist_prompt.add(original_url)
                type_name = "Playlist" if url_type == url_handler.URL_TYPE_PLAYLIST else "Kênh YouTube"
                reply = QMessageBox.question(self, f"Xác nhận tải {type_name}",
                                                f"URL bạn dán có vẻ là một {type_name.lower()}:\n{url_str}\n\nBạn có muốn tải toàn bộ video từ {type_name.lower()} này không?",
                                                QMessageBox.Yes | QMessageBox.No | QMessageBox.Cancel,
                                                QMessageBox.Yes)
                if reply == QMessageBox.Yes:
                    self.log_to_gui(f"Người dùng xác nhận tải toàn bộ {type_name.lower()}: {url_str}")
                    task_info_to_add = {"url": url_str, "type": "youtube_playlist_or_channel", "id": entity_id}
                elif reply == QMessageBox.No:
                    is_actually_video, video_id_if_any, _ = url_handler.get_url_type_and_id(original_url)
                    if is_actually_video == url_handler.URL_TYPE_VIDEO and video_id_if_any:
                        self.log_to_gui(f"Người dùng chọn chỉ tải video đơn lẻ: {original_url} (Video ID: {video_id_if_any})")
                        task_info_to_add = {"url": original_url, "type": "youtube_video", "id": video_id_if_any}
                    else:
                        self.log_to_gui(f"Người dùng chọn KHÔNG tải {type_name.lower()} và URL không phải video đơn lẻ. Bỏ qua: {url_str}")
                else: # Cancel
                    self.log_to_gui(f"Người dùng hủy tải {type_name.lower()}: {url_str}")
            elif not is_potential_list_or_channel and url_type != url_handler.URL_TYPE_UNKNOWN: # Là video đơn lẻ
                task_info_to_add = {"url": url_str, "type": "youtube_video", "id": entity_id}
            elif url_type == url_handler.URL_TYPE_UNKNOWN:
                self.log_to_gui(f"URL '{url_str[:70]}...' không được nhận diện. Thử xử lý như một video đơn lẻ.")
                # Coi như video đơn và để cho yt-dlp tự xử lý.
                task_info_to_add = {"url": url_str, "type": "youtube_video", "id": None}

            if task_info_to_add:
                tasks_to_add.append(task_info_to_add)

        if not self._confirm_cookie_mode_for_downloads(tasks_to_add):
            return

        selected_quality_label = self.quality_main_combo.currentText()
        quality_format_string = self.quality_options_map.get(selected_quality_label, "bv*+ba/b")
        self.settings["last_quality_preference_label"] = selected_quality_label
        main_logic.save_settings_to_file(self.settings, GUI_SETTINGS_FILE_PATH)

        added_count = 0
        for task_info in tasks_to_add:
            self._add_task_to_model_and_queue(
                url=task_info["url"],
                quality_label=selected_quality_label if task_info["type"].startswith("youtube") else "N/A (Drive)", # Chất lượng không áp dụng cho Drive
                quality_format=quality_format_string if task_info["type"].startswith("youtube") else "",
                task_type=task_info["type"], # Thêm loại task
                entity_id_for_task=task_info.get("id") # ID của video, playlist, channel hoặc Drive file ID
            )
            added_count +=1

        if added_count > 0:
            self.log_to_gui(f"Đã thêm {added_count} tác vụ vào hàng đợi.")
            self._save_download_history()
    def _add_task_to_model_and_queue(self, url, quality_label, quality_format,
                                     initial_title=None, initial_duration="--:--",
                                     initial_status="Đang chờ...", initial_task_id=None,
                                     task_type="youtube_video", # Thêm task_type, mặc định là youtube_video
                                     entity_id_for_task=None): # Thêm entity_id
        if initial_task_id:
            task_id = initial_task_id
        else:
            self.next_task_id_counter += 1
            task_id = f"task_{time.strftime('%H%M%S')}_{self.next_task_id_counter}"

        check_item = QStandardItem()
        check_item.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled)
        check_item.setCheckState(Qt.Unchecked)

        thumb_item = QStandardItem()
        title_to_display = initial_title

        if not title_to_display:
            if task_type == "drive_folder":
                title_to_display = f"Thư mục Drive: {entity_id_for_task}"
                initial_status = "Đang lấy danh sách file..."
                # Dùng icon thư mục cho dễ nhận biết
                thumb_item.setIcon(self.style().standardIcon(QStyle.SP_DirIcon))
            elif task_type == "drive":
                title_to_display = f"Drive ID: {entity_id_for_task if entity_id_for_task else url.split('/')[-2][:20]}..."
                # Thumbnail cho Drive sẽ không tự động lấy ở bước này, có thể để trống hoặc icon mặc định
                default_drive_pixmap = QPixmap(120, 90)
                default_drive_pixmap.fill(QColor(APP_THEME["drive_thumb_bg"])) # Màu xanh lá nhạt cho Drive
                painter = QPainter(default_drive_pixmap)
                painter.setPen(QColor(APP_THEME["drive_thumb_text"]))
                font = painter.font(); font.setPointSize(10); painter.setFont(font)
                painter.drawText(default_drive_pixmap.rect(), Qt.AlignCenter, "G-Drive")
                painter.end()
                thumb_item.setIcon(QIcon(default_drive_pixmap))

            elif task_type == "youtube_playlist_or_channel":
                title_to_display = f"Playlist/Channel: {url[:40]}..."
                initial_status = "Đang lấy danh sách video..."
                # Icon cho playlist/channel
                thumb_item.setIcon(self.style().standardIcon(QStyle.SP_MediaPlay))

            elif task_type.startswith("youtube"):
                title_to_display = f"Đang lấy TT: {url[:40]}..."
                QTimer.singleShot(10, lambda t_id=task_id, u=url: self._request_thumbnail_for_history_item(t_id, u))
            else: # Các loại khác (nếu có)
                title_to_display = f"Unknown Task: {url[:40]}..."


        current_timestamp_iso = datetime.now().isoformat()
        proxy_status_text = "Proxy" if self.settings.get("use_proxy", False) else "Direct"  # [UI-UPDATE]
        row_items = [
            check_item, # << MỚI
            thumb_item, QStandardItem(title_to_display), QStandardItem(initial_duration),
            QStandardItem(proxy_status_text),  # [UI-UPDATE]
            QStandardItem(""), # Placeholder cho độ phân giải
            QStandardItem(initial_status), QStandardItem("Chờ xác minh" if task_type.startswith("youtube") else "N/A (Drive)"),
            QStandardItem("0"), QStandardItem("- | ETA: -"),
            QStandardItem(url), QStandardItem(task_id),
            QStandardItem(quality_label), QStandardItem(""), QStandardItem(""),
            QStandardItem(current_timestamp_iso),
            QStandardItem(entity_id_for_task),
            QStandardItem("")  # expected duration placeholder [UI-UPDATE]
        ]
        # ... (setData cho timestamp, setEditable(False) như cũ) ...
        try:
            dt_obj = datetime.fromisoformat(current_timestamp_iso)
            row_items[COL_TIMESTAMP].setData(dt_obj, Qt.InitialSortOrderRole)
        except ValueError:
            row_items[COL_TIMESTAMP].setData(datetime.min, Qt.InitialSortOrderRole)

        for item in row_items: item.setEditable(False)
        self.download_tasks_model.insertRow(0, row_items)
        self._update_item_count_and_controls()

        if initial_status == "Đang chờ...":
            self.active_threads[task_id] = {
                "url": url, "quality_label": quality_label, "quality_format": quality_format,
                "status": "queued", "row": 0,
                "verification_status": "pending",
                "task_type": task_type, # Lưu loại task
                "entity_id": entity_id_for_task # Lưu ID (video, playlist, channel, or Drive file ID)
            }
            if task_type == "drive": # Nếu là task Drive, cần đảm bảo service trước khi xử lý queue
                self._ensure_drive_service(callback_on_success=self._process_download_queue)
            else:
                self._process_download_queue()
    def _ensure_drive_service(self, callback_on_success=None):
        self.log_to_gui("Kiểm tra Google Drive service...")
        if self.drive_service and hasattr(self.drive_service, 'files'): # Kiểm tra sơ bộ service
            self.log_to_gui("Google Drive service đã sẵn sàng.")
            if callback_on_success:
                callback_on_success()
            return True

        if self.drive_auth_thread and self.drive_auth_thread.isRunning():
            self.log_to_gui("Xác thực Google Drive đang diễn ra...")
            self.pending_drive_action_callback = callback_on_success # Lưu lại callback
            return False

        self.log_to_gui("Google Drive service chưa sẵn sàng. Bắt đầu xác thực (kết nối trực tiếp, bỏ qua proxy)...")
        self.drive_auth_pending = True
        self.pending_drive_action_callback = callback_on_success

        drive_proxy_url = None  # Force direct connection for Drive auth/download

        self.drive_auth_thread = QThread(self)
        self.drive_auth_worker = GoogleDriveAuthWorker(proxy_url=drive_proxy_url)
        self.drive_auth_worker.moveToThread(self.drive_auth_thread)

        self.drive_auth_worker.finished.connect(self._on_drive_auth_finished)
        self.drive_auth_worker.log_signal.connect(self.log_to_gui) # Kết nối log từ worker

        self.drive_auth_thread.started.connect(self.drive_auth_worker.run)
        self._track_thread(
            self.drive_auth_thread,
            self.drive_auth_worker,
            completion_signals=(self.drive_auth_worker.finished,),
            cleanup_callback=lambda thread=self.drive_auth_thread: self._clear_managed_thread_refs(
                "drive_auth_thread", "drive_auth_worker", thread
            ),
        )

        self.drive_auth_thread.start()
        return False
    @Slot(object, str)
    def _on_drive_auth_finished(self, drive_service_obj, message):
        self.log_to_gui(message) # Log đầy đủ thông báo từ worker auth
        self.drive_service = drive_service_obj
        self.drive_auth_pending = False # Đặt lại cờ

        if self._shutdown_in_progress:
            self.pending_drive_action_callback = None
            return

        if self.drive_service:
            self.log_to_gui("Xác thực Google Drive thành công. Service đã sẵn sàng.")
            if hasattr(self, 'pending_drive_action_callback') and self.pending_drive_action_callback:
                try:
                    self.pending_drive_action_callback()
                except Exception as e_cb:
                    self.log_to_gui(f"Lỗi khi thực thi callback sau xác thực Drive: {e_cb}")
                self.pending_drive_action_callback = None
        else:
            self.log_to_gui("Xác thực Google Drive thất bại. Không thể tải file từ Google Drive.")
            QMessageBox.critical(self, "Lỗi Xác Thực Google Drive",
                                 "Không thể xác thực với Google Drive. Các tác vụ tải từ Drive sẽ không hoạt động.\n"
                                 "Vui lòng kiểm tra file credentials.json và kết nối mạng.")
            # Xóa callback nếu có để tránh gọi không cần thiết
            self.pending_drive_action_callback = None
            # Cập nhật trạng thái các task Drive đang chờ thành lỗi
            for task_id, task_data in list(self.active_threads.items()):
                if task_data.get("task_type") == "drive" and task_data.get("status") == "queued":
                    self._on_task_finished(task_id, "Lỗi xác thực Drive", False, "", "Không thể xác thực Google Drive.")


    @Slot(str, QPixmap)
    def _on_thumbnail_ready(self, task_id, pixmap):
        row_index = self._find_row_for_task_id(task_id)
        if row_index is not None:
            thumb_item = self.download_tasks_model.item(row_index, COL_THUMBNAIL)
            if thumb_item:
                thumb_item.setIcon(QIcon(pixmap))
            else: 
                self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_THUMBNAIL), QIcon(pixmap), Qt.DecorationRole)


    @Slot(str, str, str, str)
    def _on_metadata_retrieved(self, task_id, title, duration, resolution):
        row_index = self._find_row_for_task_id(task_id)
        if row_index is not None:
            # Cập nhật tiêu đề
            if title and title.strip():
                current_title_item = self.download_tasks_model.item(row_index, COL_TITLE)
                current_title_text = current_title_item.text() if current_title_item else ""
                if title != current_title_text:
                    self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_TITLE), title)

            # Cập nhật thời lượng
            if duration and duration.strip() and duration != "--:--":
                current_duration_item = self.download_tasks_model.item(row_index, COL_DURATION)
                current_duration_text = current_duration_item.text() if current_duration_item else "--:--"
                if duration != current_duration_text:
                    self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_DURATION), duration)

            # Cập nhật độ phân giải
            if resolution and resolution.strip():
                self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_RESOLUTION), resolution)
            
            # Không nên lưu lịch sử ở đây vì có thể được gọi nhiều lần với thông tin tạm thời.
            # Việc lưu lịch sử nên được thực hiện khi tác vụ kết thúc (thành công/thất bại) 
            # hoặc khi thông tin xác minh file hoàn tất.
            # self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_TIMESTAMP), datetime.now().isoformat())
            # self._save_download_history() 


    @Slot(str, int, str, str)
    def _on_progress_update(self, task_id, percent, speed, eta):
        row_index = self._find_row_for_task_id(task_id)
        if row_index is not None:
            self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_PROGRESS), str(percent))
            self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_SPEED_ETA), f"{speed} | ETA: {eta}")

    @Slot(str, str, bool, str, str)
    def _on_task_finished(self, task_id, final_message, success_status, downloaded_file_path, error_details):
        self.log_to_gui(f"Tác vụ tải {task_id} hoàn thành. Kết quả: {final_message} (Thành công: {success_status}), Path: '{downloaded_file_path}'")
        if self._shutdown_in_progress:
            return
        row_index = self._find_row_for_task_id(task_id)
        
        if row_index is not None:
            self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_STATUS_TEXT), final_message)
            self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_PROGRESS), "100" if success_status else self.download_tasks_model.data(self.download_tasks_model.index(row_index, COL_PROGRESS))) 

            if success_status:
                self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_SPEED_ETA), "Hoàn thành")
                if downloaded_file_path and os.path.exists(downloaded_file_path):
                    self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_FILE_PATH), downloaded_file_path)
                    
                    # Kiểm tra loại tác vụ trước khi xác minh
                    task_info_for_type_check = self.active_threads.get(task_id)
                    current_task_type = "unknown" 
                    if task_info_for_type_check:
                        current_task_type = task_info_for_type_check.get("task_type", "youtube_video") # Mặc định là youtube nếu không rõ

                    if current_task_type.startswith("youtube"): # Chỉ xác minh nếu là tải từ YouTube
                        if self.ffprobe_path and video_verifier:
                            self.log_to_gui(f"Bắt đầu xác minh hậu kỳ cho file YouTube: {downloaded_file_path}")
                            self._start_video_verification(task_id, downloaded_file_path)
                        else:
                            self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_VERIFICATION_STATUS), "N/A (ffprobe lỗi)")
                            self.log_to_gui(f"ffprobe không sẵn sàng, bỏ qua xác minh cho file YouTube: {downloaded_file_path}")
                    elif current_task_type == "drive":
                        # Đối với file Drive, cột Verification Status đã được đặt là "N/A (Drive)" khi thêm task.
                        # Không cần làm gì thêm ở đây, chỉ log lại.
                        self.log_to_gui(f"Bỏ qua xác minh cho file Google Drive: {downloaded_file_path}")
                    else: # Các loại task không xác định khác (nếu có)
                        self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_VERIFICATION_STATUS), "N/A (không xác minh)")

                else: # File không tồn tại hoặc đường dẫn không có
                    self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_VERIFICATION_STATUS), "Lỗi đường dẫn file" if downloaded_file_path else "Không có đường dẫn")
                    if downloaded_file_path:
                         self.log_to_gui(f"CẢNH BÁO: Tải báo thành công nhưng file '{downloaded_file_path}' không tồn tại sau đó.")
            
            else: # success_status is False
                self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_SPEED_ETA), "Thất bại" if "Lỗi" in final_message else final_message) 
                # Trạng thái xác minh đã được đặt là "N/A (Drive)" hoặc "Chờ xác minh" khi thêm task,
                # nếu lỗi thì để là "Không xác minh" nếu không phải Drive.
                if self.download_tasks_model.data(self.download_tasks_model.index(row_index, COL_VERIFICATION_STATUS)) != "N/A (Drive)":
                    self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_VERIFICATION_STATUS), "Không xác minh")
                
                if error_details:
                    self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_ERROR_DETAILS), error_details)
                    tooltip_text = f"Lỗi: {final_message}\nChi tiết: {error_details[:200]}" # Giới hạn chi tiết lỗi cho tooltip
                    for col in range(TOTAL_COLUMNS): 
                        item = self.download_tasks_model.item(row_index, col)
                        if item: item.setToolTip(tooltip_text)
            
            self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_TIMESTAMP), datetime.now().isoformat())
            self._save_download_history()

        # Dọn dẹp task khỏi danh sách active_threads bất kể thành công hay thất bại
        if task_id in self.active_threads:
            task_data_popped = self.active_threads.pop(task_id, None)
            if task_data_popped:
                 self.log_to_gui(f"Đã xóa task {task_id} khỏi active_threads.")
        
        self._process_download_queue()


    def _start_video_verification(self, task_id: str, file_path: str):
        if task_id in self.active_verification_threads and self.active_verification_threads[task_id]["thread"].isRunning():
            self.log_to_gui(f"Luồng xác minh cho {task_id} đã chạy. Bỏ qua.")
            return

        row_index = self._find_row_for_task_id(task_id)
        if row_index is not None:
            self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_VERIFICATION_STATUS), "Đang kiểm tra...")

        thread = QThread(self)
        worker = VerificationWorker(task_id, file_path)
        worker.moveToThread(thread)
        worker.verification_started.connect(self._on_verification_started)
        worker.verification_finished.connect(self._on_verification_finished)
        thread.started.connect(worker.run)
        self._track_thread(
            thread,
            worker,
            completion_signals=(worker.lifecycle_finished,),
            cleanup_callback=lambda t_id=task_id: self.active_verification_threads.pop(t_id, None),
        )
        self.active_verification_threads[task_id] = {"thread": thread, "worker": worker}
        thread.start()
        self.log_to_gui(f"Đã khởi chạy luồng xác minh cho tác vụ {task_id} với file '{file_path}'.")


    @Slot(str)
    def _on_verification_started(self, task_id: str):
        row_index = self._find_row_for_task_id(task_id)
        if row_index is not None:
            self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_VERIFICATION_STATUS), "Đang kiểm tra...")


    @Slot(str, object)
    def _on_verification_finished(self, task_id: str, verification_result):
        self.log_to_gui(f"Xác minh hoàn thành cho {task_id}. Thành công (ffprobe process): {verification_result.success}, File readable: {verification_result.file_readable}")
        if self._shutdown_in_progress:
            return
        row_index = self._find_row_for_task_id(task_id)
        status_msg = "Lỗi không rõ"
        tooltip_for_verification = ""

        if row_index is not None:
            if verification_result.success and verification_result.file_readable:
                status_msg = "OK"
                duration_str_from_verify = ""
                if verification_result.verified_duration is not None:
                    secs = int(verification_result.verified_duration)
                    duration_str_from_verify = f"{secs // 3600:02d}:{(secs % 3600) // 60:02d}:{secs % 60:02d}"
                    self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_DURATION), duration_str_from_verify)

                if verification_result.verified_title:
                    current_title = self.download_tasks_model.data(self.download_tasks_model.index(row_index, COL_TITLE))
                    if current_title != verification_result.verified_title and ("Đang lấy TT:" not in current_title and current_title != "N/A"):
                        self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_TITLE), verification_result.verified_title)

                if verification_result.verified_resolution:
                    self.log_to_gui(f"Cập nhật độ phân giải thực tế cho task {task_id} thành: {verification_result.verified_resolution}")
                    self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_RESOLUTION), verification_result.verified_resolution)

                expected_dur_str = self.download_tasks_model.data(self.download_tasks_model.index(row_index, COL_EXPECTED_DURATION)) or ""
                def _hhmmss_to_secs(hhmmss: str) -> float:
                    try:
                        parts = hhmmss.strip().split(":")
                        parts = [int(p) for p in parts]
                        if len(parts) == 3:
                            return parts[0]*3600 + parts[1]*60 + parts[2]
                        elif len(parts) == 2:
                            return parts[0]*60 + parts[1]
                        elif len(parts) == 1:
                            return float(parts[0])
                    except Exception:
                        return 0.0
                    return 0.0
                is_duration_mismatch = False
                if expected_dur_str and verification_result.verified_duration is not None:
                    expected_secs = _hhmmss_to_secs(expected_dur_str)
                    actual_secs = float(verification_result.verified_duration)
                    if expected_secs > 0 and abs(expected_secs - actual_secs) > 10.0:
                        is_duration_mismatch = True
                        current_url = self.download_tasks_model.data(self.download_tasks_model.index(row_index, COL_URL))
                        retry_count = self.integrity_retry_counts.get(current_url, 0)
                        if retry_count == 0:
                            self.log_to_gui(f"CẢNH BÁO: Lệch thời lượng (Gốc: {expected_secs}s, Tải: {actual_secs}s). Tự động tải lại lần 1...")
                            self.integrity_retry_counts[current_url] = 1
                            self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_VERIFICATION_STATUS), "Đang tải lại (Lệch TL)...")
                            quality_label = self.download_tasks_model.data(self.download_tasks_model.index(row_index, COL_QUALITY_REQUESTED))
                            old_title = self.download_tasks_model.data(self.download_tasks_model.index(row_index, COL_TITLE))
                            entity_id_ctx = self.download_tasks_model.data(self.download_tasks_model.index(row_index, COL_ENTITY_ID)) or ""
                            url_val = current_url or ""
                            title_val = old_title or ""
                            task_type_for_redownload = "unknown"
                            if title_val.startswith("Thư mục Drive:"):
                                task_type_for_redownload = "drive_folder"
                            elif title_val.startswith("Drive ID:") or "drive.google.com/file" in url_val or (entity_id_ctx and url_val.startswith("gdrive://")):
                                task_type_for_redownload = "drive"
                            elif "youtube.com" in url_val or "youtu.be" in url_val:
                                url_type_ctx, _, _ = url_handler.get_url_type_and_id(url_val)
                                if url_type_ctx in (url_handler.URL_TYPE_PLAYLIST, url_handler.URL_TYPE_CHANNEL):
                                    task_type_for_redownload = "youtube_playlist_or_channel"
                                else:
                                    task_type_for_redownload = "youtube_video"
                            QTimer.singleShot(1000, lambda: self._handle_redownload_task(row_index, task_id, current_url, quality_label, old_title, task_type_for_redownload))
                            return
                        else:
                            self.log_to_gui(f"LỖI: Vẫn lệch thời lượng sau khi tải lại. Gốc: {expected_secs}s vs Tải: {actual_secs}s")
                            status_msg = "Chênh lệch thời lượng"
                            if current_url in self.integrity_retry_counts:
                                del self.integrity_retry_counts[current_url]
                if not is_duration_mismatch:
                    current_url = self.download_tasks_model.data(self.download_tasks_model.index(row_index, COL_URL))
                    if current_url in self.integrity_retry_counts:
                        del self.integrity_retry_counts[current_url]

                tooltip_for_verification = (f"Thời lượng: {duration_str_from_verify if duration_str_from_verify else 'N/A'}\n"
                                            f"Độ phân giải: {verification_result.verified_resolution or 'N/A'}")
                if expected_dur_str:
                    tooltip_for_verification += f"\nĐộ dài gốc: {expected_dur_str}"
                    if duration_str_from_verify:
                        tooltip_for_verification += f"\nĐộ dài thực tế: {duration_str_from_verify}"
            
            elif verification_result.error_message:
                status_msg = f"Lỗi X.Minh"
                tooltip_for_verification = f"Lỗi xác minh:\n{verification_result.error_message}"
                self.log_to_gui(f"Lỗi xác minh {task_id}: {verification_result.error_message}")

            item_verify_status = self.download_tasks_model.item(row_index, COL_VERIFICATION_STATUS)
            if item_verify_status:
                item_verify_status.setText(status_msg)
                item_verify_status.setToolTip(tooltip_for_verification)
            
            # Đảm bảo lưu lại lịch sử sau khi đã cập nhật tất cả thông tin
            self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_TIMESTAMP), datetime.now().isoformat())
            self._save_download_history()

    @Slot(str, list)
    def _on_drive_folder_items_retrieved(self, task_id, files: list):
        self.log_to_gui(f"Đã lấy được {len(files)} file từ tác vụ thư mục {task_id}.")
        if self._shutdown_in_progress:
            return
        row_index = self._find_row_for_task_id(task_id)
        if row_index is not None:
            status_text = f"Hoàn thành! (Đã thêm {len(files)} file vào hàng đợi)"
            self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_STATUS_TEXT), status_text)
            self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_PROGRESS), "100")
        
        # Dọn dẹp task meta
        if task_id in self.active_threads:
            self.active_threads.pop(task_id, None)

        # Thêm từng file vào hàng đợi tải xuống
        if files:
            selected_quality_label = "N/A (Drive)" # Chất lượng không áp dụng cho Drive
            for file_info in files:
                # Tạo một URL giả hoặc dùng URL thư mục gốc để tham chiếu
                pseudo_url = f"gdrive://file/{file_info['id']}" 
                self._add_task_to_model_and_queue(
                    url=pseudo_url,
                    quality_label=selected_quality_label,
                    quality_format="",
                    initial_title=file_info['name'],
                    task_type='drive',
                    entity_id_for_task=file_info['id']
                )
            self._save_download_history() # Lưu lại sau khi thêm loạt file

    @Slot(str, str)
    def _on_drive_folder_fetch_error(self, task_id, error_message):
        self.log_to_gui(f"Lỗi khi lấy danh sách file cho tác vụ {task_id}: {error_message}")
        if self._shutdown_in_progress:
            return
        row_index = self._find_row_for_task_id(task_id)
        if row_index is not None:
            self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_STATUS_TEXT), "Lỗi lấy danh sách")
            self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_ERROR_DETAILS), error_message)
        
        # Dọn dẹp task meta
        if task_id in self.active_threads:
            self.active_threads.pop(task_id, None)
        self._save_download_history()

    @Slot(str, list)
    def _on_playlist_items_retrieved(self, task_id, video_urls):
        """Xử lý khi lấy danh sách video từ playlist/channel thành công."""
        self.log_to_gui(f"Đã lấy danh sách {len(video_urls)} video từ playlist/channel cho tác vụ {task_id}")
        if self._shutdown_in_progress:
            return
        
        # Tìm hàng của tác vụ playlist gốc
        row_index = self._find_row_for_task_id(task_id)
        if row_index is not None:
            # Cập nhật trạng thái của tác vụ playlist gốc
            status_message = f"Hoàn thành! (Tìm thấy {len(video_urls)} video)"
            self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_STATUS_TEXT), status_message)
            self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_PROGRESS), 100)
        
        # Dọn dẹp tác vụ playlist gốc
        if task_id in self.active_threads:
            self.active_threads.pop(task_id, None)
        
        # Thêm từng video vào hàng đợi tải xuống
        for url in video_urls:
            self._add_task_to_model_and_queue(
                url=url,
                quality_label="Tốt nhất (MP4)",  # Sử dụng chất lượng mặc định
                quality_format=self.quality_options_map.get("Tốt nhất (MP4)", "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/b"),
                task_type="youtube_video",  # Mỗi video là một tác vụ riêng
                entity_id_for_task=url  # URL làm entity ID cho video đơn
            )
        
        # Lưu lịch sử sau khi thêm tất cả video
        self._save_download_history()
        self.log_to_gui(f"Đã thêm {len(video_urls)} video vào hàng đợi tải xuống")

    @Slot(str, str)
    def _on_playlist_fetch_error(self, task_id, error_message):
        """Xử lý khi lấy danh sách video từ playlist/channel thất bại."""
        self.log_to_gui(f"Lỗi khi lấy danh sách video cho tác vụ {task_id}: {error_message}")
        if self._shutdown_in_progress:
            return
        
        # Tìm hàng của tác vụ playlist gốc
        row_index = self._find_row_for_task_id(task_id)
        if row_index is not None:
            # Cập nhật trạng thái thành lỗi
            self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_STATUS_TEXT), "Lỗi lấy danh sách")
            self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_ERROR_DETAILS), error_message)
        
        # Dọn dẹp tác vụ playlist gốc
        if task_id in self.active_threads:
            self.active_threads.pop(task_id, None)
        
        # Lưu lịch sử
        self._save_download_history()

    @Slot()
    def _handle_manual_ip_change(self):
        """Xử lý yêu cầu đổi IP proxy từ SettingsDialog."""
        if not self.proxy_manager:
            QMessageBox.warning(self, "Proxy chưa bật", "Vui lòng bật và cấu hình proxy trước khi đổi IP.")
            return

        if self.ip_change_thread and self.ip_change_thread.isRunning():
            QMessageBox.information(self, "Đang xử lý", "Một yêu cầu đổi IP khác đang được xử lý. Vui lòng đợi.")
            return

        # Hiển thị thông báo đang chờ
        self.ip_change_progress_msgbox = QMessageBox(
            QMessageBox.Information, 
            "Đang đổi IP", 
            "Đang gửi yêu cầu đổi IP proxy...\nVui lòng không đóng cửa sổ này.",
            QMessageBox.NoButton, 
            self
        )
        self.ip_change_progress_msgbox.setStandardButtons(QMessageBox.NoButton)  # Ẩn nút OK
        self.ip_change_progress_msgbox.show()

        # Khởi chạy worker
        self.ip_change_thread = QThread(self)
        self.ip_change_worker = IPChangeWorker(self.proxy_manager)
        self.ip_change_worker.moveToThread(self.ip_change_thread)

        self.ip_change_worker.finished.connect(self._on_manual_ip_change_finished)
        self.ip_change_thread.started.connect(self.ip_change_worker.run)
        self._track_thread(
            self.ip_change_thread,
            self.ip_change_worker,
            completion_signals=(self.ip_change_worker.finished,),
            cleanup_callback=lambda thread=self.ip_change_thread: self._clear_managed_thread_refs(
                "ip_change_thread", "ip_change_worker", thread
            ),
        )

        self.ip_change_thread.start()

    @Slot(bool, str)
    def _on_manual_ip_change_finished(self, success, message):
        """Xử lý kết quả đổi IP proxy."""
        # Đóng thông báo đang chờ
        if self.ip_change_progress_msgbox:
            self.ip_change_progress_msgbox.accept()
            self.ip_change_progress_msgbox = None

        if self._shutdown_in_progress:
            return

        # Hiển thị kết quả cuối cùng
        if success:
            QMessageBox.information(self, "Thành công", message)
        else:
            QMessageBox.warning(self, "Thất bại", message)

        self.log_to_gui(f"[IP Change] Kết quả: {message}")

    def _process_download_queue(self):
        if self._shutdown_in_progress:
            return
        running_threads_count = sum(1 for info in self.active_threads.values() if info.get("status") in ["starting", "downloading"])
        queued_tasks = [(task_id, task_info) for task_id, task_info in self.active_threads.items() if task_info["status"] == "queued"]
        # Support new proxy_mode setting with backward compat
        proxy_mode = self.settings.get("proxy_mode", "")
        if not proxy_mode:
            proxy_mode = "m2proxy" if self.settings.get("use_proxy", False) else "none"
        proxy_required = proxy_mode != "none"
        if proxy_mode == "warp":
            warp_port = self.settings.get("warp_port", 40000)
            active_proxy_url = f"socks5://127.0.0.1:{warp_port}"
        else:
            active_proxy_url = _normalize_proxy_url(self.proxy_manager.get_proxy_url()) if self.proxy_manager else None  # [ZERO-LEAK-FIX]

        for task_id, task_info in queued_tasks:
            if running_threads_count >= self.max_concurrent_downloads:
                self.log_to_gui(f"Đạt giới hạn ({self.max_concurrent_downloads}) luồng tải. Task {task_id} sẽ chờ.")
                break

            task_type = task_info.get("task_type", "youtube_video")
            entity_id_val = task_info.get("entity_id") # Là video_id, playlist_id, channel_id, hoặc drive_file_id
            row_index = self._find_row_for_task_id(task_id)

            # Only YouTube tasks require a ready proxy when the user enables it
            if task_type.startswith("youtube") and proxy_required and not active_proxy_url:
                self.log_to_gui(f"Tác vụ {task_id} cần proxy nhưng proxy chưa sẵn sàng. Giữ trong hàng chờ để tránh lộ IP thật.")
                continue

            if task_type == "drive_folder":
                if row_index is not None:
                    self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_PROXY_STATUS), "Direct")
                if not self.drive_service:
                    self.log_to_gui(f"Task lấy danh sách thư mục Drive {task_id} cần service, đang đảm bảo service...")
                    self._ensure_drive_service(callback_on_success=self._process_download_queue)
                    return # Thoát, chờ auth xong
                else:
                    self.log_to_gui(f"Chuẩn bị khởi chạy luồng lấy danh sách file cho thư mục {task_id} (ID: {entity_id_val}).")
                    task_info["status"] = "starting"
                    thread = QThread(self)
                    # Sử dụng worker mới: DriveFolderItemFetcher
                    worker = DriveFolderItemFetcher(task_id, entity_id_val, self.drive_service)
                    worker.moveToThread(thread)
                    worker.log_message.connect(self._on_task_log_message)
                    worker.finished_fetching.connect(self._on_drive_folder_items_retrieved)
                    worker.error_fetching.connect(self._on_drive_folder_fetch_error)
                    thread.started.connect(worker.run)
                    self._track_thread(
                        thread,
                        worker,
                        completion_signals=(worker.finished_fetching, worker.error_fetching),
                    )
                    task_info["thread"] = thread
                    task_info["worker"] = worker
                    thread.start()
                    running_threads_count += 1

            elif task_type == "drive":
                if row_index is not None:
                    self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_PROXY_STATUS), "Direct")
                if not self.drive_service: # Nếu service chưa có, thử đảm bảo rồi mới bắt đầu task
                    self.log_to_gui(f"Task Drive {task_id} cần service, đang đảm bảo service...")
                    # Gọi _ensure_drive_service. _process_download_queue sẽ được gọi lại từ callback nếu auth thành công.
                    # Không tăng running_threads_count ở đây, vì task chưa thực sự chạy.
                    # Ta chỉ cần break vòng lặp này, chờ auth xong.
                    # Nếu auth đang chạy, _ensure_drive_service sẽ return False và không làm gì.
                    # Nếu auth chưa chạy, nó sẽ khởi động auth.
                    self._ensure_drive_service(callback_on_success=self._process_download_queue)
                    return # Thoát khỏi _process_download_queue hiện tại, chờ auth
                else: # Drive service đã sẵn sàng, tiến hành tạo worker
                    self.log_to_gui(f"Chuẩn bị khởi chạy luồng Drive cho tác vụ {task_id} (ID: {entity_id_val}).")
                    task_info["status"] = "starting"
                    thread = QThread(self)
                    worker = DriveDownloadWorker(task_id, entity_id_val, self.current_download_dir, self.drive_service)
                    # (Kết nối signals cho DriveDownloadWorker tương tự DownloadWorker)
                    worker.moveToThread(thread)
                    worker.started_processing.connect(self._on_worker_started)
                    worker.metadata_retrieved.connect(self._on_metadata_retrieved)
                    worker.progress_update.connect(self._on_progress_update)
                    worker.log_message.connect(self._on_task_log_message)
                    worker.task_finished.connect(self._on_task_finished)
                    thread.started.connect(worker.run)
                    self._track_thread(
                        thread,
                        worker,
                        completion_signals=(worker.task_finished,),
                    )
                    task_info["thread"] = thread
                    task_info["worker"] = worker
                    thread.start()
                    running_threads_count += 1

            elif task_type == "youtube_playlist_or_channel": # <<< KHỐI MỚI
                self.log_to_gui(f"Chuẩn bị khởi chạy luồng lấy danh sách video cho tác vụ {task_id}...")
                task_info["status"] = "starting" # Cập nhật trạng thái

                thread = QThread(self)
                proxy_url_to_use = active_proxy_url if proxy_required else None
                actual_status = "Proxy" if proxy_url_to_use else "Direct"
                if row_index is not None:
                    self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_PROXY_STATUS), actual_status)

                # Sử dụng worker mới đã tạo ở Bước 1
                worker = PlaylistFetchWorker(
                    task_id, 
                    task_info["url"], 
                    self.yt_dlp_path,
                    proxy_url=proxy_url_to_use
                )

                worker.moveToThread(thread)

                # Kết nối các tín hiệu của worker mới với các hàm xử lý trong MainWindow
                worker.finished_fetching.connect(self._on_playlist_items_retrieved)
                worker.error_fetching.connect(self._on_playlist_fetch_error)
                worker.log_message.connect(self._on_task_log_message)

                thread.started.connect(worker.run)
                self._track_thread(
                    thread,
                    worker,
                    completion_signals=(worker.finished_fetching, worker.error_fetching),
                )

                # Lưu trữ và bắt đầu thread
                task_info["thread"] = thread
                task_info["worker"] = worker
                thread.start()

                running_threads_count += 1

            elif task_type.startswith("youtube"): # youtube_video (chỉ xử lý video đơn)
                # Logic cho YouTube (DownloadWorker) giữ nguyên
                self.log_to_gui(f"Chuẩn bị khởi chạy luồng YouTube cho tác vụ {task_id} (URL: {task_info['url'][:50]}...).")
                task_info["status"] = "starting"
                thread = QThread(self)
                save_thumb_with_video_setting = self.settings.get("save_thumbnail_with_video", False)
                use_aria2c_setting = self.settings.get("use_aria2c", False)
                aria2c_args_text_setting = self.settings.get("aria2c_args", "-j 8 -x 8 -s 8 -k 1M")
                concurrent_fragments_setting = self.settings.get("concurrent_fragments", 4)
                
                # << ĐỌC CÀI ĐẶT COOKIES TỪ SETTINGS >>
                use_cookies_setting = self.settings.get("use_cookies", False)
                cookies_file_path_setting = self.settings.get("cookies_file_path", "")
                cookies_from_browser_setting = self.settings.get("cookies_from_browser", "")
                # Nếu đã trích xuất cookie qua CDP, dùng file đó thay vì --cookies-from-browser
                extracted_path = self.settings.get("extracted_cookies_path", "")
                if extracted_path and os.path.isfile(extracted_path) and cookies_from_browser_setting:
                    use_cookies_setting = True
                    cookies_file_path_setting = extracted_path
                    cookies_from_browser_setting = ""
                clean_filenames_setting = self.settings.get("clean_filenames", False)

                proxy_url_to_use = active_proxy_url if proxy_required else None
                if proxy_url_to_use and proxy_mode == "warp":
                    actual_status = "WARP"
                elif proxy_url_to_use:
                    actual_status = "Proxy"
                else:
                    actual_status = "Direct"
                if row_index is not None:
                    self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_PROXY_STATUS), actual_status)
                worker = DownloadWorker(task_id, task_info["url"], task_info["quality_format"],
                                        self.current_download_dir, self.yt_dlp_path,
                                        save_thumb_with_video_setting,
                                        use_aria2c_setting,
                                        aria2c_args_text_setting,
                                        concurrent_fragments_setting,
                                        use_cookies_setting,
                                        cookies_file_path_setting,
                                        clean_filenames_setting,
                                        proxy_url_to_use,
                                        self.settings.get("preferred_audio_format", "m4a"),
                                        cookies_from_browser_setting)
                worker.moveToThread(thread)
                worker.started_processing.connect(self._on_worker_started)
                worker.thumbnail_ready.connect(self._on_thumbnail_ready)
                worker.expected_duration_ready.connect(self._on_expected_duration_ready)
                worker.metadata_retrieved.connect(self._on_metadata_retrieved)
                worker.progress_update.connect(self._on_progress_update)
                worker.log_message.connect(self._on_task_log_message)
                worker.task_finished.connect(self._on_task_finished)
                thread.started.connect(worker.run)
                self._track_thread(
                    thread,
                    worker,
                    completion_signals=(worker.task_finished,),
                )
                task_info["thread"] = thread
                task_info["worker"] = worker
                thread.start()
                running_threads_count += 1
            else:
                self.log_to_gui(f"CẢNH BÁO: Loại tác vụ không xác định '{task_type}' cho task {task_id}. Bỏ qua.")
                task_info["status"] = "failed_unknown_type" # Đánh dấu lỗi

    
    @Slot(str)
    def _on_worker_started(self, task_id):
        row_index = self._find_row_for_task_id(task_id)
        if row_index is not None:
            self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_STATUS_TEXT), "Đang tải...")
            self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_TIMESTAMP), datetime.now().isoformat())
            self._save_download_history() 

    @Slot(str, str)
    def _on_expected_duration_ready(self, task_id: str, duration_hhmmss: str):
        row_index = self._find_row_for_task_id(task_id)
        if row_index is not None:
            self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_EXPECTED_DURATION), duration_hhmmss)
            # Hiển thị ngay cho người dùng đối chiếu
            self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_DURATION), duration_hhmmss)


    @Slot(str, str)
    def _on_task_log_message(self, task_id, message):
        if "DEBUG:" in message or "Lỗi" in message or "STDERR:" in message or "Lệnh:" in message or "Bắt đầu tải:" in message:
            self.log_to_gui(f"[{task_id.split('_')[-1]}]: {message}")


    def _find_row_for_task_id(self, task_id_to_find):
        for row in range(self.download_tasks_model.rowCount()): 
            task_id_item = self.download_tasks_model.item(row, COL_TASK_ID)
            if task_id_item and task_id_item.text() == task_id_to_find: return row
        return None

    def _show_table_context_menu(self, position: QPoint):
        indexes = self.downloads_table_view.selectionModel().selectedRows()
        if not indexes: return
        proxy_index = indexes[0]; source_index_obj = self.sort_filter_proxy_model.mapToSource(proxy_index)
        selected_row_in_source_model = source_index_obj.row()

        task_id = self.download_tasks_model.data(self.download_tasks_model.index(selected_row_in_source_model, COL_TASK_ID))
        file_path = self.download_tasks_model.data(self.download_tasks_model.index(selected_row_in_source_model, COL_FILE_PATH))
        error_details = self.download_tasks_model.data(self.download_tasks_model.index(selected_row_in_source_model, COL_ERROR_DETAILS))
        verification_status_text = self.download_tasks_model.data(self.download_tasks_model.index(selected_row_in_source_model, COL_VERIFICATION_STATUS)) or ""
        url = self.download_tasks_model.data(self.download_tasks_model.index(selected_row_in_source_model, COL_URL))
        quality_label = self.download_tasks_model.data(self.download_tasks_model.index(selected_row_in_source_model, COL_QUALITY_REQUESTED))
        current_status_text = self.download_tasks_model.data(self.download_tasks_model.index(selected_row_in_source_model, COL_STATUS_TEXT))

        task_type_from_model = ""
        title_for_context = self.download_tasks_model.data(self.download_tasks_model.index(selected_row_in_source_model, COL_TITLE)) or ""

        # Ưu tiên nhận diện dựa vào thông tin đã có (tiêu đề) để phân biệt file và folder Drive
        if title_for_context.startswith("Thư mục Drive:"):
            task_type_from_model = "drive_folder"
        elif title_for_context.startswith("Drive ID:") or "drive.google.com/file" in (url or ""):
            task_type_from_model = "drive"
        elif "youtube.com" in (url or "") or "youtu.be" in (url or ""):
             # Logic cũ cho YouTube vẫn tốt
             url_type_ctx, _, _ = url_handler.get_url_type_and_id(url)
             if url_type_ctx == url_handler.URL_TYPE_PLAYLIST or url_type_ctx == url_handler.URL_TYPE_CHANNEL:
                 task_type_from_model = "youtube_playlist_or_channel"
             else:
                 task_type_from_model = "youtube_video"
        else:
             # Fallback cho các trường hợp khác (ví dụ: pseudo URL gdrive://)
             entity_id_ctx = self.download_tasks_model.data(self.download_tasks_model.index(selected_row_in_source_model, COL_ENTITY_ID)) or ""
             if entity_id_ctx:
                 # Nếu có entity_id, có khả năng cao đây là một file Drive được thêm từ một thư mục
                 task_type_from_model = "drive"
             else:
                task_type_from_model = "unknown"

        context_menu = QMenu(self)
        if url: # Chỉ hiện tải lại nếu có URL
            old_title_val = self.download_tasks_model.data(self.download_tasks_model.index(selected_row_in_source_model, COL_TITLE))

            can_redownload = True
            if task_id and task_id in self.active_threads:
                if self.active_threads[task_id].get("status") in ["downloading", "starting", "queued"]:
                    can_redownload = False

            if can_redownload:
                redownload_action = QAction(QIcon.fromTheme("document-revert", self.style().standardIcon(QStyle.SP_BrowserReload)), "Tải lại mục này", self)
                redownload_action.triggered.connect(
                    lambda checked=False, r_idx=selected_row_in_source_model, t_id_ctx=task_id, u_ctx=url, q_lbl_ctx=quality_label, old_title_ctx=old_title_val, task_type_for_redownload=task_type_from_model :
                    self._handle_redownload_task(r_idx, t_id_ctx, u_ctx, q_lbl_ctx, old_title_ctx, task_type_for_redownload)
                )
                context_menu.addAction(redownload_action)
                context_menu.addSeparator()

        if task_id and task_id in self.active_threads:
            task_info = self.active_threads[task_id]
            if task_info.get("status") in ["queued", "starting", "downloading"]:
                cancel_action = QAction(QIcon.fromTheme("process-stop", self.style().standardIcon(QStyle.SP_DialogCancelButton)), "Hủy tải", self)
                cancel_action.triggered.connect(lambda checked=False, t=task_id: self._cancel_specific_task(t))
                context_menu.addAction(cancel_action)

        if task_id and task_id in self.active_verification_threads:
            if self.active_verification_threads[task_id]["thread"].isRunning():
                cancel_verify_action = QAction(QIcon.fromTheme("process-stop", self.style().standardIcon(QStyle.SP_DialogCancelButton)), "Hủy xác minh", self)
                cancel_verify_action.triggered.connect(lambda checked=False, t=task_id: self._cancel_specific_verification(t))
                context_menu.addAction(cancel_verify_action)

        if error_details:
            view_error_action = QAction(QIcon.fromTheme("dialog-error", self.style().standardIcon(QStyle.SP_MessageBoxCritical)), "Xem chi tiết lỗi tải", self)
            view_error_action.triggered.connect(lambda checked=False, t_id=task_id, err=error_details: self._show_error_detail_dialog(t_id, err))
            context_menu.addAction(view_error_action)

        if file_path and os.path.exists(file_path) and ("Lỗi" in verification_status_text or "N/A" in verification_status_text or "Chờ xác minh" in verification_status_text or "Đang kiểm tra..." in verification_status_text or "Không xác minh" in verification_status_text) and self.ffprobe_path and video_verifier: #
            retry_verify_action = QAction(QIcon.fromTheme("view-refresh", self.style().standardIcon(QStyle.SP_BrowserReload)), "Thử lại xác minh", self)
            retry_verify_action.triggered.connect(lambda checked=False, f=file_path, t=task_id: self._start_video_verification(t,f))
            context_menu.addAction(retry_verify_action)

        if file_path and os.path.exists(file_path):
            open_folder_action = QAction(QIcon.fromTheme("folder-open", self.style().standardIcon(QStyle.SP_DirIcon)), "Mở thư mục chứa file", self)
            open_folder_action.triggered.connect(lambda checked=False, f=file_path: self._open_containing_folder(f))
            context_menu.addAction(open_folder_action)

            play_action = QAction(QIcon.fromTheme("media-playback-start", self.style().standardIcon(QStyle.SP_MediaPlay)), "Phát file", self)
            play_action.triggered.connect(lambda checked=False, f=file_path: os.startfile(f) if platform.system() == "Windows" else subprocess.call(['open', f] if platform.system() == "Darwin" else ['xdg-open', f])) #
            context_menu.addAction(play_action)

            delete_file_action = QAction(QIcon.fromTheme("user-trash", self.style().standardIcon(QStyle.SP_TrashIcon)), "Xóa file gốc", self)
            delete_file_action.triggered.connect(self.delete_source_file)
            context_menu.addAction(delete_file_action)

        if url:
            open_browser_action = QAction(QIcon.fromTheme("internet-web-browser", self.style().standardIcon(QStyle.SP_ComputerIcon)), "Mở trong trình duyệt", self)
            open_browser_action.triggered.connect(lambda checked=False, u=url: __import__('webbrowser').open(u))
            context_menu.addAction(open_browser_action)

            copy_url_action = QAction(QIcon.fromTheme("edit-copy", self.style().standardIcon(QStyle.SP_FileDialogContentsView)), "Sao chép URL", self)
            copy_url_action.triggered.connect(lambda checked=False, u=url: QApplication.clipboard().setText(u))
            context_menu.addAction(copy_url_action)

        context_menu.addSeparator()
        remove_action = QAction(QIcon.fromTheme("edit-delete", self.style().standardIcon(QStyle.SP_DialogCloseButton)), "Xóa khỏi danh sách", self)
        remove_action.triggered.connect(lambda checked=False, r_idx=selected_row_in_source_model, t_id=task_id: self._remove_task_from_list(r_idx, t_id))
        context_menu.addAction(remove_action)

        if context_menu.actions(): context_menu.exec_(self.downloads_table_view.viewport().mapToGlobal(position))

    def delete_source_file(self):
        """Delete the physical file associated with the selected row, if safe."""
        indexes = self.downloads_table_view.selectionModel().selectedRows()
        if not indexes:
            return
        proxy_index = indexes[0]
        source_index = self.sort_filter_proxy_model.mapToSource(proxy_index)
        row_in_source = source_index.row()

        task_id = self.download_tasks_model.data(self.download_tasks_model.index(row_in_source, COL_TASK_ID))
        if task_id and task_id in self.active_threads:
            QMessageBox.warning(self, "Cảnh báo", "Không thể xóa file khi đang tải!")
            return

        file_path = self.download_tasks_model.data(self.download_tasks_model.index(row_in_source, COL_FILE_PATH))
        if not file_path:
            QMessageBox.warning(self, "Lỗi", "Không xác định được đường dẫn file.")
            return
        if not os.path.exists(file_path):
            QMessageBox.warning(self, "Lỗi", "File không tồn tại trên ổ cứng (có thể đã bị xóa hoặc di chuyển).")
            return

        reply = QMessageBox.question(
            self,
            "Xác nhận xóa",
            f"Bạn có chắc muốn xóa vĩnh viễn file này không?\n\n{os.path.basename(file_path)}",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No
        )
        if reply != QMessageBox.Yes:
            return

        try:
            os.remove(file_path)
            QMessageBox.information(self, "Thông báo", "Đã xóa file thành công!")
            self.download_tasks_model.setData(self.download_tasks_model.index(row_in_source, COL_STATUS_TEXT), "File gốc đã xóa")
            self.download_tasks_model.setData(self.download_tasks_model.index(row_in_source, COL_FILE_PATH), "")
            self._save_download_history()
        except Exception as e:
            QMessageBox.warning(self, "Lỗi", f"Không thể xóa file: {e}")

    def _show_error_detail_dialog(self, task_id, error_details):
        """Hiển thị dialog chi tiết lỗi với khả năng copy."""
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Chi tiết lỗi tải - {task_id}")
        dialog.setMinimumSize(550, 300)
        layout = QVBoxLayout(dialog)

        error_text = QTextEdit()
        error_text.setPlainText(error_details)
        error_text.setReadOnly(True)
        layout.addWidget(error_text)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        copy_btn = QPushButton("  Sao chép")
        copy_btn.setIcon(self.style().standardIcon(QStyle.SP_FileDialogContentsView))
        def _copy_error():
            QApplication.clipboard().setText(error_details)
            copy_btn.setText("  Đã sao chép ✓")
            QTimer.singleShot(2000, lambda: copy_btn.setText("  Sao chép"))
        copy_btn.clicked.connect(_copy_error)
        btn_layout.addWidget(copy_btn)

        close_btn = QPushButton("Đóng")
        close_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(close_btn)

        layout.addLayout(btn_layout)
        dialog.exec_()

    def _update_item_count_and_controls(self):
        """Cập nhật label đếm số mục và trạng thái của các control liên quan."""
        count = self.download_tasks_model.rowCount()
        self.item_count_label.setText(f"{count} mục")
        self.select_all_checkbox.setEnabled(count > 0)
        # Nếu không còn mục nào, bỏ chọn checkbox "Chọn tất cả" một cách an toàn
        if count == 0 and self.select_all_checkbox.isChecked():
            self.select_all_checkbox.blockSignals(True)
            self.select_all_checkbox.setChecked(False)
            self.select_all_checkbox.blockSignals(False)

    def _get_checked_rows(self):
        """Lấy danh sách các hàng đang được chọn bởi checkbox."""
        checked_rows = []
        for row in range(self.download_tasks_model.rowCount()):
            item = self.download_tasks_model.item(row, COL_CHECKBOX)
            if item and item.checkState() == Qt.Checked:
                checked_rows.append(row)
        return checked_rows

    @Slot(int)
    def _toggle_select_all(self, state):
        """Chọn hoặc bỏ chọn tất cả các mục trong bảng."""
        # Nếu không có mục nào, hiển thị thông báo và đặt lại checkbox
        if self.download_tasks_model.rowCount() == 0:
            if state == Qt.Checked:
                QMessageBox.information(self, "Không có mục nào", "Không có mục nào trong danh sách để chọn.")
                # Tự động bỏ chọn lại checkbox một cách an toàn
                self.select_all_checkbox.blockSignals(True)
                self.select_all_checkbox.setChecked(False)
                self.select_all_checkbox.blockSignals(False)
            return

        check_state = Qt.Checked if state == Qt.Checked else Qt.Unchecked
        self.download_tasks_model.blockSignals(True)
        for row in range(self.download_tasks_model.rowCount()):
            item = self.download_tasks_model.item(row, COL_CHECKBOX)
            if item:
                item.setCheckState(check_state)
        self.download_tasks_model.blockSignals(False)

        # Chỉ phát tín hiệu cập nhật nếu có hàng
        if self.download_tasks_model.rowCount() > 0:
            self.download_tasks_model.dataChanged.emit(
                self.download_tasks_model.index(0, COL_CHECKBOX),
                self.download_tasks_model.index(self.download_tasks_model.rowCount() - 1, COL_CHECKBOX)
            )

    @Slot()
    def _handle_redownload_selected(self):
        """Tải lại tất cả các tác vụ đã được chọn."""
        checked_rows = self._get_checked_rows()
        if not checked_rows:
            QMessageBox.information(self, "Chưa chọn mục", "Vui lòng chọn ít nhất một mục để tải lại.")
            return

        reply = QMessageBox.question(self, "Xác nhận Tải lại",
                                     f"Bạn có chắc muốn tải lại {len(checked_rows)} mục đã chọn không?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if reply == QMessageBox.Yes:
            # Lấy thông tin từ các hàng trước khi chúng có thể bị xóa
            tasks_to_redownload = []
            for row in checked_rows:
                task_id = self.download_tasks_model.data(self.download_tasks_model.index(row, COL_TASK_ID))
                # Các thông tin khác để truyền cho _handle_redownload_task
                url = self.download_tasks_model.data(self.download_tasks_model.index(row, COL_URL))
                quality_label = self.download_tasks_model.data(self.download_tasks_model.index(row, COL_QUALITY_REQUESTED))
                old_title = self.download_tasks_model.data(self.download_tasks_model.index(row, COL_TITLE))
                title_for_context = old_title or ""
                task_type = "unknown"
                if title_for_context.startswith("Thư mục Drive:"): task_type = "drive_folder"
                elif title_for_context.startswith("Drive ID:"): task_type = "drive"
                else: task_type = "youtube_video"

                tasks_to_redownload.append({
                    "row": row, "task_id": task_id, "url": url, 
                    "quality_label": quality_label, "old_title": old_title, "task_type": task_type
                })
            
            for task in tasks_to_redownload:
                 self._handle_redownload_task(task["row"], task["task_id"], task["url"], 
                                              task["quality_label"], task["old_title"], task["task_type"])

    @Slot()
    def _handle_redownload_failed_items(self):
        """Finds and re-downloads all tasks that have a failed or unverified status."""
        tasks_to_reload = []
        # Define keywords for failed/unverified statuses
        failed_status_keywords = ["lỗi", "thất bại", "failed", "đã hủy"]
        unverified_status_keywords = ["lỗi x.minh", "không xác minh"]

        for row in range(self.download_tasks_model.rowCount()):
            status = self.download_tasks_model.data(self.download_tasks_model.index(row, COL_STATUS_TEXT), Qt.DisplayRole).lower()
            verification_status = self.download_tasks_model.data(self.download_tasks_model.index(row, COL_VERIFICATION_STATUS), Qt.DisplayRole).lower()
            task_id = self.download_tasks_model.data(self.download_tasks_model.index(row, COL_TASK_ID))

            # Skip currently active tasks to prevent conflicts
            if task_id and task_id in self.active_threads:
                if self.active_threads[task_id].get("status") in ["downloading", "starting", "queued"]:
                    continue
            
            # Check for failure conditions
            is_failed = any(keyword in status for keyword in failed_status_keywords)
            is_unverified = any(keyword in verification_status for keyword in unverified_status_keywords)

            if is_failed or is_unverified:
                # Gather all necessary info for reloading
                url = self.download_tasks_model.data(self.download_tasks_model.index(row, COL_URL))
                if not url: # Cannot reload without a URL
                    continue

                quality_label = self.download_tasks_model.data(self.download_tasks_model.index(row, COL_QUALITY_REQUESTED))
                old_title = self.download_tasks_model.data(self.download_tasks_model.index(row, COL_TITLE)) or ""
                
                # Determine task_type (copied logic from context menu)
                task_type = "unknown"
                if old_title.startswith("Thư mục Drive:"): task_type = "drive_folder"
                elif old_title.startswith("Drive ID:"): task_type = "drive"
                else: task_type = "youtube_video"

                tasks_to_reload.append({
                    "row": row, "task_id": task_id, "url": url, 
                    "quality_label": quality_label, "old_title": old_title, "task_type": task_type
                })

        if not tasks_to_reload:
            QMessageBox.information(self, "Không có mục nào", "Không tìm thấy mục nào bị lỗi hoặc chưa được xác minh để tải lại.")
            return

        reply = QMessageBox.question(self, "Xác nhận Tải lại",
                                     f"Tìm thấy {len(tasks_to_reload)} mục bị lỗi hoặc chưa xác minh.\n"
                                     f"Bạn có muốn tải lại tất cả chúng không?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if reply == QMessageBox.Yes:
            self.log_to_gui(f"Bắt đầu tải lại {len(tasks_to_reload)} mục bị lỗi/chưa xác minh...")
            # Sort by row in reverse order to avoid index issues when removing items from the model
            sorted_tasks = sorted(tasks_to_reload, key=lambda x: x['row'], reverse=True)
            
            for task in sorted_tasks:
                 self._handle_redownload_task(task["row"], task["task_id"], task["url"], task["quality_label"], task["old_title"], task["task_type"])

    @Slot()
    def _handle_cancel_selected(self):
        """Hủy tất cả các tác vụ đang chạy đã được chọn."""
        checked_rows = self._get_checked_rows()
        if not checked_rows: return
        
        cancelled_count = 0
        for row in checked_rows:
            task_id = self.download_tasks_model.data(self.download_tasks_model.index(row, COL_TASK_ID))
            if task_id in self.active_threads:
                self._cancel_specific_task(task_id)
                cancelled_count += 1
        self.log_to_gui(f"Đã gửi yêu cầu hủy cho {cancelled_count} tác vụ.")
    
    @Slot()
    def _handle_remove_selected(self):
        """Xóa tất cả các mục đã chọn khỏi danh sách."""
        checked_rows = self._get_checked_rows()
        if not checked_rows:
            QMessageBox.information(self, "Chưa chọn mục", "Vui lòng chọn ít nhất một mục để xóa.")
            return

        reply = QMessageBox.question(self, "Xác nhận Xóa",
                                     f"Bạn có chắc muốn xóa {len(checked_rows)} mục đã chọn khỏi danh sách không?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
        if reply == QMessageBox.Yes:
            # Sắp xếp các hàng theo thứ tự giảm dần để tránh lỗi chỉ số khi xóa
            checked_rows.sort(reverse=True)
            for row in checked_rows:
                task_id = self.download_tasks_model.data(self.download_tasks_model.index(row, COL_TASK_ID))
                self._remove_task_from_list(row, task_id, silent=True)
            self.log_to_gui(f"Đã xóa {len(checked_rows)} mục khỏi danh sách.")
            self._save_download_history() # Lưu lại lịch sử sau khi xóa hàng loạt


    @Slot(int, str, str, str, str, str)
    def _handle_redownload_task(self, row_in_source_model, task_id, url, quality_label, old_title, task_type_for_redownload):
        self.log_to_gui(f"Yêu cầu tải lại cho mục (ID cũ: {task_id}, URL: {url}) tại hàng {row_in_source_model}")

        # Kiểm tra xem tác vụ có đang hoạt động không. Nếu có, ngăn chặn việc tải lại.
        if task_id and task_id in self.active_threads:
            if self.active_threads[task_id].get("status") in ["downloading", "starting", "queued"]:
                QMessageBox.warning(self, "Đang xử lý", f"Tác vụ '{old_title}' (ID: {task_id}) đang được xử lý. Không thể tải lại ngay.")
                return

        # Xác minh chỉ số hàng được cung cấp là hợp lệ và khớp với task_id
        if row_in_source_model is None or not (0 <= row_in_source_model < self.download_tasks_model.rowCount()):
            self.log_to_gui(f"Cảnh báo: Hàng {row_in_source_model} không hợp lệ. Thử tìm lại bằng task_id...")
            row_in_source_model = self._find_row_for_task_id(task_id) # Tìm lại hàng phòng trường hợp filter/sort
            if row_in_source_model is None:
                self.log_to_gui(f"Lỗi: Không tìm thấy hàng nào cho task_id {task_id} để tải lại.")
                QMessageBox.critical(self, "Lỗi Tải Lại", f"Không tìm thấy tác vụ '{old_title}' để tải lại.")
                return

        # --- LOGIC MỚI: Reset và tái sử dụng hàng hiện có ---
        
        # 1. Tạo một task_id mới để quản lý lần tải lại này một cách sạch sẽ
        self.next_task_id_counter += 1
        new_task_id = f"task_{time.strftime('%H%M%S')}_{self.next_task_id_counter}"

        # 2. Lấy thông tin cần thiết từ hàng
        model = self.download_tasks_model
        entity_id = model.data(model.index(row_in_source_model, COL_ENTITY_ID))
        quality_format = self.quality_options_map.get(quality_label, "bv*+ba/b")

        # 3. Reset dữ liệu trong model cho hàng hiện có
        model.setData(model.index(row_in_source_model, COL_TASK_ID), new_task_id)
        model.setData(model.index(row_in_source_model, COL_STATUS_TEXT), "Đang chờ...")
        model.setData(model.index(row_in_source_model, COL_VERIFICATION_STATUS), "Chờ xác minh" if task_type_for_redownload.startswith("youtube") else "N/A (Drive)")
        model.setData(model.index(row_in_source_model, COL_PROGRESS), "0")
        model.setData(model.index(row_in_source_model, COL_SPEED_ETA), "- | ETA: -")
        model.setData(model.index(row_in_source_model, COL_FILE_PATH), "")
        model.setData(model.index(row_in_source_model, COL_ERROR_DETAILS), "")
        
        current_timestamp_iso = datetime.now().isoformat()
        model.setData(model.index(row_in_source_model, COL_TIMESTAMP), current_timestamp_iso)
        dt_obj = datetime.fromisoformat(current_timestamp_iso)
        model.setData(model.index(row_in_source_model, COL_TIMESTAMP), dt_obj, Qt.InitialSortOrderRole)

        # 4. Thêm tác vụ với ID MỚI vào hàng đợi active_threads
        self.active_threads[new_task_id] = {
            "url": url, "quality_label": quality_label, "quality_format": quality_format,
            "status": "queued", "row": row_in_source_model, "verification_status": "pending",
            "task_type": task_type_for_redownload, "entity_id": entity_id
        }
        
        self.log_to_gui(f"Đã reset và đưa tác vụ tại hàng {row_in_source_model} (ID mới: {new_task_id}) vào hàng đợi.")

        # 5. Kích hoạt xử lý hàng đợi
        if task_type_for_redownload == "drive":
            self._ensure_drive_service(callback_on_success=self._process_download_queue)
        else:
            self._process_download_queue()
        
        # 6. Lưu lại lịch sử sau khi cập nhật
        self._save_download_history()

    def _cancel_specific_task(self, task_id):
        self.log_to_gui(f"Yêu cầu hủy tác vụ tải: {task_id}")
        if task_id in self.active_threads:
            task_info = self.active_threads[task_id]
            worker = task_info.get("worker")
            if worker : worker.stop()
            row_index = self._find_row_for_task_id(task_id)
            if row_index is not None: self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_STATUS_TEXT), "Đang hủy...")


    def _cancel_specific_verification(self, task_id: str):
        self.log_to_gui(f"Yêu cầu hủy xác minh cho tác vụ: {task_id}")
        if task_id in self.active_verification_threads:
            verify_info = self.active_verification_threads.pop(task_id, None) 
            if verify_info:
                worker = verify_info.get("worker"); thread_instance = verify_info.get("thread")
                if worker: worker.stop()
                if thread_instance and thread_instance.isRunning(): thread_instance.quit()

            row_index = self._find_row_for_task_id(task_id)
            if row_index is not None:
                item = self.download_tasks_model.item(row_index, COL_VERIFICATION_STATUS)
                if item: item.setText("Hủy xác minh")
                self.download_tasks_model.setData(self.download_tasks_model.index(row_index, COL_TIMESTAMP), datetime.now().isoformat())
            self._save_download_history()


    def _open_containing_folder(self, file_path):
        if not file_path or not os.path.exists(file_path):
            self.log_to_gui(f"Lỗi: File không tồn tại '{file_path}'")
            return

        folder_path = os.path.dirname(file_path)
        
        # [FIX-DOUBLE-OPEN] Kiểm tra ký tự đặc biệt gây lỗi cho explorer /select
        # Ký tự '｜' khiến explorer trả về lỗi 1 nhưng vẫn mở window -> gây hiện tượng mở 2 lần khi fallback chạy.
        # Nếu gặp ký tự này, ta dùng os.startfile ngay lập tức để chỉ mở thư mục.
        is_complex_path = "｜" in file_path
        
        if platform.system() == "Windows" and is_complex_path:
            try:
                os.startfile(folder_path)
                # self.log_to_gui(f"Đã mở thư mục (Direct mode): {folder_path}")
            except Exception as e:
                self.log_to_gui(f"Lỗi mở thư mục (Direct mode): {e}")
            return

        try:
            if platform.system() == "Windows":
                # Logic cũ: cố gắng bôi đen file
                subprocess.run(['explorer', '/select,', os.path.normpath(file_path)], check=True)
            elif platform.system() == "Darwin":
                subprocess.run(['open', '-R', os.path.normpath(file_path)], check=True)
            else:
                subprocess.run(['xdg-open', os.path.normpath(os.path.dirname(file_path))], check=True)
        except Exception as e:
            self.log_to_gui(f"Lỗi mở thư mục: {e}. Thử mở thư mục chứa...")
            try:
                system = platform.system()
                dir_path = os.path.normpath(folder_path)
                if system == "Windows" and hasattr(os, "startfile"):
                    os.startfile(dir_path)
                elif system == "Darwin":
                    subprocess.run(['open', dir_path])
                else:
                    subprocess.run(['xdg-open', dir_path])
            except Exception as e_fallback:
                self.log_to_gui(f"Lỗi fallback mở thư mục: {e_fallback}")

    def _remove_task_from_list(self, row_in_source_model, task_id, silent=False):
        if not silent:
            self.log_to_gui(f"Yêu cầu xóa tác vụ {task_id} (hàng: {row_in_source_model}) khỏi danh sách.")
        
        if not (0 <= row_in_source_model < self.download_tasks_model.rowCount()):
            if not silent: self.log_to_gui(f"CẢNH BÁO: Hàng {row_in_source_model} không hợp lệ để xóa.")
            found_row = self._find_row_for_task_id(task_id)
            if found_row is None:
                if not silent: self.log_to_gui(f"CẢNH BÁO: Không tìm thấy task_id {task_id} trong model để xóa.")
                return
            row_in_source_model = found_row


        current_task_id_in_row = self.download_tasks_model.data(self.download_tasks_model.index(row_in_source_model, COL_TASK_ID))
        if current_task_id_in_row != task_id:
            if not silent: self.log_to_gui(f"CẢNH BÁO: Task ID tại hàng {row_in_source_model} ({current_task_id_in_row}) không khớp với task ID cần xóa ({task_id}). Thử tìm lại.")
            actual_row_to_remove = self._find_row_for_task_id(task_id)
            if actual_row_to_remove is None:
                if not silent: self.log_to_gui(f"CẢNH BÁO: Không tìm thấy hàng cho task_id {task_id} để xóa sau khi kiểm tra lại.")
                return 
            row_in_source_model = actual_row_to_remove 


        if task_id: 
            task_info_dl = self.active_threads.pop(task_id, None)
            if task_info_dl:
                worker = task_info_dl.get("worker"); thread_instance = task_info_dl.get("thread")
                if worker: worker.stop()
                if thread_instance and thread_instance.isRunning(): thread_instance.quit()
                if not silent: self.log_to_gui(f"Đã dừng (nếu cần) luồng tải cho {task_id}.")

            self._cancel_specific_verification(task_id) 

            thumb_fetch_info = self.active_thumbnail_fetchers.pop(task_id, None)
            if thumb_fetch_info:
                worker = thumb_fetch_info.get("worker"); thread_instance = thumb_fetch_info.get("thread")
                if worker: worker.deleteLater() 
                if thread_instance and thread_instance.isRunning(): thread_instance.quit()
                if not silent: self.log_to_gui(f"Đã dừng (nếu cần) luồng thumbnail cho {task_id}.")
        
        self.download_tasks_model.removeRow(row_in_source_model)
        if not silent: self.log_to_gui(f"Đã xóa hàng {row_in_source_model} (task_id: {task_id}) khỏi model.")

        self._update_item_count_and_controls()
        self._save_download_history()
        self._process_download_queue()


    def on_filter_button_clicked(self):
        sender = self.sender(); filter_text_orig = sender.text().lower()
        filter_key = filter_text_orig.replace(" ", "_")

        for btn_name_key, btn_widget in self.filter_button_group.items():
            if btn_widget != sender: btn_widget.setChecked(False)
        sender.setChecked(True)

        self.sort_filter_proxy_model.setFilterKeyColumn(-1) 
        self.sort_filter_proxy_model.setFilterCaseSensitivity(Qt.CaseInsensitive)


        if filter_key == "tất_cả": self.sort_filter_proxy_model.setFilterRegularExpression("")
        elif filter_key == "đang_tải":
            self.sort_filter_proxy_model.setFilterKeyColumn(COL_STATUS_TEXT)
            self.sort_filter_proxy_model.setFilterRegularExpression(r"Đang tải...|Đang chờ...|Đang hủy...|Đang kiểm tra...")
        elif filter_key == "hoàn_thành":
            self.sort_filter_proxy_model.setFilterKeyColumn(COL_STATUS_TEXT)
            self.sort_filter_proxy_model.setFilterRegularExpression(r"Hoàn thành!")
        elif filter_key == "bị_lỗi":
            self.sort_filter_proxy_model.setFilterKeyColumn(COL_STATUS_TEXT)
            self.sort_filter_proxy_model.setFilterRegularExpression(r"Lỗi \(mã|Thất bại|Lỗi file sau tải|Lỗi worker|Lỗi \(không rõ file\)|Lỗi yt-dlp")
        elif filter_key == "đã_xác_minh":
            self.sort_filter_proxy_model.setFilterKeyColumn(COL_VERIFICATION_STATUS)
            self.sort_filter_proxy_model.setFilterRegularExpression(r"^OK")
        elif filter_key == "lỗi_xác_minh":
            self.sort_filter_proxy_model.setFilterKeyColumn(COL_VERIFICATION_STATUS)
            self.sort_filter_proxy_model.setFilterRegularExpression(r"Lỗi X.Minh|File trống\?|Lỗi đường dẫn file")
        elif filter_key == "file_đã_xóa": 
            self.sort_filter_proxy_model.setFilterKeyColumn(COL_STATUS_TEXT)
            self.sort_filter_proxy_model.setFilterRegularExpression(r"File gốc đã xóa")
        elif filter_key == "video":
            self.sort_filter_proxy_model.setFilterKeyColumn(COL_QUALITY_REQUESTED)
            self.sort_filter_proxy_model.setFilterRegularExpression(r"p \(MP4\)|Tốt nhất \(MP4\)")
        elif filter_key == "audio":
            self.sort_filter_proxy_model.setFilterKeyColumn(COL_QUALITY_REQUESTED)
            self.sort_filter_proxy_model.setFilterRegularExpression(r"Audio \(M4A\)")
        else: 
            self.sort_filter_proxy_model.setFilterRegularExpression(f".*{sender.text()}.*")


    def _load_initial_settings_to_ui(self):
        #self.save_thumbnail_with_video_checkbox.setChecked(self.settings.get("save_thumbnail_with_video", False))
        #self.use_cookies_for_info_checkbox.setChecked(self.settings.get("use_cookies_for_info_fetcher", True)) # Giữ lại nếu checkbox này vẫn trên toolbar

        last_quality_label = self.settings.get("last_quality_preference_label", "1080p (MP4)")
        if last_quality_label in self.quality_options_map:
            self.quality_main_combo.setCurrentText(last_quality_label)

        self._update_save_to_button_text()

        log_is_visible = self.system_log_widget.isVisible()
        self.toggle_log_action.setChecked(log_is_visible)
        self.hide_log_button.setChecked(log_is_visible)
        self.hide_log_button.setText("Ẩn" if log_is_visible else "Hiện")

        # Cập nhật giá trị self.max_concurrent_downloads từ settings
        self.max_concurrent_downloads = self.settings.get("max_concurrent_downloads", 2)
        # Các cài đặt khác như aria2c, concurrent_fragments sẽ được đọc từ self.settings
        # khi DownloadWorker hoặc InfoRetrieveWorker được tạo.
    def _initialize_yt_dlp_non_blocking(self):
        self.log_to_gui("Đang khởi tạo yt-dlp trong nền...")
        self.init_thread = QThread(self)
        # Only use M2Proxy for yt-dlp binary downloads (WARP not used here)
        proxy_mode = self.settings.get("proxy_mode", "")
        if not proxy_mode:
            proxy_mode = "m2proxy" if self.settings.get("use_proxy", False) else "none"
        proxy_url_for_init = _normalize_proxy_url(self.proxy_manager.get_proxy_url()) if (proxy_mode == "m2proxy" and self.proxy_manager) else None
        if proxy_mode == "m2proxy" and not proxy_url_for_init:
            self.log_to_gui("Proxy đang bật nhưng thiếu cấu hình, bỏ qua tải yt-dlp để tránh lộ IP.")
            return
        effective_proxy_for_init = proxy_url_for_init if proxy_mode == "m2proxy" else None
        self.initializer_worker = YTDLPInitializer(proxy_url=effective_proxy_for_init)
        self.initializer_worker.moveToThread(self.init_thread)
        self.initializer_worker.finished.connect(self._on_yt_dlp_initialized)
        self.init_thread.started.connect(self.initializer_worker.run)
        self._track_thread(
            self.init_thread,
            self.initializer_worker,
            completion_signals=(self.initializer_worker.finished,),
            cleanup_callback=lambda thread=self.init_thread: self._clear_managed_thread_refs(
                "init_thread", "initializer_worker", thread
            ),
        )
        self.init_thread.start()

    @Slot(str, str)
    def _on_yt_dlp_initialized(self, yt_dlp_path, messages):
        self.log_to_gui("--- Log khởi tạo yt-dlp ---\n" + messages + "\n--- Kết thúc log ---")
        if self._shutdown_in_progress:
            return
        if yt_dlp_path:
            self.yt_dlp_path = os.path.abspath(yt_dlp_path) # Đảm bảo đường dẫn luôn là tuyệt đối
            main_logic.YT_DLP_CMD_TO_USE = self.yt_dlp_path
            self.log_to_gui(f"Sẵn sàng sử dụng yt-dlp tại: {self.yt_dlp_path}")
            self.paste_link_action.setEnabled(True)

            # Lấy phiên bản ban đầu
            self.yt_dlp_version = main_logic.get_local_yt_dlp_version(self.yt_dlp_path) or "Không thể đọc"
            self.log_to_gui(f"Phiên bản yt-dlp hiện tại: {self.yt_dlp_version}")
            
            # Kiểm tra xem người dùng có muốn tự động cập nhật khi khởi động không
            if self.settings.get("auto_update_yt_dlp", False):
                self.log_to_gui("Bắt đầu kiểm tra cập nhật tự động cho yt-dlp (do cài đặt)...")
                self._start_yt_dlp_update(manual=False) # manual=False cho tự động
            else:
                self.log_to_gui("Bỏ qua kiểm tra cập nhật tự động (do cài đặt của người dùng).")

        else:
            QMessageBox.critical(self, "Lỗi yt-dlp", "Không thể tìm hoặc cài đặt yt-dlp. Xem log chi tiết.")
            self.paste_link_action.setEnabled(False)

    @Slot()
    def _select_download_directory(self):
        dir_path = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu video", self.current_download_dir)
        if dir_path:
            self.current_download_dir = dir_path
            self._update_save_to_button_text()
            self.settings["last_output_directory"] = self.current_download_dir
            main_logic.save_settings_to_file(self.settings, GUI_SETTINGS_FILE_PATH)
            self.log_to_gui(f"Đã chọn thư mục lưu: {self.current_download_dir}")

    def log_to_gui(self, message: str):
        if hasattr(self, 'general_log_area') and self.general_log_area:
            timestamp = time.strftime("[%H:%M:%S]")
            self.general_log_area.append(f"{timestamp} {message}"); self.general_log_area.ensureCursorVisible()
        else: print(f"[LOG_UI_EARLY]: {message}")

    def _apply_qss(self):
        qss = f"""
            QMainWindow, QDialog {{ background-color: {APP_THEME['app_bg']}; }}

            /* Toolbar - Màu đồng bộ với Selection */
            QToolBar {{
                background: {APP_THEME['toolbar_bg']};
                border-bottom: 1px solid {APP_THEME['toolbar_border']};
                padding: 4px;
                spacing: 10px;
            }}

            /* Toolbar buttons */
            QToolBar QToolButton, QToolBar QPushButton {{
                background: transparent;
                border: 1px solid transparent;
                border-radius: 4px;
                padding: 6px;
                color: {APP_THEME['text_white']};
                font-weight: bold;
            }}
            QToolBar QToolButton:hover, QToolBar QPushButton:hover {{
                background-color: {APP_THEME['toolbar_btn_hover']};
            }}
            QToolBar QToolButton:pressed, QToolBar QToolButton:checked,
            QToolBar QPushButton:pressed, QToolBar QPushButton:checked {{
                background-color: {APP_THEME['toolbar_btn_pressed']};
            }}

            /* Hide menu arrow */
            QToolBar QToolButton::menu-indicator {{
                image: none;
                width: 0px;
                border: none;
            }}

            /* ComboBox on toolbar */
            QToolBar QComboBox {{ padding: 3px 6px; }}

            /* Filter bar */
            #FilterBar {{ background-color: {APP_THEME['table_alt_bg']}; border-bottom: 1px solid {APP_THEME['table_grid']}; }}
            #FilterBar QPushButton {{
                min-width: 70px;
                padding: 6px 8px;
                border: 1px solid transparent;
                border-radius: 3px;
                background-color: transparent;
            }}
            #FilterBar QPushButton:hover {{
                background-color: {APP_THEME['table_grid']};
            }}
            #FilterBar QPushButton:checked, #FilterBar QPushButton:pressed {{
                background-color: {APP_THEME['table_header_border']};
                border: 1px solid {APP_THEME['table_selection_bg']};
                font-weight: bold;
                padding: 6px 8px;
            }}

            /* Tables */
            QTableView {{ background-color: {APP_THEME['table_bg']}; border: 1px solid {APP_THEME['table_header_border']}; gridline-color: {APP_THEME['table_grid']}; alternate-background-color: {APP_THEME['table_alt_bg']}; }}
            QTableView::item:selected {{ background-color: {APP_THEME['table_selection_bg']}; color: {APP_THEME['table_selection_text']}; }}

            /* Headers */
            QHeaderView::section {{
                background-color: {APP_THEME['table_header_bg']};
                padding: 4px 12px;
                border: 1px solid {APP_THEME['table_header_border']};
                font-weight: bold;
            }}
            QHeaderView::section:checked, QHeaderView::section:pressed {{
                background-color: {APP_THEME['table_header_border']};
                padding: 4px 12px;
            }}

            /* Progress bar */
            QProgressBar {{ border: 1px solid {APP_THEME['progress_border']}; border-radius: 3px; text-align: center; background-color: {APP_THEME['progress_bg']}; }}
            QProgressBar::chunk {{ background-color: {APP_THEME['progress_chunk']}; width: 1px; }}

            /* Text edits */
            QTextEdit {{ background-color: {APP_THEME['table_alt_bg']}; border: 1px solid {APP_THEME['table_header_bg']}; border-radius: 3px; font-family: Consolas, Courier New, monospace; font-size: 9pt; }}

            /* Menus */
            QMenu {{
                background: {APP_THEME['menu_bg']};
                border: 1px solid {APP_THEME['menu_border']};
            }}
            QMenu::item {{
                padding: 5px 20px;
                background: transparent;
            }}
            QMenu::item:selected {{
                background: {APP_THEME['menu_item_hover']};
                color: {APP_THEME['text_white']};
            }}
        """
        self.setStyleSheet(qss)

    def _save_shutdown_state_once(self):
        if self._shutdown_state_saved:
            return

        current_widths = {}
        header = self.downloads_table_view.horizontalHeader()
        for col in range(header.count()):
            current_widths[str(col)] = header.sectionSize(col)
        self.settings["table_column_widths"] = current_widths
        self._save_download_history()
        self.settings["max_concurrent_downloads"] = self.max_concurrent_downloads
        main_logic.save_settings_to_file(self.settings, GUI_SETTINGS_FILE_PATH)
        self._shutdown_state_saved = True
        self.log_to_gui("Đã lưu cài đặt và lịch sử.")

    def _finish_deferred_close(self):
        self._adopt_running_child_threads()
        if self._thread_registry.running_threads():
            self._shutdown_poll_timer.start(100)
            return

        self._allow_final_close = True
        self.close()

    def closeEvent(self, event):
        if self._allow_final_close:
            self._adopt_running_child_threads()
            if self._thread_registry.running_threads():
                self._allow_final_close = False
                event.ignore()
                self._shutdown_poll_timer.start(100)
                return
            super().closeEvent(event)
            return

        if self._shutdown_in_progress:
            event.ignore()
            return

        self.log_to_gui("Đang đóng ứng dụng...")
        active_download_or_verification = []
        for task_info in list(self.active_threads.values()):
            worker = task_info.get("worker")
            thread = task_info.get("thread")
            if worker and thread and thread.isRunning():
                active_download_or_verification.append(worker)
        for verify_info in list(self.active_verification_threads.values()):
            worker = verify_info.get("worker")
            thread = verify_info.get("thread")
            if worker and thread and thread.isRunning():
                active_download_or_verification.append(worker)

        if active_download_or_verification:
            reply = QMessageBox.question(
                self,
                "Xác nhận thoát",
                f"Có {len(active_download_or_verification)} tác vụ tải/xác minh đang chạy. "
                "Bạn có chắc muốn thoát?\n(Các tác vụ đang chạy sẽ được hủy an toàn.)",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply == QMessageBox.No:
                event.ignore()
                return

        self._shutdown_in_progress = True
        self._save_shutdown_state_once()
        self._request_thread_shutdown()

        if self._thread_registry.running_threads():
            self.log_to_gui("Đang chờ các tác vụ nền kết thúc an toàn...")
            event.ignore()
            self.setEnabled(False)
            self._shutdown_poll_timer.start(100)
            return

        self._allow_final_close = True
        super().closeEvent(event)


if __name__ == "__main__":
    if hasattr(Qt, 'AA_EnableHighDpiScaling'): QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    if hasattr(Qt, 'AA_UseHighDpiPixmaps'): QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    lock_file_path = QDir.tempPath() + '/yt_downloader_app.lock'
    lock_file = QLockFile(lock_file_path)
    lock_file.setStaleLockTime(0)
    if not lock_file.tryLock(100):
        QMessageBox.warning(None, "Ứng dụng đang chạy", "Ứng dụng đang chạy! Vui lòng kiểm tra thanh taskbar hoặc khay hệ thống.")
        sys.exit(1)
    app_font = QFont("Segoe UI", 10)
    app.setFont(app_font)
    main_window = MainWindow()
    main_window.show()
    sys.exit(app.exec_())
