# url_handler.py
import re
import subprocess
import platform
import json
import os
import main_logic
import urllib.parse # Thêm thư viện để mã hóa URL

# Định nghĩa các loại URL
URL_TYPE_VIDEO = "video"
URL_TYPE_PLAYLIST = "playlist"
URL_TYPE_CHANNEL = "channel"
URL_TYPE_UNKNOWN = "unknown"

# Regex cho các URL YouTube tiêu chuẩn
YOUTUBE_VIDEO_PATTERNS = [
    re.compile(r"(?i)https?://(?:www\.)?(?:youtube\.com/(?:watch\?v=|embed/|v/)|youtu\.be/)([\w-]+)"),
]
YOUTUBE_PLAYLIST_PATTERN = re.compile(r"(?i)https?://(?:www\.)?youtube\.com/playlist\?list=([\w-]{2,})")
YOUTUBE_CHANNEL_PATTERNS = [
    re.compile(r"(?i)https?://(?:www\.)?youtube\.com/channel/(UC[\w-]{22}[\w-])(?:/(videos|playlists|streams|community|about|featured))?/?$"),
    re.compile(r"(?i)https?://(?:www\.)?youtube\.com/user/([\w.-]+)(?:/(videos|playlists|streams|community|about|featured))?/?$"),
    re.compile(r"(?i)https?://(?:www\.)?youtube\.com/c/([\w.-]+)(?:/(videos|playlists|streams|community|about|featured))?/?$"),
    re.compile(r"(?i)https?://(?:www\.)?youtube\.com/@([\w.-]+)(?:/(videos|playlists|streams|community|about|featured))?/?$"),
]

def get_url_type_and_id(url_string):
    """
    Xác định loại URL và ID/Identifier từ một chuỗi URL.
    LƯU Ý: Các pattern regex hiện tại chỉ hỗ trợ URL YouTube tiêu chuẩn.
    Các định dạng URL khác (ví dụ: googleusercontent.com) có thể không được nhận dạng đúng.
    """
    if not url_string or not url_string.strip().startswith("http"):
        return URL_TYPE_UNKNOWN, None, url_string

    match = YOUTUBE_PLAYLIST_PATTERN.search(url_string)
    if match:
        playlist_id = match.group(1)
        return URL_TYPE_PLAYLIST, playlist_id, url_string

    for pattern in YOUTUBE_CHANNEL_PATTERNS:
        match = pattern.search(url_string)
        if match:
            channel_identifier = None
            for group_val in match.groups():
                if group_val:
                    channel_identifier = group_val
                    break
            if not channel_identifier and len(match.groups()) > 0 and match.group(1):
                channel_identifier = match.group(1)
            return URL_TYPE_CHANNEL, channel_identifier or url_string, url_string

    for pattern in YOUTUBE_VIDEO_PATTERNS:
        match = pattern.search(url_string)
        if match:
            return URL_TYPE_VIDEO, match.group(1), url_string

    # Nếu không khớp với bất kỳ pattern YouTube tiêu chuẩn nào
    print(f"[get_url_type_and_id] WARN: URL '{url_string}' không khớp với các pattern YouTube tiêu chuẩn. Phân loại là UNKNOWN.")
    return URL_TYPE_UNKNOWN, None, url_string

class YTdlpInfoFetcher:
    def __init__(self, yt_dlp_path, cookies_options=None, proxy_url: str | None = None):
        self.yt_dlp_path = yt_dlp_path
        self.cookies_options = cookies_options if cookies_options else [] # Đảm bảo là list
        self._process = None
        self.proxy_url = proxy_url

    def _encode_url_for_cli(self, url_string): # Hiện tại không dùng, nhưng để lại phòng khi cần
        parsed_url = urllib.parse.urlparse(url_string)
        encoded_query = urllib.parse.quote(parsed_url.query, safe='=&%')
        reconstructed_url = urllib.parse.urlunparse(
            (parsed_url.scheme, parsed_url.netloc, parsed_url.path,
             parsed_url.params, encoded_query, parsed_url.fragment)
        )
        return reconstructed_url

    def get_playlist_item_urls(self, playlist_or_channel_url, log_callback=print):
        if not self.yt_dlp_path or not os.path.exists(self.yt_dlp_path):
            log_callback(f"Lỗi: Đường dẫn yt-dlp ('{self.yt_dlp_path}') không hợp lệ.")
            return []

        urls = []
        command = [
            self.yt_dlp_path,
            '--flat-playlist',
            '--print', 'webpage_url',
            '--ignore-errors', # Bỏ qua lỗi cho từng video khi lấy danh sách URL
            '--no-warnings',
        ]
        command.extend(main_logic.get_yt_dlp_js_runtime_args())
        if self.proxy_url:
            command.extend(['--proxy', self.proxy_url])
        if self.cookies_options:
            command.extend(self.cookies_options)
        command.append(playlist_or_channel_url)

        log_callback(f"Đang chạy lệnh lấy danh sách video: {' '.join(command)}")
        try:
            if not os.access(self.yt_dlp_path, os.X_OK) and platform.system() != "Windows":
                 log_callback(f"Cảnh báo: File yt-dlp tại '{self.yt_dlp_path}' không có quyền thực thi.")

            self._process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            )
            stdout, stderr = self._process.communicate(timeout=120)

            if self._process.returncode == 0:
                raw_urls = [line.strip() for line in stdout.splitlines() if line.strip()]
                for u in raw_urls:
                    url_type, _, _ = get_url_type_and_id(u) # Kiểm tra loại URL trả về
                    if url_type == URL_TYPE_VIDEO: # Chỉ thêm nếu là URL video hợp lệ theo định nghĩa
                        urls.append(u)
                log_callback(f"Tìm thấy {len(urls)} video hợp lệ trong '{playlist_or_channel_url}'. (Tổng số dòng output: {len(raw_urls)})")
            else:
                log_callback(f"Lỗi khi lấy danh sách video từ '{playlist_or_channel_url}' (mã lỗi: {self._process.returncode}): {stderr.strip()}")
                # Các điều kiện lỗi cụ thể hơn để tránh fallback không cần thiết
                error_lower = stderr.lower()
                if "unsupported url" in error_lower or \
                   "not a valid youtube" in error_lower or \
                   ("unable to download api page" in error_lower and "bad request" in error_lower) or \
                   "no such channel" in error_lower or \
                   "playlist id" in error_lower and ("invalid" in error_lower or "not found" in error_lower) or \
                   "private video" in error_lower or "login required" in error_lower:
                    log_callback(f"Lỗi cho thấy URL '{playlist_or_channel_url}' có thể là riêng tư, không tồn tại, không phải playlist/kênh hợp lệ hoặc có vấn đề với ID. Sẽ không fallback.")
                    return [] # Trả về danh sách rỗng
                else:
                    log_callback(f"Lỗi không rõ ràng khi lấy danh sách, sẽ thử tải URL gốc như một video đơn (có thể không thành công): {playlist_or_channel_url}")
                    return [playlist_or_channel_url] # Fallback như cũ, nhưng ít có khả năng đạt được
        except subprocess.TimeoutExpired:
            log_callback(f"Timeout khi lấy danh sách video từ '{playlist_or_channel_url}'.")
            if self._process and self._process.poll() is None: self._process.kill()
            return [playlist_or_channel_url]
        except FileNotFoundError:
            log_callback(f"Lỗi FileNotFoundError: Lệnh '{self.yt_dlp_path}' không tìm thấy.")
            return []
        except Exception as e:
            log_callback(f"Ngoại lệ khi lấy danh sách video từ '{playlist_or_channel_url}': {type(e).__name__} - {e}")
            if self._process and self._process.poll() is None : self._process.kill()
            return [playlist_or_channel_url]
        finally:
            self._process = None
        return urls

    def get_url_metadata(self, url_string, log_callback=print):
        if not self.yt_dlp_path or not os.path.exists(self.yt_dlp_path):
            log_callback(f"Lỗi: Đường dẫn yt-dlp ('{self.yt_dlp_path}') không hợp lệ.")
            return None

        command = [
            self.yt_dlp_path,
            '--dump-single-json',
            '--no-warnings',
            '--ignore-errors',  # QUAN TRỌNG: Thêm lại để bỏ qua lỗi video riêng tư trong playlist
        ]
        command.extend(main_logic.get_yt_dlp_js_runtime_args())
        if self.proxy_url:
            command.extend(['--proxy', self.proxy_url])
        if self.cookies_options:
            command.extend(self.cookies_options)
        command.append(url_string)

        log_callback(f"Đang lấy metadata JSON cho: {url_string} bằng lệnh: {' '.join(command)}")
        try:
            self._process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding='utf-8',
                errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW if platform.system() == "Windows" else 0
            )
            stdout, stderr = self._process.communicate(timeout=60)

            if self._process.returncode == 0 and stdout:
                try:
                    metadata = json.loads(stdout)
                    # Kiểm tra xem có phải là lỗi được gói trong JSON không (một số extractor làm vậy)
                    if metadata.get('_type') == 'youtube' and metadata.get('availability') == 'private' and not metadata.get('id'):
                         log_callback(f"Metadata JSON cho '{url_string}' chỉ chứa thông tin lỗi video riêng tư. Stderr: {stderr.strip()}")
                         return None # Coi như không lấy được metadata hợp lệ
                    log_callback(f"Lấy metadata JSON thành công cho '{url_string}'. _type: {metadata.get('_type')}, title: {metadata.get('title', 'N/A')}")
                    return metadata
                except json.JSONDecodeError as je:
                    log_callback(f"Lỗi parse JSON metadata cho '{url_string}': {je}\nOutput nhận được (đầu): {stdout[:500]}")
                    return None
            else:
                error_message = stderr.strip()
                if not error_message and self._process.returncode != 0:
                    error_message = f"yt-dlp exited with code {self._process.returncode}"
                # Với --ignore-errors, mã lỗi có thể là 0 ngay cả khi có lỗi nhỏ. Kiểm tra stdout.
                if not stdout and self._process.returncode == 0 : # Nếu stdout trống và mã lỗi là 0
                     log_callback(f"Lấy metadata JSON cho '{url_string}' không thành công (stdout trống, mã lỗi 0). Có thể tất cả item đều lỗi. Stderr: {error_message}")
                     return None
                log_callback(f"Lỗi hoặc cảnh báo khi lấy metadata JSON cho '{url_string}' (mã lỗi: {self._process.returncode}). Stderr: {error_message}")
                # Nếu stdout có nội dung, có thể là JSON của playlist với vài item lỗi đã bị bỏ qua
                if stdout:
                    try:
                        metadata = json.loads(stdout)
                        log_callback(f"Metadata JSON có thể không đầy đủ do lỗi, nhưng vẫn parse được cho '{url_string}'. _type: {metadata.get('_type')}, title: {metadata.get('title', 'N/A')}")
                        return metadata
                    except json.JSONDecodeError:
                        log_callback(f"Không parse được stdout dù có nội dung sau lỗi: {stdout[:500]}")
                        return None
                return None # Mặc định trả về None nếu có lỗi và không parse được stdout
        except subprocess.TimeoutExpired:
            log_callback(f"Timeout khi lấy metadata JSON cho '{url_string}'.")
            if self._process and self._process.poll() is None: self._process.kill()
            return None
        except FileNotFoundError:
            log_callback(f"Lỗi FileNotFoundError: Lệnh '{self.yt_dlp_path}' không tìm thấy khi lấy metadata.")
            return None
        except Exception as e:
            log_callback(f"Ngoại lệ khi lấy metadata JSON cho '{url_string}': {type(e).__name__} - {e}")
            if self._process and self._process.poll() is None : self._process.kill()
            return None
        finally:
            self._process = None

    def cancel_fetch(self):
        if self._process and self._process.poll() is None:
            print(f"Yêu cầu hủy tiến trình yt-dlp (PID: {self._process.pid}) của YTdlpInfoFetcher.")
            try:
                self._process.terminate()
                try:
                    self._process.wait(timeout=2)
                    print(f"Tiến trình yt-dlp (PID: {self._process.pid}) đã được terminate.")
                except subprocess.TimeoutExpired:
                    print(f"Tiến trình yt-dlp (PID: {self._process.pid}) không phản hồi terminate trong 2s, thử kill.")
                    self._process.kill()
                    self._process.wait(timeout=2)
                    print(f"Tiến trình yt-dlp (PID: {self._process.pid}) đã được kill.")
            except Exception as e:
                print(f"Lỗi khi cố gắng hủy tiến trình yt-dlp: {e}")
            finally:
                self._process = None
