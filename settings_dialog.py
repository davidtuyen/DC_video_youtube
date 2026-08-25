# settings_dialog.py - SettingsDialog extracted from ui_script.py
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QLabel, QComboBox, QProgressBar,
    QFileDialog, QMessageBox, QStyle,
    QSizePolicy, QCheckBox, QGridLayout,
    QDialog, QFormLayout, QSpinBox, QLineEdit, QDialogButtonBox, QGroupBox, QTabWidget,
)
from PyQt5.QtCore import (
    Qt, QThread, pyqtSignal as Signal, QObject, pyqtSlot as Slot,
    QTimer,
)
import json
import os
import platform
import subprocess
import urllib.request
import urllib.parse
from browser_cookie_profiles import (
    COOKIE_SOURCE_FILE,
    COOKIE_SOURCE_MANAGED,
    COOKIE_SOURCE_NONE,
    get_cookie_source_mode,
    set_cookie_source_mode,
)

# These will be set by ui_script after import
APP_THEME = {}
APP_VERSION = ""
SCRIPT_BASE_DIR_UI = ""
DATA_DIR_NAME = ""

def init_settings_config(theme, app_version, script_base_dir, data_dir_name):
    global APP_THEME, APP_VERSION, SCRIPT_BASE_DIR_UI, DATA_DIR_NAME
    APP_THEME = theme
    APP_VERSION = app_version
    SCRIPT_BASE_DIR_UI = script_base_dir
    DATA_DIR_NAME = data_dir_name

class SettingsDialog(QDialog):
    manual_update_requested = Signal()
    manual_app_update_requested = Signal()
    manual_change_ip_requested = Signal()  # Tín hiệu mới cho đổi IP

    def __init__(self, current_settings, parent=None, *, managed_chrome=None):
        super().__init__(parent)
        self.setWindowTitle("Cài đặt Chương trình")
        self.resize(500, 500)  # [FIX-FLICKER]

        self.settings = current_settings
        self.new_settings = current_settings.copy()
        self.managed_chrome = managed_chrome

        # Tạo QTabWidget làm layout trung tâm
        tab_widget = QTabWidget(self)
        main_layout = QVBoxLayout(self)  # Layout chính để chứa tab_widget và các nút OK/Cancel
        main_layout.addWidget(tab_widget)
        
        # Tạo các trang (Page) cho Tab
        general_settings_page = QWidget()
        proxy_settings_page = QWidget()
        cookies_settings_page = QWidget()
        
        # Tạo layout cho mỗi trang
        general_settings_layout = QVBoxLayout(general_settings_page)
        proxy_settings_layout = QVBoxLayout(proxy_settings_page)
        cookies_settings_layout = QVBoxLayout(cookies_settings_page)

        # --- Cài đặt Chung (giữ nguyên) ---
        general_group_box = QGroupBox("Cài đặt Chung")
        # ... (giữ nguyên code cho group box này) ...
        general_form_layout = QFormLayout()
        self.max_concurrent_downloads_spinbox = QSpinBox()
        self.max_concurrent_downloads_spinbox.setRange(1, 10)
        self.max_concurrent_downloads_spinbox.setValue(self.new_settings.get("max_concurrent_downloads", 2))
        general_form_layout.addRow("Số lượt tải đồng thời tối đa:", self.max_concurrent_downloads_spinbox)
        self.save_thumbnail_with_video_checkbox = QCheckBox("Lưu thumbnail chung với video tải về")
        self.save_thumbnail_with_video_checkbox.setChecked(self.new_settings.get("save_thumbnail_with_video", False))
        general_form_layout.addRow(self.save_thumbnail_with_video_checkbox)

        self.auto_deduplicate_checkbox = QCheckBox("Tự động tối ưu lịch sử tải về")
        self.auto_deduplicate_checkbox.setToolTip("Tự động lọc và xóa các URL trùng lặp khi khởi động ứng dụng.")
        self.auto_deduplicate_checkbox.setChecked(self.new_settings.get("auto_deduplicate_history", True))
        general_form_layout.addRow(self.auto_deduplicate_checkbox)

        self.clean_filenames_checkbox = QCheckBox("Làm Sạch Tên File (chỉ giữ ký tự ASCII an toàn)")
        self.clean_filenames_checkbox.setToolTip("Khi được chọn, tên file sẽ được giới hạn trong các ký tự ASCII, loại bỏ dấu và các ký tự đặc biệt để đảm bảo tương thích tối đa.")
        self.clean_filenames_checkbox.setChecked(self.new_settings.get("clean_filenames", False))
        general_form_layout.addRow(self.clean_filenames_checkbox)

        general_group_box.setLayout(general_form_layout)
        general_settings_layout.addWidget(general_group_box)

        # --- Cài đặt Tăng tốc Tải xuống (giữ nguyên) ---
        acceleration_group_box = QGroupBox("Cài đặt Tăng tốc Tải xuống")
        # ... (giữ nguyên code cho group box này) ...
        acceleration_form_layout = QFormLayout()
        self.use_aria2c_checkbox = QCheckBox("Sử dụng aria2c (cần cài đặt và có trong PATH)")
        self.use_aria2c_checkbox.setChecked(self.new_settings.get("use_aria2c", False))
        acceleration_form_layout.addRow(self.use_aria2c_checkbox)
        self.aria2c_args_label = QLabel("Đối số dòng lệnh cho aria2c:")
        self.aria2c_args_input = QLineEdit()
        self.aria2c_args_input.setText(self.new_settings.get("aria2c_args", "-j 8 -x 8 -s 8 -k 1M"))
        acceleration_form_layout.addRow(self.aria2c_args_label, self.aria2c_args_input)
        self.concurrent_fragments_label = QLabel("Số mảnh tải đồng thời (yt-dlp):")
        self.concurrent_fragments_spinbox = QSpinBox()
        self.concurrent_fragments_spinbox.setRange(1, 32)
        self.concurrent_fragments_spinbox.setValue(self.new_settings.get("concurrent_fragments", 4))
        acceleration_form_layout.addRow(self.concurrent_fragments_label, self.concurrent_fragments_spinbox)
        self.use_aria2c_checkbox.stateChanged.connect(self._toggle_aria2c_options_visibility)
        self._toggle_aria2c_options_visibility(self.use_aria2c_checkbox.checkState())
        acceleration_group_box.setLayout(acceleration_form_layout)
        general_settings_layout.addWidget(acceleration_group_box)

        # --- Cookies Tab Content ---
        self._build_cookies_tab(cookies_settings_layout)

        # --- HỘP MỚI: Cài đặt Âm thanh ---
        audio_group_box = QGroupBox("Cài đặt Âm thanh")
        audio_form_layout = QFormLayout()
        self.preferred_audio_format_combo = QComboBox()
        self.preferred_audio_format_combo.addItems([
            "Best (M4A)",
            "MP3",
            "WAV",
            "AAC",
            "FLAC"
        ])
        # Map setting value -> combo label
        saved_audio_pref = (self.new_settings.get("preferred_audio_format", "m4a") or "m4a").lower()
        mapping_value_to_label = {
            "m4a": "Best (M4A)",
            "mp3": "MP3",
            "wav": "WAV",
            "aac": "AAC",
            "flac": "FLAC",
        }
        self.preferred_audio_format_combo.setCurrentText(mapping_value_to_label.get(saved_audio_pref, "Best (M4A)"))
        audio_form_layout.addRow(QLabel("Định dạng âm thanh ưa thích:"), self.preferred_audio_format_combo)
        audio_group_box.setLayout(audio_form_layout)
        general_settings_layout.addWidget(audio_group_box)

        # --- Quản lý phiên bản & Cập nhật (giữ nguyên) ---
        version_group_box = QGroupBox("Quản lý phiên bản & Cập nhật")
        # ... (giữ nguyên code cho group box này) ...
        version_layout = QVBoxLayout()
        version_grid_layout = QGridLayout()
        self.version_label = QLabel("Phiên bản yt-dlp: Đang kiểm tra...")
        self.version_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.update_yt_dlp_button = QPushButton("Kiểm tra & Cập nhật")
        self.update_yt_dlp_button.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.update_yt_dlp_button.clicked.connect(self.manual_update_requested.emit)

        self.app_version_label = QLabel(f"Phiên bản ứng dụng: {APP_VERSION}")
        self.app_version_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.app_update_button = QPushButton("Cập nhật ứng dụng")
        self.app_update_button.setIcon(self.style().standardIcon(QStyle.SP_ArrowDown))
        self.app_update_button.clicked.connect(self.manual_app_update_requested.emit)

        version_grid_layout.addWidget(self.version_label, 0, 0)
        version_grid_layout.addWidget(self.update_yt_dlp_button, 0, 1, alignment=Qt.AlignRight)
        version_grid_layout.addWidget(self.app_version_label, 1, 0)
        version_grid_layout.addWidget(self.app_update_button, 1, 1, alignment=Qt.AlignRight)
        version_grid_layout.setColumnStretch(0, 1)
        self.update_progress_bar = QProgressBar()
        self.update_progress_bar.setVisible(False)
        self.update_progress_bar.setTextVisible(True)
        self.update_progress_bar.setFormat("Đang tải cập nhật... %p%")
        
        # Thêm trường hiển thị đường dẫn
        path_display_layout = QHBoxLayout()
        path_display_layout.addWidget(QLabel("Đường dẫn đang dùng:"))
        self.yt_dlp_path_display_input = QLineEdit()
        self.yt_dlp_path_display_input.setReadOnly(True)
        self.yt_dlp_path_display_input.setStyleSheet(f"background-color: {APP_THEME['app_bg']};") # Màu nền xám nhẹ
        path_display_layout.addWidget(self.yt_dlp_path_display_input)

        version_layout.addLayout(version_grid_layout)

        self.auto_update_yt_dlp_checkbox = QCheckBox("Tự động kiểm tra cập nhật yt-dlp khi khởi động")
        self.auto_update_yt_dlp_checkbox.setToolTip("Nếu được chọn, ứng dụng sẽ tự động kiểm tra phiên bản yt-dlp mới nhất mỗi khi khởi động.")
        self.auto_update_yt_dlp_checkbox.setChecked(self.new_settings.get("auto_update_yt_dlp", False)) # Mặc định là False (tắt)
        version_layout.addWidget(self.auto_update_yt_dlp_checkbox) # << THÊM DÒNG NÀY

        version_layout.addWidget(self.update_progress_bar)
        version_layout.addLayout(path_display_layout) # Thêm vào layout
        version_group_box.setLayout(version_layout)
        general_settings_layout.addWidget(version_group_box)
        
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept_settings)
        self.button_box.rejected.connect(self.reject)
        main_layout.addWidget(self.button_box)
        self.setLayout(main_layout)

        # --- Hộp mới: Cài đặt Proxy ---
        proxy_group_box = QGroupBox("Cài đặt Proxy")
        proxy_layout = QVBoxLayout()

        # --- Proxy Mode Selector ---
        proxy_mode_layout = QHBoxLayout()
        proxy_mode_layout.addWidget(QLabel("Phương thức Proxy:"))
        self.proxy_mode_combo = QComboBox()
        self.proxy_mode_combo.addItems(["Không dùng Proxy", "M2Proxy", "WARP (Cloudflare 1.1.1.1)"])
        # Load saved proxy_mode (backward compat with old use_proxy)
        saved_proxy_mode = self.new_settings.get("proxy_mode", "")
        if not saved_proxy_mode:
            # Migrate from old use_proxy boolean
            saved_proxy_mode = "m2proxy" if self.new_settings.get("use_proxy", False) else "none"
        mode_to_index = {"none": 0, "m2proxy": 1, "warp": 2}
        self.proxy_mode_combo.setCurrentIndex(mode_to_index.get(saved_proxy_mode, 0))
        proxy_mode_layout.addWidget(self.proxy_mode_combo)
        proxy_layout.addLayout(proxy_mode_layout)

        # --- Cấu hình M2Proxy Chi tiết ---
        self.proxy_details_group_box = QGroupBox("Cấu hình M2Proxy")
        proxy_details_layout = QFormLayout()
        
        # Package API key
        self.proxy_api_key_input = QLineEdit()
        proxy_details_layout.addRow("Package API key:", self.proxy_api_key_input)
        
        # User Token
        self.proxy_user_token_input = QLineEdit()
        proxy_details_layout.addRow("User Token:", self.proxy_user_token_input)
        
        # Host
        self.proxy_host_input = QLineEdit()
        proxy_details_layout.addRow("Host:", self.proxy_host_input)
        
        # Port
        self.proxy_port_spinbox = QSpinBox()
        self.proxy_port_spinbox.setRange(1, 65535)
        self.proxy_port_spinbox.setValue(8823)  # Default value
        proxy_details_layout.addRow("Port:", self.proxy_port_spinbox)
        
        # Username
        self.proxy_username_input = QLineEdit()
        self.proxy_username_input.setPlaceholderText("Bắt buộc cho xác thực USER/PASS")
        proxy_details_layout.addRow("Username:", self.proxy_username_input)
        
        # Password
        self.proxy_password_input = QLineEdit()
        self.proxy_password_input.setEchoMode(QLineEdit.Password)
        self.proxy_password_input.setPlaceholderText("Bắt buộc cho xác thực USER/PASS")
        proxy_details_layout.addRow("Password:", self.proxy_password_input)
        
        # Cooldown
        self.proxy_cooldown_spinbox = QSpinBox()
        self.proxy_cooldown_spinbox.setRange(0, 3600)
        self.proxy_cooldown_spinbox.setValue(240)  # Default value
        proxy_details_layout.addRow("Cooldown (giây):", self.proxy_cooldown_spinbox)

        # <<< THÊM Ô NHẬP LIỆU DỊCH VỤ IP >>>
        self.proxy_ip_checker_url_input = QLineEdit()
        self.proxy_ip_checker_url_input.setToolTip(
            "Dịch vụ URL (trả về JSON) để kiểm tra IP public.\n"
            "Phải chứa key 'ip' (vd: api.ipify.org) hoặc 'origin' (vd: httpbin.org)"
        )
        proxy_details_layout.addRow("IP Checker URL:", self.proxy_ip_checker_url_input)
        
        # Nút đổi IP proxy
        self.change_ip_button = QPushButton("Đổi IP Proxy ngay")
        self.change_ip_button.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        proxy_details_layout.addRow(self.change_ip_button)
        
        self.proxy_details_group_box.setLayout(proxy_details_layout)
        proxy_layout.addWidget(self.proxy_details_group_box)

        # --- Cấu hình WARP ---
        self.warp_details_group_box = QGroupBox("Cấu hình WARP (Cloudflare 1.1.1.1)")
        warp_details_layout = QFormLayout()
        self.warp_port_spinbox = QSpinBox()
        self.warp_port_spinbox.setRange(1, 65535)
        self.warp_port_spinbox.setValue(self.new_settings.get("warp_port", 40000))
        warp_details_layout.addRow("WARP SOCKS5 Port:", self.warp_port_spinbox)

        # Hàng nút: Cài đặt + Kiểm tra
        warp_buttons_layout = QHBoxLayout()
        self.warp_setup_button = QPushButton("Cài đặt && Kết nối WARP")
        self.warp_setup_button.setIcon(self.style().standardIcon(QStyle.SP_ComputerIcon))
        self.warp_setup_button.setToolTip("Tự động đăng ký, bật proxy mode và kết nối WARP")
        self.warp_setup_button.clicked.connect(self._setup_warp_connection)
        warp_buttons_layout.addWidget(self.warp_setup_button)

        self.warp_test_button = QPushButton("Kiểm tra kết nối")
        self.warp_test_button.setIcon(self.style().standardIcon(QStyle.SP_DialogApplyButton))
        self.warp_test_button.clicked.connect(self._test_warp_connection)
        warp_buttons_layout.addWidget(self.warp_test_button)

        self.warp_change_ip_button = QPushButton("Đổi IP WARP")
        self.warp_change_ip_button.setIcon(self.style().standardIcon(QStyle.SP_BrowserReload))
        self.warp_change_ip_button.setToolTip("Ngắt kết nối rồi kết nối lại để thử lấy IP mới")
        self.warp_change_ip_button.clicked.connect(self._change_warp_ip)
        warp_buttons_layout.addWidget(self.warp_change_ip_button)
        warp_details_layout.addRow(warp_buttons_layout)

        # Label hiển thị trạng thái WARP
        self.warp_status_label = QLabel("Chưa kiểm tra")
        self.warp_status_label.setStyleSheet("color: #888; font-size: 11px; padding: 4px;")
        self.warp_status_label.setWordWrap(True)
        warp_details_layout.addRow("Trạng thái:", self.warp_status_label)

        warp_info_label = QLabel(
            "Chỉ áp dụng cho tải video, không ảnh hưởng hệ thống.\n"
            "Nếu chưa cài WARP: tải tại https://1.1.1.1"
        )
        warp_info_label.setStyleSheet("color: #666; font-size: 11px;")
        warp_info_label.setOpenExternalLinks(True)
        warp_details_layout.addRow(warp_info_label)
        self.warp_details_group_box.setLayout(warp_details_layout)
        proxy_layout.addWidget(self.warp_details_group_box)
        
        # Kết nối tín hiệu để bật/tắt group box chi tiết
        self.proxy_mode_combo.currentIndexChanged.connect(self._on_proxy_mode_changed)
        
        # Kết nối nút đổi IP với tín hiệu
        self.change_ip_button.clicked.connect(self.manual_change_ip_requested.emit)
        
        # Đặt trạng thái ban đầu
        self._on_proxy_mode_changed()
        
        proxy_group_box.setLayout(proxy_layout)
        proxy_settings_layout.addWidget(proxy_group_box)
        
        # Thêm các trang vào QTabWidget
        tab_widget.addTab(general_settings_page, "Cài đặt chung")
        tab_widget.addTab(proxy_settings_page, "Cài đặt Proxy")
        tab_widget.addTab(cookies_settings_page, "🍪 Cookies")
        
        # Tải dữ liệu proxy từ file
        self._load_proxy_config()

    def _on_proxy_mode_changed(self, index=None):
        """Xử lý khi combo proxy mode thay đổi."""
        current_index = self.proxy_mode_combo.currentIndex() if index is None else index
        # 0 = Không dùng, 1 = M2Proxy, 2 = WARP
        self.proxy_details_group_box.setVisible(current_index == 1)
        self.warp_details_group_box.setVisible(current_index == 2)
    def _setup_warp_connection(self):
        """Tự động cài đặt và kết nối WARP (registration + proxy mode + connect)."""
        self.warp_setup_button.setEnabled(False)
        self.warp_test_button.setEnabled(False)
        self.warp_status_label.setText("⏳ Đang cài đặt WARP...")
        self.warp_status_label.setStyleSheet("color: #2196F3; font-size: 11px; padding: 4px;")

        self._warp_setup_thread = QThread(self)
        WARP_CLI = r"C:\Program Files\Cloudflare\Cloudflare WARP\warp-cli.exe"

        class WarpSetupWorker(QObject):
            finished = Signal(bool, str)  # success, message
            progress = Signal(str)  # step status

            def __init__(self):
                super().__init__()

            def _run_cli(self, args):
                flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
                return subprocess.run(
                    [WARP_CLI] + args,
                    capture_output=True, text=True, timeout=15,
                    creationflags=flags
                )

            @Slot()
            def run(self):
                # Step 0: Kiểm tra WARP CLI có tồn tại
                if not os.path.isfile(WARP_CLI):
                    self.finished.emit(False,
                        "❌ Chưa cài đặt Cloudflare WARP!\n"
                        "Tải tại: https://1.1.1.1\n"
                        "Sau khi cài xong, nhấn lại nút này.")
                    return

                steps_log = []

                # Step 1: Đăng ký (registration new)
                self.progress.emit("⏳ Bước 1/3: Đăng ký WARP...")
                try:
                    result = self._run_cli(["registration", "new"])
                    if result.returncode == 0:
                        steps_log.append("✅ Đăng ký thành công")
                    elif "Already" in result.stderr or "already" in result.stdout.lower() or "already" in result.stderr.lower():
                        steps_log.append("✅ Đã đăng ký trước đó")
                    else:
                        err = result.stderr.strip() or result.stdout.strip()
                        steps_log.append(f"⚠️ Đăng ký: {err}")
                except Exception as e:
                    steps_log.append(f"⚠️ Đăng ký lỗi: {e}")

                # Step 2: Bật proxy mode
                self.progress.emit("⏳ Bước 2/3: Bật chế độ proxy...")
                try:
                    result = self._run_cli(["mode", "proxy"])
                    if result.returncode == 0:
                        steps_log.append("✅ Đã bật proxy mode")
                    else:
                        err = result.stderr.strip() or result.stdout.strip()
                        if "already" in err.lower():
                            steps_log.append("✅ Proxy mode đã bật sẵn")
                        else:
                            steps_log.append(f"⚠️ Proxy mode: {err}")
                except Exception as e:
                    steps_log.append(f"⚠️ Proxy mode lỗi: {e}")

                # Step 3: Kết nối
                self.progress.emit("⏳ Bước 3/3: Kết nối WARP...")
                try:
                    result = self._run_cli(["connect"])
                    if result.returncode == 0:
                        steps_log.append("✅ Đã kết nối WARP")
                    else:
                        err = result.stderr.strip() or result.stdout.strip()
                        if "already" in err.lower() or "Connected" in err:
                            steps_log.append("✅ Đã kết nối sẵn")
                        else:
                            steps_log.append(f"⚠️ Kết nối: {err}")
                except Exception as e:
                    steps_log.append(f"⚠️ Kết nối lỗi: {e}")

                # Kiểm tra kết quả cuối cùng
                has_error = any("⚠️" in s and "đã" not in s.lower() for s in steps_log)
                summary = "\n".join(steps_log)
                if has_error:
                    self.finished.emit(False, f"Cài đặt có vấn đề:\n{summary}")
                else:
                    self.finished.emit(True, f"🎉 Cài đặt WARP hoàn tất!\n{summary}")

        self._warp_setup_worker = WarpSetupWorker()
        self._warp_setup_worker.moveToThread(self._warp_setup_thread)
        self._warp_setup_worker.progress.connect(
            lambda msg: self.warp_status_label.setText(msg)
        )
        self._warp_setup_worker.finished.connect(self._on_warp_setup_finished)
        self._warp_setup_thread.started.connect(self._warp_setup_worker.run)
        self._warp_setup_thread.finished.connect(self._warp_setup_thread.deleteLater)
        self._warp_setup_thread.finished.connect(self._warp_setup_worker.deleteLater)
        self._warp_setup_thread.start()

    @Slot(bool, str)
    def _on_warp_setup_finished(self, success, message):
        """Xử lý kết quả setup WARP."""
        self.warp_setup_button.setEnabled(True)
        self.warp_test_button.setEnabled(True)
        self.warp_status_label.setText(message)
        if success:
            self.warp_status_label.setStyleSheet("color: #4CAF50; font-size: 11px; padding: 4px;")
            # Auto-run test sau khi setup thành công
            QTimer.singleShot(1000, self._test_warp_connection)
        else:
            self.warp_status_label.setStyleSheet("color: #F44336; font-size: 11px; padding: 4px;")
        if self._warp_setup_thread and self._warp_setup_thread.isRunning():
            self._warp_setup_thread.quit()

    def _change_warp_ip(self):
        """Ngắt kết nối rồi kết nối lại WARP để thử lấy IP mới."""
        self.warp_change_ip_button.setEnabled(False)
        self.warp_test_button.setEnabled(False)
        self.warp_setup_button.setEnabled(False)
        self.warp_status_label.setText("⏳ Đang đổi IP WARP...")
        self.warp_status_label.setStyleSheet("color: #2196F3; font-size: 11px; padding: 4px;")

        self._warp_change_ip_thread = QThread(self)
        WARP_CLI = r"C:\Program Files\Cloudflare\Cloudflare WARP\warp-cli.exe"
        warp_port = self.warp_port_spinbox.value()

        class WarpChangeIpWorker(QObject):
            finished = Signal(bool, str, str, str)  # success, message, old_ip, new_ip
            progress = Signal(str)

            def _run_cli(self, args):
                flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
                return subprocess.run(
                    [WARP_CLI] + args,
                    capture_output=True, text=True, timeout=15,
                    creationflags=flags
                )

            def _get_proxy_ip(self):
                """Lấy IP hiện tại qua WARP proxy."""
                try:
                    import socks
                    import socket
                    s = socks.socksocket()
                    s.set_proxy(socks.SOCKS5, "127.0.0.1", warp_port)
                    s.settimeout(10)
                    s.connect(("api.ipify.org", 80))
                    s.sendall(b"GET /?format=text HTTP/1.1\r\nHost: api.ipify.org\r\nConnection: close\r\n\r\n")
                    response = s.recv(4096).decode()
                    s.close()
                    for line in response.split("\n"):
                        line = line.strip()
                        if line and all(c in "0123456789." for c in line):
                            return line
                except Exception:
                    pass
                # Fallback: curl
                try:
                    flags = subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
                    r = subprocess.run(
                        ["curl", "-s", "--max-time", "10",
                         "--socks5-hostname", f"127.0.0.1:{warp_port}",
                         "https://api.ipify.org?format=text"],
                        capture_output=True, text=True, timeout=15, creationflags=flags
                    )
                    if r.returncode == 0 and r.stdout.strip():
                        return r.stdout.strip()
                except Exception:
                    pass
                return None

            @Slot()
            def run(self):
                # Lấy IP cũ trước
                self.progress.emit("⏳ Đang lấy IP hiện tại...")
                old_ip = self._get_proxy_ip()

                # Disconnect
                self.progress.emit("⏳ Đang ngắt kết nối...")
                try:
                    self._run_cli(["disconnect"])
                except Exception:
                    pass

                # Đợi 2 giây
                import time as _time
                _time.sleep(2)

                # Reconnect
                self.progress.emit("⏳ Đang kết nối lại...")
                try:
                    result = self._run_cli(["connect"])
                    if result.returncode != 0:
                        err = result.stderr.strip() or result.stdout.strip()
                        if "already" not in err.lower() and "connected" not in err.lower():
                            self.finished.emit(False, f"❌ Lỗi kết nối lại: {err}", old_ip or "?", "?")
                            return
                except Exception as e:
                    self.finished.emit(False, f"❌ Lỗi: {e}", old_ip or "?", "?")
                    return

                # Đợi WARP ổn định
                _time.sleep(2)

                # Lấy IP mới
                self.progress.emit("⏳ Đang kiểm tra IP mới...")
                new_ip = self._get_proxy_ip()

                if not new_ip:
                    self.finished.emit(False, "❌ Không lấy được IP mới (WARP có thể chưa kết nối)", old_ip or "?", "?")
                    return

                if old_ip and new_ip != old_ip:
                    self.finished.emit(True, f"✅ Đổi IP thành công!\n🔴 IP cũ: {old_ip}\n🟢 IP mới: {new_ip}", old_ip, new_ip)
                elif old_ip and new_ip == old_ip:
                    self.finished.emit(True, f"⚠️ IP không thay đổi (vẫn là {new_ip})\nCloudflare Anycast gán IP theo vị trí, thử lại sau.", old_ip, new_ip)
                else:
                    self.finished.emit(True, f"✅ Đã kết nối lại!\n🟢 IP hiện tại: {new_ip}", "?", new_ip)

        self._warp_change_ip_worker = WarpChangeIpWorker()
        self._warp_change_ip_worker.moveToThread(self._warp_change_ip_thread)
        self._warp_change_ip_worker.progress.connect(
            lambda msg: self.warp_status_label.setText(msg)
        )
        self._warp_change_ip_worker.finished.connect(self._on_warp_change_ip_finished)
        self._warp_change_ip_thread.started.connect(self._warp_change_ip_worker.run)
        self._warp_change_ip_thread.finished.connect(self._warp_change_ip_thread.deleteLater)
        self._warp_change_ip_thread.finished.connect(self._warp_change_ip_worker.deleteLater)
        self._warp_change_ip_thread.start()

    @Slot(bool, str, str, str)
    def _on_warp_change_ip_finished(self, success, message, old_ip, new_ip):
        """Xử lý kết quả đổi IP WARP."""
        self.warp_change_ip_button.setEnabled(True)
        self.warp_test_button.setEnabled(True)
        self.warp_setup_button.setEnabled(True)
        self.warp_status_label.setText(message)
        if success and old_ip != new_ip:
            self.warp_status_label.setStyleSheet("color: #4CAF50; font-size: 11px; padding: 4px;")
        elif success:
            self.warp_status_label.setStyleSheet("color: #FF9800; font-size: 11px; padding: 4px;")
        else:
            self.warp_status_label.setStyleSheet("color: #F44336; font-size: 11px; padding: 4px;")
        if self._warp_change_ip_thread and self._warp_change_ip_thread.isRunning():
            self._warp_change_ip_thread.quit()

    def _test_warp_connection(self):
        """Kiểm tra kết nối WARP proxy."""
        self.warp_test_button.setEnabled(False)
        self.warp_status_label.setText("⏳ Đang kiểm tra...")
        self.warp_status_label.setStyleSheet("color: #2196F3; font-size: 11px; padding: 4px;")
        warp_port = self.warp_port_spinbox.value()

        self._warp_test_thread = QThread(self)

        class WarpTestWorker(QObject):
            finished = Signal(bool, str)  # success, message

            def __init__(self, port):
                super().__init__()
                self.port = port

            @Slot()
            def run(self):
                import socket
                # Step 1: Kiểm tra WARP CLI status
                warp_cli_status = ""
                try:
                    result = subprocess.run(
                        [r"C:\Program Files\Cloudflare\Cloudflare WARP\warp-cli.exe", "status"],
                        capture_output=True, text=True, timeout=5,
                        creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
                    )
                    warp_cli_status = result.stdout.strip() if result.returncode == 0 else f"CLI error: {result.stderr.strip()}"
                except FileNotFoundError:
                    self.finished.emit(False, "❌ Không tìm thấy warp-cli.exe\nCần cài đặt Cloudflare WARP.")
                    return
                except Exception as e:
                    warp_cli_status = f"Không thể kiểm tra CLI: {e}"

                # Step 2: Kiểm tra SOCKS5 port mở
                try:
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(3)
                    conn_result = sock.connect_ex(('127.0.0.1', self.port))
                    sock.close()
                    if conn_result != 0:
                        self.finished.emit(False,
                            f"❌ Không thể kết nối SOCKS5 tại 127.0.0.1:{self.port}\n"
                            f"Hãy chạy: warp-cli connect\n"
                            f"WARP CLI: {warp_cli_status}")
                        return
                except Exception as e:
                    self.finished.emit(False, f"❌ Lỗi kiểm tra port: {e}")
                    return

                # Step 3: Lấy IP qua WARP proxy
                warp_ip = "Không xác định"
                try:
                    import urllib.request
                    import socks  # PySocks
                    proxy_handler = urllib.request.ProxyHandler({
                        'http': f'socks5h://127.0.0.1:{self.port}',
                        'https': f'socks5h://127.0.0.1:{self.port}'
                    })
                    opener = urllib.request.build_opener(proxy_handler)
                    req = urllib.request.Request(
                        "https://api.ipify.org?format=json",
                        headers={'User-Agent': 'Mozilla/5.0'}
                    )
                    with opener.open(req, timeout=10) as resp:
                        data = json.loads(resp.read().decode())
                        warp_ip = data.get("ip", "Không xác định")
                except ImportError:
                    # PySocks không có, thử cURL fallback
                    try:
                        curl_result = subprocess.run(
                            ["curl", "-s", "--socks5-hostname",
                             f"127.0.0.1:{self.port}",
                             "https://api.ipify.org?format=json"],
                            capture_output=True, text=True, timeout=15,
                            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
                        )
                        if curl_result.returncode == 0 and curl_result.stdout.strip():
                            data = json.loads(curl_result.stdout.strip())
                            warp_ip = data.get("ip", "Không xác định")
                    except Exception:
                        warp_ip = "Không thể lấy (thiếu PySocks & curl)"
                except Exception as e:
                    warp_ip = f"Lỗi: {e}"

                # Step 4: Lấy IP trực tiếp để so sánh
                direct_ip = ""
                try:
                    req_direct = urllib.request.Request(
                        "https://api.ipify.org?format=json",
                        headers={'User-Agent': 'Mozilla/5.0'}
                    )
                    with urllib.request.urlopen(req_direct, timeout=5) as resp:
                        data = json.loads(resp.read().decode())
                        direct_ip = data.get("ip", "")
                except Exception:
                    direct_ip = "Không lấy được"

                ip_match_note = ""
                if direct_ip and warp_ip and direct_ip != warp_ip and "Lỗi" not in warp_ip and "Không" not in warp_ip:
                    ip_match_note = f"\n📍 IP thật: {direct_ip} (khác → WARP hoạt động!)"
                elif direct_ip and warp_ip == direct_ip:
                    ip_match_note = f"\n⚠️ IP thật: {direct_ip} (giống → WARP có thể chưa hoạt động)"

                self.finished.emit(True,
                    f"✅ WARP đang hoạt động!\n"
                    f"🌐 IP qua WARP: {warp_ip}{ip_match_note}\n"
                    f"📡 SOCKS5: 127.0.0.1:{self.port}")

        self._warp_test_worker = WarpTestWorker(warp_port)
        self._warp_test_worker.moveToThread(self._warp_test_thread)
        self._warp_test_worker.finished.connect(self._on_warp_test_finished)
        self._warp_test_thread.started.connect(self._warp_test_worker.run)
        self._warp_test_thread.finished.connect(self._warp_test_thread.deleteLater)
        self._warp_test_thread.finished.connect(self._warp_test_worker.deleteLater)
        self._warp_test_thread.start()

    @Slot(bool, str)
    def _on_warp_test_finished(self, success, message):
        """Xử lý kết quả test WARP."""
        self.warp_test_button.setEnabled(True)
        self.warp_status_label.setText(message)
        if success:
            self.warp_status_label.setStyleSheet("color: #4CAF50; font-size: 11px; padding: 4px;")
        else:
            self.warp_status_label.setStyleSheet("color: #F44336; font-size: 11px; padding: 4px;")
        if self._warp_test_thread and self._warp_test_thread.isRunning():
            self._warp_test_thread.quit()

    def _load_proxy_config(self):
        """Tải cấu hình proxy từ file proxy_settings.json."""
        proxy_config_path = os.path.join(SCRIPT_BASE_DIR_UI, DATA_DIR_NAME, "proxy_settings.json")
        
        try:
            with open(proxy_config_path, 'r', encoding='utf-8') as f:
                proxy_config = json.load(f)
            
            # Điền dữ liệu vào các widget
            m2_config = proxy_config.get("M2_CONFIG", {})
            self.proxy_api_key_input.setText(m2_config.get("package_api_key", ""))
            self.proxy_user_token_input.setText(m2_config.get("user_token", ""))
            
            proxy_connection = proxy_config.get("PROXY_CONNECTION", {})
            self.proxy_host_input.setText(proxy_connection.get("host", ""))
            self.proxy_port_spinbox.setValue(proxy_connection.get("port", 8823))
            self.proxy_username_input.setText(proxy_connection.get("username", ""))
            self.proxy_password_input.setText(proxy_connection.get("password", ""))
            
            self.proxy_cooldown_spinbox.setValue(proxy_config.get("proxy_cooldown_seconds", 240))

            # <<< TẢI URL DỊCH VỤ IP >>>
            default_checker_url = "https://api.ipify.org?format=json"
            self.proxy_ip_checker_url_input.setText(
                proxy_config.get("ip_checker_service_url", default_checker_url)
            )
            
        except FileNotFoundError:
            # File không tồn tại, giữ giá trị mặc định
            # Đặt giá trị mặc định cho ô mới nếu file không tồn tại
            self.proxy_ip_checker_url_input.setText("https://api.ipify.org?format=json")
            pass
        except (json.JSONDecodeError, KeyError):
            # File bị hỏng hoặc cấu trúc không đúng, giữ giá trị mặc định
            # Đặt giá trị mặc định cho ô mới nếu file bị hỏng
            self.proxy_ip_checker_url_input.setText("https://api.ipify.org?format=json")
            pass

    def _build_cookies_tab(self, layout):
        """Xây dựng nội dung tab Cookies."""
        source_group = QGroupBox("Nguồn Cookies")
        source_layout = QFormLayout()

        self.cookies_mode_combo = QComboBox()
        self.cookies_mode_combo.addItems([
            "Không dùng",
            "Chrome riêng của ứng dụng",
            "File tùy chỉnh (.txt)",
        ])
        source_layout.addRow("Chế độ:", self.cookies_mode_combo)

        self.cookies_browser_panel = QWidget()
        browser_panel_layout = QVBoxLayout(self.cookies_browser_panel)
        browser_panel_layout.setContentsMargins(0, 4, 0, 0)

        self.managed_profile_path = QLabel(
            str(getattr(self.managed_chrome, "profile_dir", "Không khả dụng"))
        )
        self.managed_profile_path.setWordWrap(True)
        self.managed_profile_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        browser_panel_layout.addWidget(QLabel("Profile Chrome riêng:"))
        browser_panel_layout.addWidget(self.managed_profile_path)

        actions = QHBoxLayout()
        self.managed_open_button = QPushButton("Mở Chrome / Đăng nhập")
        self.managed_open_button.clicked.connect(self._open_managed_chrome)
        self.managed_status_button = QPushButton("Kiểm tra đăng nhập")
        self.managed_status_button.clicked.connect(self._check_managed_login)
        actions.addWidget(self.managed_open_button)
        actions.addWidget(self.managed_status_button)
        actions.addStretch()
        browser_panel_layout.addLayout(actions)

        self.managed_status_label = QLabel("")
        self.managed_status_label.setWordWrap(True)
        self.managed_status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.managed_status_label.setStyleSheet("font-size: 11px; padding: 2px;")
        browser_panel_layout.addWidget(self.managed_status_label)
        source_layout.addRow(self.cookies_browser_panel)

        self.cookies_file_widget = QWidget()
        file_layout = QHBoxLayout(self.cookies_file_widget)
        file_layout.setContentsMargins(0, 4, 0, 0)
        self.cookies_file_path_input = QLineEdit()
        self.cookies_file_path_input.setPlaceholderText("Đường dẫn đến file cookies.txt")
        self.cookies_file_path_input.setText(
            str(self.new_settings.get("cookies_file_path", "") or "")
        )
        self.browse_cookies_button = QPushButton("Duyệt...")
        self.browse_cookies_button.clicked.connect(self._browse_for_cookies_file)
        file_layout.addWidget(self.cookies_file_path_input)
        file_layout.addWidget(self.browse_cookies_button)
        source_layout.addRow(self.cookies_file_widget)

        source_group.setLayout(source_layout)
        layout.addWidget(source_group)
        layout.addStretch()

        mode_to_index = {
            COOKIE_SOURCE_NONE: 0,
            COOKIE_SOURCE_MANAGED: 1,
            COOKIE_SOURCE_FILE: 2,
        }
        self.cookies_mode_combo.setCurrentIndex(
            mode_to_index[get_cookie_source_mode(self.new_settings)]
        )

        def _on_cookies_mode_changed(index=None):
            selected = self.cookies_mode_combo.currentIndex() if index is None else index
            self.cookies_browser_panel.setVisible(selected == 1)
            self.cookies_file_widget.setVisible(selected == 2)

        self.cookies_mode_combo.currentIndexChanged.connect(_on_cookies_mode_changed)
        _on_cookies_mode_changed()

    def _open_managed_chrome(self):
        if self.managed_chrome is None:
            self.managed_status_label.setText("Chrome riêng chưa khả dụng.")
            self.managed_status_label.setStyleSheet(
                "color: #F44336; font-size: 11px; padding: 2px;"
            )
            return
        result = self.managed_chrome.open_browser()
        self.managed_status_label.setText(result.message)
        color = "#4CAF50" if result.success else "#F44336"
        self.managed_status_label.setStyleSheet(
            f"color: {color}; font-size: 11px; padding: 2px;"
        )

    def _check_managed_login(self):
        if self.managed_chrome is None:
            self.managed_status_label.setText("Chrome riêng chưa khả dụng.")
            self.managed_status_label.setStyleSheet(
                "color: #F44336; font-size: 11px; padding: 2px;"
            )
            return
        status = self.managed_chrome.check_login_status()
        self.managed_status_label.setText(status.message)
        colors = {
            "authenticated": "#4CAF50",
            "not_authenticated": "#F57C00",
            "unavailable": "#F44336",
        }
        self.managed_status_label.setStyleSheet(
            f"color: {colors.get(status.state, '#F44336')}; font-size: 11px; padding: 2px;"
        )


    def _browse_for_cookies_file(self):
        """Mở hộp thoại file để chọn file cookies."""
        current_path = self.cookies_file_path_input.text()
        start_dir = os.path.dirname(current_path) if current_path and os.path.exists(os.path.dirname(current_path)) else os.path.expanduser("~")
        
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Chọn file Cookies",
            start_dir,
            "Cookies Files (*.txt);;All Files (*)"
        )
        if file_path:
            self.cookies_file_path_input.setText(file_path)


    def accept_settings(self):
        # Lưu các cài đặt cũ
        self.new_settings["max_concurrent_downloads"] = self.max_concurrent_downloads_spinbox.value()
        self.new_settings["save_thumbnail_with_video"] = self.save_thumbnail_with_video_checkbox.isChecked()
        self.new_settings["auto_deduplicate_history"] = self.auto_deduplicate_checkbox.isChecked()
        self.new_settings["clean_filenames"] = self.clean_filenames_checkbox.isChecked()
        self.new_settings["use_aria2c"] = self.use_aria2c_checkbox.isChecked()
        self.new_settings["aria2c_args"] = self.aria2c_args_input.text().strip()
        self.new_settings["concurrent_fragments"] = self.concurrent_fragments_spinbox.value()

        self.new_settings["auto_update_yt_dlp"] = self.auto_update_yt_dlp_checkbox.isChecked()
        
        # Lưu ba chế độ cookie tách biệt; giữ lại đường dẫn file khi tạm chuyển mode.
        self.new_settings["cookies_file_path"] = self.cookies_file_path_input.text().strip()
        cookie_modes = (
            COOKIE_SOURCE_NONE,
            COOKIE_SOURCE_MANAGED,
            COOKIE_SOURCE_FILE,
        )
        set_cookie_source_mode(
            self.new_settings,
            cookie_modes[self.cookies_mode_combo.currentIndex()],
        )

        # Lưu định dạng âm thanh ưa thích (dưới dạng chuỗi chữ thường)
        label = (self.preferred_audio_format_combo.currentText() or "Best (M4A)").strip()
        label_lower = label.lower()
        if "m4a" in label_lower or "best" in label_lower:
            pref_value = "m4a"
        elif "mp3" in label_lower:
            pref_value = "mp3"
        elif "wav" in label_lower:
            pref_value = "wav"
        elif "aac" in label_lower:
            pref_value = "aac"
        elif "flac" in label_lower:
            pref_value = "flac"
        else:
            pref_value = "m4a"
        self.new_settings["preferred_audio_format"] = pref_value
        
        # Lưu cài đặt proxy mode
        index_to_mode = {0: "none", 1: "m2proxy", 2: "warp"}
        current_proxy_mode = index_to_mode.get(self.proxy_mode_combo.currentIndex(), "none")
        self.new_settings["proxy_mode"] = current_proxy_mode
        # Backward compat: keep use_proxy in sync
        self.new_settings["use_proxy"] = current_proxy_mode != "none"
        # Lưu WARP port
        self.new_settings["warp_port"] = self.warp_port_spinbox.value()
        
        # Lưu cấu hình M2Proxy chi tiết (chỉ validate khi mode=m2proxy)
        if current_proxy_mode == "m2proxy":
            # Validation: Kiểm tra các trường bắt buộc
            api_key = self.proxy_api_key_input.text().strip()
            host = self.proxy_host_input.text().strip()
            username = self.proxy_username_input.text().strip()
            password = self.proxy_password_input.text()  # Không strip() mật khẩu
            
            if not api_key or not host or not username or not password:
                QMessageBox.warning(
                    self, 
                    "Cấu hình Proxy không đầy đủ", 
                    "Vui lòng điền đầy đủ API Key, Host, Username và Password cho proxy."
                )
                return  # Ngăn không cho dialog đóng lại
            
            # Tạo đối tượng cấu hình proxy
            proxy_settings_to_save = {
                "M2_CONFIG": {
                    "base_url": "https://api.m2proxy.com",  # Giữ giá trị này cố định
                    "user_token": self.proxy_user_token_input.text().strip(),
                    "package_api_key": api_key
                },
                "PROXY_CONNECTION": {
                    "host": host,
                    "port": self.proxy_port_spinbox.value(),
                    "username": username,
                    "password": password  # Không strip() mật khẩu
                },
                "proxy_cooldown_seconds": self.proxy_cooldown_spinbox.value(),
                
                # <<< LƯU URL DỊCH VỤ IP >>>
                "ip_checker_service_url": (
                    self.proxy_ip_checker_url_input.text().strip() or 
                    "https://api.ipify.org?format=json" # Giá trị mặc định nếu người dùng xóa trống
                )
            }
            
            # Ghi ra file
            proxy_config_path = os.path.join(SCRIPT_BASE_DIR_UI, DATA_DIR_NAME, "proxy_settings.json")
            try:
                with open(proxy_config_path, 'w', encoding='utf-8') as f:
                    json.dump(proxy_settings_to_save, f, indent=4, ensure_ascii=False)
            except IOError as e:
                QMessageBox.warning(
                    self, 
                    "Lỗi lưu cấu hình Proxy", 
                    f"Không thể lưu cấu hình proxy: {str(e)}"
                )
                return  # Ngăn không cho dialog đóng lại

        self.accept()
        
    # Các hàm khác giữ nguyên: get_settings, set_yt_dlp_version, set_update_button_enabled, etc.
    def get_settings(self):
        return self.new_settings
        
    def _toggle_aria2c_options_visibility(self, state):
        use_aria2c = (state == Qt.Checked)
        self.aria2c_args_label.setVisible(use_aria2c)
        self.aria2c_args_input.setVisible(use_aria2c)
        self.concurrent_fragments_label.setVisible(not use_aria2c)
        self.concurrent_fragments_spinbox.setVisible(not use_aria2c)

    def set_yt_dlp_version(self, version_string):
        if version_string: self.version_label.setText(f"Phiên bản yt-dlp: {version_string}")
        else: self.version_label.setText("Phiên bản yt-dlp: Không tìm thấy")

    def set_update_button_enabled(self, enabled):
        self.update_yt_dlp_button.setEnabled(enabled)
        if enabled: self.update_progress_bar.setVisible(False)

    def set_app_update_button_enabled(self, enabled):
        self.app_update_button.setEnabled(enabled)

    def show_update_progress(self, show):
        self.update_progress_bar.setVisible(show)
        if show: self.update_progress_bar.setValue(0)

    def update_progress_value(self, downloaded, total):
        if total > 0: self.update_progress_bar.setValue(int((downloaded / total) * 100))
        else: self.update_progress_bar.setRange(0, 0)
        
    def set_yt_dlp_path_display(self, path_string):
        """Cập nhật text cho QLineEdit hiển thị đường dẫn yt-dlp."""
        if path_string: self.yt_dlp_path_display_input.setText(path_string)
        else: self.yt_dlp_path_display_input.setText("Chưa xác định")
