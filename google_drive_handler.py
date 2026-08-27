import os
import sys
import collections.abc
import urllib.parse  # [ZERO-LEAK-FIX] encode proxy credentials safely

from google.oauth2.credentials import Credentials as UserCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
import google.auth.transport.requests
from google.auth.transport.requests import AuthorizedSession as GoogleAuthorizedSession
from googleapiclient.discovery import build
from googleapiclient.http import HttpRequest
import requests

# --- ADAPTER HOÀN CHỈNH - SỬA LỖI TƯƠNG THÍCH ĐẦU VÀO VÀ ĐẦU RA ---

class Httplib2ResponseAdapter(collections.abc.Mapping):
    """
    Adapter để làm cho một đối tượng requests.Response trông giống như
    một đối tượng httplib2.Response. Cần thiết cho google-api-python-client.
    Nó cung cấp thuộc tính .status và truy cập headers qua kiểu dictionary.
    """
    def __init__(self, resp):
        self._response = resp
        self.status = resp.status_code
        self.reason = resp.reason
        self._headers = {k.lower(): v for k, v in resp.headers.items()}
    def __getitem__(self, key):
        return self._headers[key.lower()]
    def __iter__(self):
        return iter(self._headers)
    def __len__(self):
        return len(self._headers)

class CustomAuthorizedSession(GoogleAuthorizedSession):
    """
    Lớp adapter cuối cùng.
    1. Sửa lỗi signature ĐẦU VÀO: Nhận (url, method, body) từ google-api-client.
    2. Sửa lỗi signature ĐẦU RA: Trả về tuple (info, content) mà google-api-client mong đợi.
    """
    def request(self, url, method="GET", body=None, headers=None, **kwargs):
        # Gọi phương thức request của lớp cha (requests.Session) để nhận một đối tượng requests.Response duy nhất.
        response_obj = super().request(
            method=method,
            url=url,
            data=body,
            headers=headers,
            **kwargs
        )
        
        # Bây giờ, chuyển đổi requests.Response thành tuple (response_info, content_bytes)
        # mà google-api-python-client mong đợi.
        response_adapter = Httplib2ResponseAdapter(response_obj)
        content_bytes = response_obj.content
        
        return response_adapter, content_bytes


SCOPES_DRIVE = ['https://www.googleapis.com/auth/drive']
DATA_DIR_NAME = "data"

USER_TOKEN_DRIVE_FILE_NAME = 'token_drive.json'
USER_CREDS_FILE_NAME = 'credentials.json'
PACKAGED_CREDS_FILE_NAME = 'google_drive_client.json'

USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36 Edg/121.0.0.0"  # [ZERO-LEAK-FIX]


def _application_directory() -> str:
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _drive_paths() -> tuple[str, str, str]:
    data_dir = os.path.join(_application_directory(), DATA_DIR_NAME)
    return (
        data_dir,
        os.path.join(data_dir, USER_TOKEN_DRIVE_FILE_NAME),
        os.path.join(data_dir, USER_CREDS_FILE_NAME),
    )


def _client_credentials_path(data_dir: str, user_credentials_path: str) -> str | None:
    if os.path.isfile(user_credentials_path):
        return user_credentials_path
    packaged_path = os.path.join(data_dir, PACKAGED_CREDS_FILE_NAME)
    return packaged_path if os.path.isfile(packaged_path) else None


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
        safe_user = urllib.parse.quote(parsed.username or "", safe="")
        safe_pass = urllib.parse.quote(parsed.password or "", safe="")
        netloc_host = f"{safe_user}:{safe_pass}@{netloc_host}"

    return urllib.parse.urlunparse((
        parsed.scheme or "http",
        netloc_host,
        parsed.path or "",
        "",
        parsed.query,
        parsed.fragment
    ))  # [ZERO-LEAK-FIX]


def authenticate_gdrive_user_flow(status_callback=print, proxy_url: str | None = None):
    data_dir, token_path, user_credentials_path = _drive_paths()
    safe_proxy_url = _normalize_proxy_url(proxy_url)
    if proxy_url and not safe_proxy_url:
        return None, "Proxy được yêu cầu cho Drive nhưng URL không hợp lệ."  # [ZERO-LEAK-FIX]
    session = requests.Session()
    session.headers.update({'User-Agent': USER_AGENT})
    if safe_proxy_url:
        proxies = {'http': safe_proxy_url, 'https': safe_proxy_url}
        session.proxies.update(proxies)
        status_callback("AuthFlow: Đặt proxy cho toàn bộ phiên xác thực Drive.")  # [ZERO-LEAK-FIX]

    creds = None

    if not os.path.exists(data_dir):
        try:
            os.makedirs(data_dir)
        except OSError as e:
            return None, f"Lỗi khi tạo thư mục data: {e}"

    # 1. Tải token đã lưu nếu có
    if os.path.exists(token_path):
        try:
            creds = UserCredentials.from_authorized_user_file(token_path, SCOPES_DRIVE)
        except Exception as e:
            status_callback(f"AuthFlow: Không thể tải token từ file. Lỗi: {e}")
            creds = None

    # 2. Refresh token nếu cần
    if creds and creds.expired and creds.refresh_token:
        status_callback("AuthFlow: Token đã hết hạn, đang làm mới...")
        try:
            creds.refresh(google.auth.transport.requests.Request(session=session))  # [ZERO-LEAK-FIX]
        except Exception as e:
            status_callback(f"AuthFlow: Làm mới token thất bại. Lỗi: {e}")
            status_callback("AuthFlow: Thử xóa token cũ và yêu cầu xác thực lại từ đầu.")
            creds = None # Đánh dấu là không hợp lệ
            try:
                # Xóa file token hỏng/hết hạn để buộc tạo mới
                if os.path.exists(token_path):
                    os.remove(token_path)
                    status_callback(f"AuthFlow: Đã xóa file token cũ tại {token_path}.")
            except OSError as e_del:
                status_callback(f"AuthFlow: Không thể xóa file token cũ: {e_del}")

    # 2.5. Chạy luồng xác thực mới nếu (sau khi thử refresh) vẫn không hợp lệ
    if not creds or not creds.valid:
        status_callback("AuthFlow: Bắt đầu luồng xác thực người dùng mới (do không có token/token không hợp lệ/refresh thất bại)...")
        credentials_path = _client_credentials_path(data_dir, user_credentials_path)
        if not credentials_path:
            return None, (
                "Lỗi: Không tìm thấy cấu hình OAuth Google Drive của ứng dụng "
                f"trong thư mục '{data_dir}'."
            )
        try:
            flow = InstalledAppFlow.from_client_secrets_file(credentials_path, SCOPES_DRIVE)
            flow.session = session  # [ZERO-LEAK-FIX]
            creds = flow.run_local_server(port=0)
        except Exception as e:
            return None, f"Lỗi trong quá trình xác thực OAuth: {e}"

        # Lưu token mới
        if creds:
            with open(token_path, 'w') as token_file:
                token_file.write(creds.to_json())
            status_callback("AuthFlow: Đã lưu token mới thành công.")

    # 3. Xây dựng và trả về đối tượng service
    if creds and creds.valid:
        try:
            # SỬA LỖI TypeError: unexpected keyword argument 'body'
            authed_session = CustomAuthorizedSession(credentials=creds)
            authed_session.headers.update({'User-Agent': USER_AGENT})

            if safe_proxy_url:
                authed_session.proxies.update({'http': safe_proxy_url, 'https': safe_proxy_url})

            drive_service = build(
                'drive',
                'v3',
                http=authed_session,
                requestBuilder=lambda http, *args, **kwargs: HttpRequest(authed_session, *args, **kwargs),
                cache_discovery=False
            )  # [ZERO-LEAK-FIX]

            status_callback("AuthFlow: Xây dựng Drive service thành công.")
            return drive_service, None
        except Exception as e:
            import traceback
            status_callback(f"AuthFlow-DEBUG: Traceback khi build service: {traceback.format_exc()}")
            return None, f"Lỗi khi xây dựng Drive service: {e}"
    return None, "Không thể xác thực với Google Drive."
