# main_logic.py
import subprocess
import os
import platform
import sys
import urllib.request
import urllib.parse  # [ZERO-LEAK-FIX] encode proxy credentials safely
import shutil
import json
import re # Thêm import re
import ssl # << THÊM DÒNG NÀY

from update_manager import UpdateManager

# --- Import module xác minh ---
try:
    import video_verifier
except ImportError:
    print("LỖI: Không thể import video_verifier.py. Đảm bảo file này ở cùng thư mục.")
    video_verifier = None # Để chương trình có thể chạy nhưng không có xác minh

SCRIPT_BASE_DIR = os.path.dirname(sys.executable) \
    if getattr(sys, 'frozen', False) \
    else os.path.dirname(os.path.abspath(__file__)) \
    if '__file__' in globals() and os.path.exists(__file__) \
    else os.getcwd()
# --- THAY ĐỔI ĐƯỜNG DẪN FILE CÀI ĐẶT CONSOLE ---
DATA_DIR_NAME_MAIN = "data" # Định nghĩa tên thư mục data
CONSOLE_SETTINGS_FILE_NAME = "downloader_settings.json"
CONSOLE_SETTINGS_FILE_PATH = os.path.join(SCRIPT_BASE_DIR, DATA_DIR_NAME_MAIN, CONSOLE_SETTINGS_FILE_NAME)
# --- KẾT THÚC THAY ĐỔI ---
LOCAL_YT_DLP_SUBDIR = os.path.join(SCRIPT_BASE_DIR, "yt-dlp")
YT_DLP_CMD_TO_USE = None
GITHUB_OWNER = "davidtuyen"
GITHUB_REPO = "DC_video_youtube"
USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0"  # [ZERO-LEAK-FIX]


def _normalize_proxy_url(proxy_url: str | None) -> str | None:
    """Return sanitized proxy URL with URL-encoded credentials."""
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

# --- Các hàm get_script_directory, load_settings_from_file, save_settings_to_file,
# download_file_with_progress, find_or_download_yt_dlp giữ nguyên như trước ---
# (Không gửi lại để tiết kiệm không gian)
def get_yt_dlp_js_runtime_args(which=shutil.which, base_dir=None):
    """Return yt-dlp CLI args, preferring the Node runtime bundled with the app."""
    runtime_base_dir = base_dir or SCRIPT_BASE_DIR
    bundled_node_path = os.path.abspath(os.path.join(
        runtime_base_dir,
        DATA_DIR_NAME_MAIN,
        "node",
        "node.exe" if platform.system() == "Windows" else "node",
    ))
    if os.path.isfile(bundled_node_path):
        return ["--js-runtimes", f"node:{bundled_node_path}"]

    for runtime_name in ("deno", "node"):
        runtime_path = which(runtime_name)
        if runtime_path:
            return ["--js-runtimes", f"{runtime_name}:{runtime_path}"]
    return []


def get_script_directory():
    """Trả về đường dẫn thư mục chứa script hoặc file .exe đã đóng gói."""
    return SCRIPT_BASE_DIR
def _ensure_data_directory_main(): # << THÊM HÀM TIỆN ÍCH NẾU CẦN
    """Đảm bảo thư mục data tồn tại ở SCRIPT_BASE_DIR."""
    data_dir_path = os.path.join(SCRIPT_BASE_DIR, DATA_DIR_NAME_MAIN)
    if not os.path.exists(data_dir_path):
        try:
            os.makedirs(data_dir_path)
            print(f"Thông báo (main_logic): Đã tạo thư mục dữ liệu: {data_dir_path}")
        except OSError as e:
            print(f"Lỗi (main_logic): Không thể tạo thư mục dữ liệu '{data_dir_path}': {e}")

def load_settings_from_file(settings_file_path):
    """Tải cài đặt từ file JSON được chỉ định."""
    _ensure_data_directory_main() # Đảm bảo thư mục data tồn tại trước khi đọc
    if os.path.exists(settings_file_path):
        try:
            with open(settings_file_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
                return settings
        except (json.JSONDecodeError, IOError) as e:
            print(f"Cảnh báo: Không thể đọc file cài đặt ({settings_file_path}): {e}.")
            print("  Sử dụng cài đặt mặc định (rỗng).")
    return {}

def save_settings_to_file(settings_data, settings_file_path):
    """Lưu cài đặt vào file JSON được chỉ định."""
    _ensure_data_directory_main() # Đảm bảo thư mục data tồn tại trước khi ghi
    try:
        with open(settings_file_path, 'w', encoding='utf-8') as f:
            json.dump(settings_data, f, indent=4, ensure_ascii=False)
    except IOError as e:
        print(f"Lỗi: Không thể lưu file cài đặt ({settings_file_path}): {e}")


def download_file_with_progress(url, destination_path, progress_callback=None, proxy_url: str | None = None):
    """
    Tải file từ URL và lưu vào destination_path.
    progress_callback(downloaded_bytes, total_bytes) là hàm tùy chọn để nhận thông tin tiến trình.
    """
    try:
        safe_proxy_url = _normalize_proxy_url(proxy_url) if proxy_url else None  # [ZERO-LEAK-FIX]
        if proxy_url and not safe_proxy_url:
            print("Lỗi: Proxy được yêu cầu nhưng URL không hợp lệ. Dừng tải để tránh lộ IP.")
            return False  # [ZERO-LEAK-FIX]

        headers = {'User-Agent': USER_AGENT}  # [ZERO-LEAK-FIX]
        req = urllib.request.Request(url, headers=headers)

        # << KHỐI MÃ SỬA ĐỔI ĐỂ BỎ QUA KIỂM TRA SSL >>
        handlers = []
        # 1. Thêm proxy handler nếu có
        if safe_proxy_url:
            proxy_handler = urllib.request.ProxyHandler({'http': safe_proxy_url, 'https': safe_proxy_url})
            handlers.append(proxy_handler)

        # 2. Tạo và thêm HTTPS handler bỏ qua xác thực SSL
        # Đây là mấu chốt để sửa lỗi CERTIFICATE_VERIFY_FAILED
        ssl_context = ssl._create_unverified_context()
        https_handler = urllib.request.HTTPSHandler(context=ssl_context)
        handlers.append(https_handler)
        
        # 3. Build opener với tất cả các handler cần thiết
        opener = urllib.request.build_opener(*handlers)
        # << KẾT THÚC KHỐI MÃ SỬA ĐỔI >>

        with opener.open(req) as response:
            if response.status != 200:
                print(f"Lỗi: Máy chủ trả về mã trạng thái {response.status} cho URL {url}")
                return False

            total_length_header = response.getheader('content-length')
            total_length = 0
            if total_length_header:
                try:
                    total_length = int(total_length_header)
                    # print(f"  Kích thước file: {total_length / (1024*1024):.2f} MB")
                except ValueError:
                    print(f"Cảnh báo: không thể đọc kích thước file từ header: {total_length_header}")

            with open(destination_path, 'wb') as out_file:
                # Tăng kích thước bộ đệm (chunk size) để cải thiện tốc độ tải
                # 8192 bytes (8KB) là quá nhỏ, gây ra nhiều lệnh đọc/ghi
                block_size = 1024 * 1024 # 1MB
                downloaded_length = 0
                # print("  Tiến trình tải xuống:") # Bỏ bớt log
                while True:
                    buffer = response.read(block_size)
                    if not buffer:
                        break
                    out_file.write(buffer)
                    downloaded_length += len(buffer)
                    if progress_callback:
                        progress_callback(downloaded_length, total_length)
                    else: 
                        if total_length > 0:
                            percent = downloaded_length * 100.0 / total_length
                            bar_length = 40
                            filled_len = int(bar_length * downloaded_length // total_length)
                            bar = '█' * filled_len + '-' * (bar_length - filled_len)
                            sys.stdout.write(f'\r  |{bar}| {percent:.1f}% Hoàn thành')
                            sys.stdout.flush()
                if not progress_callback: 
                    sys.stdout.write('\n')
        # print(f"Thông báo: Đã lưu file vào: {destination_path}") # Bỏ bớt log
        return True
    except urllib.error.HTTPError as e:
        print(f"Lỗi HTTP khi tải file {url}: {e.code} {e.reason}")
    except urllib.error.URLError as e:
        print(f"Lỗi URL khi tải file {url}: {e.reason} (Kiểm tra kết nối internet hoặc URL)")
    except OSError as e:
        print(f"Lỗi OS khi lưu file {destination_path}: {e}")
    except Exception as e:
        print(f"Lỗi không mong muốn khi tải file {url}: {e}")
    return False

def find_or_download_yt_dlp(status_callback=print, progress_callback_for_downloader=None, proxy_url: str | None = None):
    """
    Tìm kiếm yt-dlp trong PATH hoặc thư mục cục bộ. Nếu không tìm thấy, sẽ tải về.
    status_callback(message) là hàm để gửi thông báo trạng thái.
    progress_callback_for_downloader được truyền cho download_file_with_progress.
    Trả về đường dẫn đến yt-dlp nếu thành công, None nếu thất bại.
    """
    global YT_DLP_CMD_TO_USE
    if YT_DLP_CMD_TO_USE and os.path.exists(YT_DLP_CMD_TO_USE): # Kiểm tra thêm xem path còn tồn tại không
        return YT_DLP_CMD_TO_USE

    system = platform.system()
    local_yt_dlp_filename = "yt-dlp.exe" if system == "Windows" else "yt-dlp"
    # Lấy đường dẫn tuyệt đối để log và sử dụng cho chính xác
    local_yt_dlp_exe_path = os.path.abspath(os.path.join(LOCAL_YT_DLP_SUBDIR, local_yt_dlp_filename))

    # ƯU TIÊN 1: KIỂM TRA THƯ MỤC CỤC BỘ TRƯỚC
    if not os.path.exists(LOCAL_YT_DLP_SUBDIR):
        try:
            os.makedirs(LOCAL_YT_DLP_SUBDIR)
        except OSError as e:
            status_callback(f"Lỗi nghiêm trọng: Không thể tạo thư mục '{LOCAL_YT_DLP_SUBDIR}'. Chi tiết: {e}")
            return None

    if os.path.exists(local_yt_dlp_exe_path):
        if system != "Windows" and not os.access(local_yt_dlp_exe_path, os.X_OK):
            status_callback(f"Thông báo: Cấp quyền thực thi cho yt-dlp cục bộ tại: {local_yt_dlp_exe_path}")
            try:
                os.chmod(local_yt_dlp_exe_path, 0o755)
            except Exception as e:
                status_callback(f"Cảnh báo: Không thể cấp quyền thực thi cho {local_yt_dlp_exe_path}. Chi tiết: {e}")
        try:
            process = subprocess.Popen(
                [local_yt_dlp_exe_path, '--version'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if system == "Windows" else 0
            )
            stdout, _ = process.communicate(timeout=10)
            if process.returncode == 0:
                status_callback(f"Thông báo: Tìm thấy yt-dlp cục bộ hợp lệ tại '{local_yt_dlp_exe_path}'. Phiên bản: {stdout.strip()}")
                YT_DLP_CMD_TO_USE = local_yt_dlp_exe_path
                return YT_DLP_CMD_TO_USE
            else:
                status_callback(f"Cảnh báo: yt-dlp cục bộ tại {local_yt_dlp_exe_path} bị lỗi. Sẽ thử tìm trong PATH hoặc tải lại.")
        except Exception as e:
            status_callback(f"Lỗi khi chạy yt-dlp cục bộ {local_yt_dlp_exe_path}: {e}. Sẽ thử tìm trong PATH hoặc tải lại.")

    # ƯU TIÊN 2: KIỂM TRA TRONG PATH HỆ THỐNG (NẾU CỤC BỘ KHÔNG CÓ)
    system_yt_dlp_path = shutil.which('yt-dlp')
    if system_yt_dlp_path:
        try:
            process = subprocess.Popen(
                [system_yt_dlp_path, '--version'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            )
            stdout, _ = process.communicate(timeout=10)
            if process.returncode == 0:
                status_callback(f"Thông báo: Tìm thấy yt-dlp trong PATH hệ thống tại '{system_yt_dlp_path}'. Phiên bản: {stdout.strip()}")
                YT_DLP_CMD_TO_USE = system_yt_dlp_path
                return YT_DLP_CMD_TO_USE
        except Exception as e:
            status_callback(f"Lỗi khi kiểm tra yt-dlp trong PATH tại '{system_yt_dlp_path}': {e}")
    
    # ƯU TIÊN 3: TẢI VỀ PHIÊN BẢN MỚI (NẾU CẢ 2 NƠI TRÊN ĐỀU KHÔNG CÓ)
    status_callback(f"Thông báo: Không tìm thấy yt-dlp hợp lệ, sẽ tải phiên bản mới về '{local_yt_dlp_exe_path}'...")

    # ĐÃ XÓA KHỐI LỆNH TỰ ĐỘNG XÓA FILE CŨ/LỖI TẠI ĐÂY
    # Việc tải file mới sẽ tự động ghi đè nếu cần thiết.
    # if os.path.exists(local_yt_dlp_exe_path):
    #     try: 
    #         os.remove(local_yt_dlp_exe_path)
    #         ...
    #     except Exception as e_rem: 
    #         ...

    if not os.path.exists(LOCAL_YT_DLP_SUBDIR):
        try:
            os.makedirs(LOCAL_YT_DLP_SUBDIR)
            # status_callback(f"Thông báo: Đã tạo thư mục: {LOCAL_YT_DLP_SUBDIR}") # Bỏ bớt log
        except OSError as e:
            status_callback(f"Lỗi nghiêm trọng: Không thể tạo thư mục '{LOCAL_YT_DLP_SUBDIR}'. Chi tiết: {e}")
            return None

    if os.path.exists(local_yt_dlp_exe_path):
        if system != "Windows" and not os.access(local_yt_dlp_exe_path, os.X_OK):
            status_callback(f"Thông báo: yt-dlp cục bộ ({local_yt_dlp_exe_path}) chưa có quyền thực thi. Đang cấp quyền...")
            try:
                os.chmod(local_yt_dlp_exe_path, 0o755)
            except Exception as e:
                status_callback(f"Cảnh báo: Không thể cấp quyền thực thi cho {local_yt_dlp_exe_path}. Chi tiết: {e}")

        try:
            process = subprocess.Popen(
                [local_yt_dlp_exe_path, '--version'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if system == "Windows" else 0
            )
            stdout, _ = process.communicate(timeout=10)
            if process.returncode == 0:
                status_callback(f"Thông báo: Tìm thấy yt-dlp cục bộ hợp lệ. Phiên bản: {stdout.strip()}")
                YT_DLP_CMD_TO_USE = local_yt_dlp_exe_path
                return YT_DLP_CMD_TO_USE
            else:
                status_callback(f"Cảnh báo: yt-dlp cục bộ tại {local_yt_dlp_exe_path} không hoạt động đúng. Sẽ thử tải lại.")
                try: os.remove(local_yt_dlp_exe_path)
                except Exception as e_rem: status_callback(f"Cảnh báo: Không thể xóa file lỗi {local_yt_dlp_exe_path}: {e_rem}")
        except subprocess.TimeoutExpired:
            status_callback(f"Cảnh báo: Lệnh '{local_yt_dlp_exe_path} --version' bị treo. Sẽ thử tải lại.")
            try: os.remove(local_yt_dlp_exe_path)
            except Exception as e_rem: status_callback(f"Cảnh báo: Không thể xóa file lỗi {local_yt_dlp_exe_path}: {e_rem}")
        except Exception as e:
            status_callback(f"Lỗi khi chạy yt-dlp cục bộ {local_yt_dlp_exe_path}: {e}. Sẽ thử tải lại.")
            try: os.remove(local_yt_dlp_exe_path)
            except Exception as e_rem: status_callback(f"Cảnh báo: Không thể xóa file lỗi {local_yt_dlp_exe_path}: {e_rem}")
    
    status_callback("Thông báo: Bắt đầu quá trình tải yt-dlp tự động...")
    machine = platform.machine().lower()
    github_asset_name = ""

    if system == "Windows":
        github_asset_name = "yt-dlp.exe"
    elif system == "Darwin": # macOS
        github_asset_name = "yt-dlp_macos"
    elif system == "Linux":
        if "aarch64" in machine or "arm64" in machine:
            github_asset_name = "yt-dlp_linux_aarch64"
        elif "x86_64" in machine or "amd64" in machine:
            github_asset_name = "yt-dlp" 
        else: 
            github_asset_name = "yt-dlp"
            status_callback(f"Cảnh báo: Kiến trúc Linux không xác định rõ ({machine}), thử tải file 'yt-dlp' chung.")
    else:
        status_callback(f"Lỗi nghiêm trọng: Hệ điều hành {system} ({machine}) không được hỗ trợ tự động tải yt-dlp.")
        return None

    if not github_asset_name:
        status_callback(f"Lỗi nghiêm trọng: Không thể xác định file yt-dlp phù hợp cho {system} ({machine}).")
        return None

    download_url = f"https://github.com/yt-dlp/yt-dlp/releases/latest/download/{github_asset_name}"
    status_callback(f"Thông báo: Đang tải {github_asset_name} từ {download_url}")

    if download_file_with_progress(download_url, local_yt_dlp_exe_path, progress_callback_for_downloader, proxy_url):
        status_callback("Thông báo: Tải xuống yt-dlp thành công.")
        if system != "Windows":
            status_callback(f"Thông báo: Đang cấp quyền thực thi cho {local_yt_dlp_exe_path}...")
            try:
                os.chmod(local_yt_dlp_exe_path, 0o755) 
            except Exception as e:
                status_callback(f"Lỗi: Không thể cấp quyền thực thi cho {local_yt_dlp_exe_path}. Chi tiết: {e}")
        try:
            process = subprocess.Popen(
                [local_yt_dlp_exe_path, '--version'],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                creationflags=subprocess.CREATE_NO_WINDOW if system == "Windows" else 0
            )
            stdout, _ = process.communicate(timeout=10)
            if process.returncode == 0:
                status_callback(f"Thông báo: yt-dlp vừa tải về hoạt động tốt. Phiên bản: {stdout.strip()}")
                YT_DLP_CMD_TO_USE = local_yt_dlp_exe_path
                return YT_DLP_CMD_TO_USE
            else:
                status_callback("Lỗi nghiêm trọng: yt-dlp vừa tải về không hoạt động đúng cách (--version thất bại).")
                return None
        except subprocess.TimeoutExpired:
             status_callback("Lỗi: Lệnh xác minh yt-dlp vừa tải về bị treo.")
             return None
        except Exception as e:
            status_callback(f"Lỗi nghiêm trọng khi xác minh yt-dlp vừa tải về: {e}")
            return None
    else:
        status_callback(f"Lỗi nghiêm trọng: Tải xuống yt-dlp từ {download_url} thất bại.")
        if os.path.exists(local_yt_dlp_exe_path): 
            try: os.remove(local_yt_dlp_exe_path)
            except Exception as e_rem: status_callback(f"Cảnh báo: Không thể xóa file tải lỗi {local_yt_dlp_exe_path}: {e_rem}")
        return None

def download_youtube_video_logic(video_url, output_directory, yt_dlp_executable_path,
                                 quality_preference="bv*[height<=1080]+ba/b[height<=1080] / bv*+ba/b",
                                 process_output_callback=None):
    """
    Logic tải video sử dụng yt-dlp.
    Trả về (bool: thành công, str: thông báo cuối cùng, str: đường dẫn file đã tải (nếu có)).
    """
    print("-" * 60)
    downloaded_file_path = None # Khởi tạo
    final_video_title_from_log = None # Để lưu tên file từ log

    if not video_url or not video_url.strip():
        message = "Lỗi: URL video không được để trống."
        print(message)
        print("-" * 60)
        return False, message, None

    # ... (các kiểm tra output_directory, yt_dlp_executable_path giữ nguyên) ...
    if not output_directory or not output_directory.strip():
        message = "Lỗi: Thư mục lưu trữ không được để trống."
        print(message)
        print("-" * 60)
        return False, message, None

    abs_output_directory = os.path.abspath(output_directory)
    try:
        if not os.path.exists(abs_output_directory):
            os.makedirs(abs_output_directory)
            # print(f"Thông báo: Đã tạo thư mục lưu trữ: {abs_output_directory}") # Bỏ bớt log
        elif not os.path.isdir(abs_output_directory):
            message = f"Lỗi: '{abs_output_directory}' tồn tại nhưng không phải thư mục."
            print(message)
            print("-" * 60)
            return False, message, None
    except OSError as e:
        message = f"Lỗi: Không thể tạo/truy cập thư mục '{abs_output_directory}': {e}"
        print(message)
        print("-" * 60)
        return False, message, None

    if not yt_dlp_executable_path:
        message = "Lỗi nghiêm trọng: Đường dẫn yt-dlp không được cung cấp."
        print(message)
        print("-" * 60)
        return False, message, None

    # print(f"Thông báo: Sẽ sử dụng yt-dlp tại: {yt_dlp_executable_path}") # Bỏ bớt log
    # Sử dụng %(title).200B để giới hạn byte, nhưng vẫn giữ lại tên file đầy đủ cho trường hợp không restrict
    # Thay đổi output_template để lấy tên file dễ dự đoán hơn, đặc biệt khi không dùng --restrict-filenames
    # yt-dlp sẽ tự xử lý các ký tự không hợp lệ.
    # Ta sẽ cố gắng parse tên file từ output log của yt-dlp.
    output_template_pattern = '%(title)s.%(ext)s' # Không giới hạn độ dài ở đây
    output_template_path = os.path.join(abs_output_directory, output_template_pattern)


    command = [
        yt_dlp_executable_path,
        '-o', output_template_path, # Đường dẫn đầy đủ với template
        '--no-playlist',
        # '--restrict-filenames', # Đã loại bỏ để hỗ trợ tên tiếng Việt
        '--merge-output-format', 'mp4', # Đảm bảo output là mp4 nếu có merge
        '--progress',
        '--no-colors',
        # '--print', 'filename', # Có thể dùng cờ này để yt-dlp in ra đường dẫn cuối cùng
                                 # Tuy nhiên, nó có thể in nhiều lần nếu có các file trung gian
                                 # Việc parse từ log "[Merger] Merging formats into" hoặc "[download] Destination" vẫn tốt hơn
    ]
    command.extend(get_yt_dlp_js_runtime_args())
    if quality_preference:
        command.extend(['-f', quality_preference])
    command.append(video_url)

    # print(f"\nThông báo: Đang thực thi lệnh: {' '.join(command)}") # Bỏ bớt log
    print("Thông báo: Quá trình tải xuống có thể mất vài phút...")
    if not process_output_callback:
        print("--- BẮT ĐẦU LOG TỪ YT-DLP ---")

    success = False
    final_message = ""
    process = None
    captured_stderr = [] # Để bắt lỗi nếu có

    try:
        creation_flags = 0
        if platform.system() == "Windows":
            creation_flags = subprocess.CREATE_NO_WINDOW

        process = subprocess.Popen(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, # Tách stderr ra để kiểm tra lỗi dễ hơn
            text=True,
            encoding='utf-8',
            errors='replace',
            bufsize=1,
            creationflags=creation_flags
        )

        # Xử lý stdout (log tiến trình, tên file)
        if process.stdout:
            for line in iter(process.stdout.readline, ''):
                if process_output_callback:
                    process_output_callback(line)
                else:
                    sys.stdout.write(line)
                    sys.stdout.flush()

                # Cố gắng parse tên file từ log (ưu tiên dòng Merger)
                merger_match = re.search(r"\[Merger\] Merging formats into \"(.+?)\"", line)
                if merger_match:
                    # Đường dẫn có thể tương đối với thư mục làm việc của yt-dlp (thường là thư mục output)
                    # hoặc tuyệt đối. Chúng ta nên join với abs_output_directory để chắc chắn.
                    potential_filename = os.path.basename(merger_match.group(1))
                    downloaded_file_path = os.path.join(abs_output_directory, potential_filename)
                    # print(f"\n[DEBUG] Parsed from Merger: {downloaded_file_path}")

                # Nếu không có Merger, thử parse từ Destination (ít ưu tiên hơn)
                if not downloaded_file_path:
                    dest_match = re.search(r"\[download\] Destination:\s*(.+)", line)
                    if dest_match:
                        # Tên file này có thể chưa có extension đúng nếu có merge sau đó
                        # và nó không bao gồm thư mục output.
                        potential_filename_base = os.path.basename(dest_match.group(1).strip())
                        # Thử ghép với output_directory và tìm file có extension là mp4
                        # Điều này không hoàn toàn chính xác, nhưng là một nỗ lực
                        # Tốt hơn là dựa vào dòng Merger nếu có.
                        # Lưu lại title từ đây để có thể dùng để đoán tên file nếu cần
                        if not final_video_title_from_log:
                             title_part_match = re.match(r"(.+?)\s+\[.+?\]\..+", potential_filename_base)
                             if title_part_match:
                                 final_video_title_from_log = title_part_match.group(1)


            process.stdout.close()

        # Xử lý stderr (bắt lỗi)
        if process.stderr:
            for line in iter(process.stderr.readline, ''):
                captured_stderr.append(line)
                if process_output_callback: # Gửi cả lỗi qua callback nếu có
                    process_output_callback(f"STDERR: {line}")
                else:
                    sys.stderr.write(line) # In lỗi ra console
                    sys.stderr.flush()
            process.stderr.close()

        process.wait()

        # Sau khi process kết thúc, kiểm tra lại downloaded_file_path
        # Nếu downloaded_file_path vẫn là None và tải thành công, thử đoán tên file
        if process.returncode == 0 and not downloaded_file_path:
            print("\nCảnh báo: Không parse được tên file từ log Merger/Destination.")
            print("  Sẽ cố gắng tìm file đã tải trong thư mục output...")
            # Thử tìm file .mp4 mới nhất hoặc file khớp với title (nếu parse được title)
            # Đây là phần nâng cao hơn, tạm thời có thể bỏ qua và dựa vào việc yt-dlp tự đặt tên
            # Nếu dùng cờ --print filename, output của nó sẽ là đường dẫn tuyệt đối
            # Tuy nhiên, nếu không dùng --restrict-filenames, output_template_pattern sẽ giúp yt-dlp tạo tên đúng.
            # Chúng ta cần một cách chắc chắn hơn để lấy tên file.
            # Cách đơn giản nhất là listdir và tìm file khớp với một phần của URL hoặc title.

            # DỰ ĐOÁN TÊN FILE DỰA TRÊN OUTPUT TEMPLATE VÀ TITLE (nếu có)
            # Điều này chỉ hoạt động tốt nếu không có ký tự đặc biệt nào được yt-dlp thay thế
            # mà không được dự đoán trước.
            video_id_match = re.search(r"(?:v=|/embed/|/v/|youtu\.be/)([^#&?]{11})", video_url)
            video_id = video_id_match.group(1) if video_id_match else "unknown_id"

            if final_video_title_from_log: # Ưu tiên title parse từ log
                potential_filename_from_title = f"{final_video_title_from_log} [{video_id}].mp4"
                guessed_path = os.path.join(abs_output_directory, potential_filename_from_title)
                if os.path.exists(guessed_path):
                    downloaded_file_path = guessed_path
                    print(f"  Đoán tên file thành công (dựa trên title log): {downloaded_file_path}")
                else: # Thử làm sạch title hơn nữa (loại bỏ ký tự không an toàn thường gặp)
                    # Đây là một phỏng đoán rất thô sơ
                    import string
                    safe_chars = "-_.() %s%s" % (string.ascii_letters, string.digits)
                    cleaned_title = ''.join(c for c in final_video_title_from_log if c in safe_chars or ord(c) >= 128).strip()
                    cleaned_title = cleaned_title[:180] # Giới hạn độ dài
                    potential_filename_cleaned = f"{cleaned_title} [{video_id}].mp4"
                    guessed_path_cleaned = os.path.join(abs_output_directory, potential_filename_cleaned)
                    if os.path.exists(guessed_path_cleaned):
                        downloaded_file_path = guessed_path_cleaned
                        print(f"  Đoán tên file thành công (dựa trên title log đã làm sạch): {downloaded_file_path}")
                    else:
                        print(f"  Không tìm thấy file dự đoán: {guessed_path} hoặc {guessed_path_cleaned}")
            else: # Nếu không parse được title từ log, thử cách khác (ví dụ: tìm file .mp4 mới nhất - phức tạp hơn)
                print("  Không có title từ log để đoán tên file.")


        if process.returncode == 0:
            if downloaded_file_path and os.path.exists(downloaded_file_path):
                final_message = f"Thành công! Video đã được tải xuống: {downloaded_file_path}"
                success = True
            elif not downloaded_file_path:
                final_message = f"Thành công! Video dường như đã được tải vào '{abs_output_directory}', nhưng không thể xác định tên file chính xác."
                success = True # Vẫn coi là thành công về mặt tải
            else: # có downloaded_file_path nhưng file không tồn tại
                final_message = f"Lỗi: yt-dlp báo thành công nhưng file '{downloaded_file_path}' không tìm thấy."
                success = False
                downloaded_file_path = None # Reset vì file không tồn tại
        else:
            error_log_summary = "".join(captured_stderr[-5:]) # Lấy 5 dòng lỗi cuối
            final_message = f"Lỗi: yt-dlp không thể tải video. Mã lỗi: {process.returncode}.\nChi tiết lỗi (có thể có):\n{error_log_summary.strip()}"
            success = False
            downloaded_file_path = None # Reset vì tải lỗi

        print(f"\n{final_message}")

    except FileNotFoundError:
        final_message = f"Lỗi nghiêm trọng: Lệnh '{yt_dlp_executable_path}' không thể thực thi (FileNotFoundError)."
        print(f"\n{final_message}")
        downloaded_file_path = None
    except OSError as e:
        final_message = f"Lỗi hệ thống khi cố gắng thực thi '{yt_dlp_executable_path}': {e}"
        print(f"\n{final_message}")
        downloaded_file_path = None
    except Exception as e:
        final_message = f"Lỗi không mong muốn đã xảy ra trong quá trình tải video: {e}"
        print(f"\n{final_message}")
        downloaded_file_path = None
    finally:
        if process and process.poll() is None:
            print("Cảnh báo: Tiến trình yt-dlp có thể chưa kết thúc đúng cách. Thử dừng.")
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()

        if not process_output_callback:
            print("--- KẾT THÚC LOG TỪ YT-DLP ---")
        print("-" * 60)

    return success, final_message, downloaded_file_path

def get_local_yt_dlp_version(yt_dlp_path: str) -> str | None:
    """
    Lấy chuỗi phiên bản từ một file thực thi yt-dlp cụ thể.
    Trả về chuỗi phiên bản nếu thành công, None nếu có lỗi.
    """
    if not yt_dlp_path or not os.path.exists(yt_dlp_path):
        return None
    try:
        process = subprocess.Popen(
            [yt_dlp_path, '--version'],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            encoding='utf-8', errors='replace',
            creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
        )
        stdout, stderr = process.communicate(timeout=10)
        if process.returncode == 0 and stdout and re.match(r'\d{4}\.\d{2}\.\d{2}', stdout.strip()):
            return stdout.strip()
        else:
            print(f"Lỗi khi lấy phiên bản yt-dlp: {stderr.strip()}")
            return None
    except Exception as e:
        print(f"Lỗi ngoại lệ khi lấy phiên bản yt-dlp: {e}")
        return None

def update_yt_dlp_executable(status_callback=print, progress_callback=None, proxy_url: str | None = None) -> bool:
    """Update yt-dlp atomically and repair the bundled Node runtime when needed."""
    if platform.system() != "Windows":
        status_callback("Lỗi: Cơ chế runtime portable hiện chỉ hỗ trợ Windows x64.")
        return False

    status_callback("Đang kiểm tra Node portable...")
    manager = UpdateManager(
        base_dir=SCRIPT_BASE_DIR,
        repo_owner=GITHUB_OWNER,
        repo_name=GITHUB_REPO,
        status_callback=status_callback,
        progress_callback=progress_callback,
        proxy_url=_normalize_proxy_url(proxy_url),
    )
    result = manager.update_yt_dlp()
    if not result.success:
        status_callback(f"{result.message}: {result.error}")
        return False

    changed = ", ".join(result.changed_components)
    status_callback(f"Hoàn tất cập nhật {changed}. Phiên bản yt-dlp: {result.new_version}")
    global YT_DLP_CMD_TO_USE
    YT_DLP_CMD_TO_USE = None
    return True
# --- Hàm Main cho phiên bản Console (nếu script này được chạy trực tiếp) ---
if __name__ == "__main__":
    print("--- CHƯƠNG TRÌNH TẢI VIDEO YOUTUBE (CONSOLE MODE) ---")

    # Khởi tạo đường dẫn FFmpeg (cho video_verifier)
    if video_verifier:
        ff_paths = video_verifier.initialize_ffmpeg_paths()
        if not ff_paths[0]: # ffprobe_path
            print("CẢNH BÁO: ffprobe không tìm thấy. Tính năng xác minh video sẽ không hoạt động.")
            print("  Hãy đặt ffmpeg (bao gồm ffprobe) vào thư mục 'data/ffmpeg/bin' hoặc trong PATH hệ thống.")
        else:
            print(f"Thông báo: ffprobe sẵn sàng tại: {ff_paths[0]}")

    # ... (phần còn lại của main giữ nguyên logic hỏi URL, thư mục) ...
    current_settings = load_settings_from_file(CONSOLE_SETTINGS_FILE_PATH)
    last_output_directory = current_settings.get("last_output_directory")

    yt_dlp_path = find_or_download_yt_dlp(status_callback=print)
    if not yt_dlp_path:
        print("Lỗi nghiêm trọng: Không thể tìm thấy hoặc cài đặt yt-dlp. Không thể tiếp tục.")
        input("Nhấn Enter để thoát.")
        sys.exit(1)

    fallback_default_dir = os.path.join(get_script_directory(), "TaiVeYouTube_Console")
    actual_default_to_use = fallback_default_dir

    if last_output_directory:
        if os.path.isdir(last_output_directory):
            actual_default_to_use = last_output_directory
            prompt_message = f"Nhập thư mục lưu (Enter để dùng lần trước: '{actual_default_to_use}'): "
        else:
            print(f"Cảnh báo: Thư mục đã lưu lần trước ('{last_output_directory}') không còn hợp lệ.")
            prompt_message = f"Nhập thư mục lưu (Enter để dùng mặc định: '{actual_default_to_use}'): "
    else:
        prompt_message = f"Nhập thư mục lưu (Enter để dùng mặc định: '{actual_default_to_use}'): "

    video_url_input = input("Nhập URL video YouTube bạn muốn tải: ").strip()
    output_directory_input = input(prompt_message).strip()

    if not output_directory_input:
        output_directory_input = actual_default_to_use

    chosen_output_dir_abs = os.path.abspath(output_directory_input)
    print(f"Thông báo: Video sẽ được thử lưu vào: {chosen_output_dir_abs}")
    quality = "bv[height=1080][ext=mp4]+ba[ext=m4a]/bv[height=720][ext=mp4]+ba[ext=m4a]/b[height<=1080][ext=mp4]/bv*+ba/b" # Ưu tiên 1080p, fallback 720p

    # Gọi hàm tải và nhận thêm downloaded_file_actual_path
    success, final_dl_message, downloaded_file_actual_path = download_youtube_video_logic(
        video_url_input, chosen_output_dir_abs, yt_dlp_path, quality_preference=quality
    )

    if success and downloaded_file_actual_path and video_verifier and video_verifier.FFPROBE_CMD_TO_USE:
        print("\n--- Bắt đầu kiểm tra hậu kỳ file video ---")
        verification_result = video_verifier.verify_video_file(downloaded_file_actual_path)
        print("--- Kết quả kiểm tra hậu kỳ ---")
        if verification_result.success and verification_result.file_readable:
            print(f"  Trạng thái file: OK (Đọc được bởi ffprobe)")
            if verification_result.verified_duration is not None:
                # Chuyển đổi giây thành HH:MM:SS
                secs = int(verification_result.verified_duration)
                verified_duration_str = f"{secs // 3600:02d}:{(secs % 3600) // 60:02d}:{secs % 60:02d}"
                print(f"  Thời lượng (từ file): {verified_duration_str} ({verification_result.verified_duration:.2f}s)")
            if verification_result.verified_title:
                print(f"  Tiêu đề (từ file): {verification_result.verified_title}")
            print(f"  Có stream video: {'Có' if verification_result.video_stream_exists else 'Không'}")
            print(f"  Có stream audio: {'Có' if verification_result.audio_stream_exists else 'Không'}")
            if not verification_result.video_stream_exists and not verification_result.audio_stream_exists:
                 print("  CẢNH BÁO: File không có stream video hoặc audio.")
        elif verification_result.error_message:
            print(f"  Lỗi kiểm tra file: {verification_result.error_message}")
        else:
            print("  Không thể xác minh file hoặc file có vấn đề.")
        print("-" * 30)
    elif success and downloaded_file_actual_path and (not video_verifier or not video_verifier.FFPROBE_CMD_TO_USE):
        print("\nThông báo: Tải thành công, nhưng không thể thực hiện kiểm tra hậu kỳ (ffprobe không sẵn sàng).")


    if success: # Chỉ lưu thư mục nếu tải thành công (yt-dlp báo thành công)
        current_settings["last_output_directory"] = chosen_output_dir_abs
        save_settings_to_file(current_settings, CONSOLE_SETTINGS_FILE_PATH)
        # print(f"Thông báo: Đã lưu '{chosen_output_dir_abs}' làm thư mục tải về cho lần sau (console).") # Bớt log

    input("\nQuá trình hoàn tất. Nhấn Enter để thoát chương trình.")
