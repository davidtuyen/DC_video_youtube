import os
import json
import time
import collections.abc
import urllib.parse  # [ZERO-LEAK-FIX] encode proxy credentials safely

from google.oauth2.credentials import Credentials as UserCredentials
from google_auth_oauthlib.flow import InstalledAppFlow
import google.auth.transport.requests
from google.auth.transport.requests import AuthorizedSession as GoogleAuthorizedSession
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, HttpRequest
from googleapiclient.errors import HttpError
import requests
import google.auth.exceptions

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

USER_TOKEN_DRIVE_PATH = os.path.join(DATA_DIR_NAME, USER_TOKEN_DRIVE_FILE_NAME)
USER_CREDS_PATH = os.path.join(DATA_DIR_NAME, USER_CREDS_FILE_NAME)
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

    if not os.path.exists(DATA_DIR_NAME):
        try:
            os.makedirs(DATA_DIR_NAME)
        except OSError as e:
            return None, f"Lỗi khi tạo thư mục data: {e}"

    # 1. Tải token đã lưu nếu có
    if os.path.exists(USER_TOKEN_DRIVE_PATH):
        try:
            creds = UserCredentials.from_authorized_user_file(USER_TOKEN_DRIVE_PATH, SCOPES_DRIVE)
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
                if os.path.exists(USER_TOKEN_DRIVE_PATH):
                    os.remove(USER_TOKEN_DRIVE_PATH)
                    status_callback(f"AuthFlow: Đã xóa file token cũ tại {USER_TOKEN_DRIVE_PATH}.")
            except OSError as e_del:
                status_callback(f"AuthFlow: Không thể xóa file token cũ: {e_del}")

    # 2.5. Chạy luồng xác thực mới nếu (sau khi thử refresh) vẫn không hợp lệ
    if not creds or not creds.valid:
        status_callback("AuthFlow: Bắt đầu luồng xác thực người dùng mới (do không có token/token không hợp lệ/refresh thất bại)...")
        if not os.path.exists(USER_CREDS_PATH):
            return None, f"Lỗi: File '{USER_CREDS_PATH}' không tìm thấy."
        try:
            flow = InstalledAppFlow.from_client_secrets_file(USER_CREDS_PATH, SCOPES_DRIVE)
            flow.session = session  # [ZERO-LEAK-FIX]
            creds = flow.run_local_server(port=0)
        except Exception as e:
            return None, f"Lỗi trong quá trình xác thực OAuth: {e}"

        # Lưu token mới
        if creds:
            with open(USER_TOKEN_DRIVE_PATH, 'w') as token_file:
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
    else:
        return None, "Không thể xác thực với Google Drive."

def upload_srt_to_drive(drive_service, folder_id, srt_file_path, srt_file_name_on_drive, status_callback=print):
    try:
        status_callback(f"Đang chuẩn bị tải lên: {srt_file_name_on_drive} vào thư mục ID: {folder_id}")
        file_metadata = {
            'name': srt_file_name_on_drive,
            'parents': [folder_id]
        }
        media = MediaFileUpload(srt_file_path, mimetype='text/plain', resumable=True)
        request = drive_service.files().create(
            body=file_metadata,
            media_body=media,
            fields='id, webViewLink, name'
        )
        
        # Cân nhắc thêm timeout cho execute nếu cần, ví dụ: request.execute(num_retries=3)
        # Hoặc nếu thư viện cho phép timeout trực tiếp: request.execute(timeout=...)
        # Mặc định, nó sẽ dùng timeout của http object (authed_http)
        file = request.execute() 
        
        file_id = file.get('id')
        web_view_link = file.get('webViewLink')
        uploaded_name = file.get('name')
        if file_id and web_view_link:
            status_callback(f"Đã tải lên thành công '{uploaded_name}' (ID: {file_id}), Link: {web_view_link}")
            try:
                permission = {'type': 'anyone', 'role': 'reader'}
                drive_service.permissions().create(fileId=file_id, body=permission).execute()
                status_callback(f"Đã cấp quyền xem công khai cho file: {file_id}")
            except HttpError as e_perm:
                status_callback(f"Lỗi khi cấp quyền cho file {file_id}: {e_perm}. Link có thể không truy cập được công khai.")
            return file_id, web_view_link
        else:
            status_callback(f"Tải lên file '{srt_file_name_on_drive}' có vẻ thành công nhưng không nhận được ID hoặc link xem.")
            return None, None
    except HttpError as error:
        error_content = getattr(error, 'content', '{}') # An toàn hơn nếu error.resp không có
        try:
            # Đảm bảo error_content là bytes trước khi decode
            if isinstance(error_content, bytes):
                error_details = json.loads(error_content.decode('utf-8'))
            elif isinstance(error_content, str): # Nếu đã là str
                 error_details = json.loads(error_content)
            else: # Trường hợp khác, thử str(error_content)
                 error_details = json.loads(str(error_content))

            message = error_details.get('error', {}).get('message', str(error))
        except (json.JSONDecodeError, TypeError): # Bắt cả TypeError nếu content không phải dạng có thể decode/load
            message = str(error) # Fallback về thông báo lỗi gốc
        status_callback(f"Lỗi API Google Drive khi tải file '{srt_file_name_on_drive}': {message}")
        # import traceback # Thêm nếu cần debug sâu lỗi HttpError
        # status_callback(f"[DEBUG] Traceback HttpError upload: {traceback.format_exc()}")
        return None, None
    except Exception as e:
        status_callback(f"Lỗi không xác định khi tải file '{srt_file_name_on_drive}' lên Drive: {e}")
        # import traceback # Thêm nếu cần debug sâu lỗi Exception
        # status_callback(f"[DEBUG] Traceback Exception upload: {traceback.format_exc()}")
        return None, None

def check_drive_folder_exists(drive_service, folder_id, status_callback=print):
    if not folder_id or not folder_id.strip():
        status_callback("Folder ID rỗng, không thể kiểm tra.")
        return False, "Folder ID không được để trống."
    try:
        folder_metadata = drive_service.files().get(fileId=folder_id, fields="id, name, mimeType").execute()
        if folder_metadata.get("mimeType") == "application/vnd.google-apps.folder":
            status_callback(f"Thư mục Google Drive hợp lệ: '{folder_metadata.get('name')}' (ID: {folder_id})")
            return True, f"Thư mục '{folder_metadata.get('name')}' hợp lệ."
        else:
            status_callback(f"ID '{folder_id}' không phải là một thư mục Google Drive.")
            return False, f"ID '{folder_id}' không phải là một thư mục."
    except HttpError as error:
        message = f"Lỗi API khi kiểm tra thư mục Drive ID '{folder_id}': {error}"
        try: # Cố gắng lấy thông tin chi tiết hơn từ lỗi
            error_resp = getattr(error, 'resp', None)
            if error_resp and hasattr(error_resp, 'status') and error_resp.status == 404:
                 message = f"Không tìm thấy thư mục Google Drive với ID '{folder_id}' hoặc không có quyền truy cập."
            elif error_resp and hasattr(error_resp, 'status'):
                 message = f"Lỗi API ({error_resp.status}) khi kiểm tra thư mục Drive ID '{folder_id}': {error._get_reason()}"
        except:
            pass # Giữ message cũ nếu không lấy được chi tiết
        status_callback(message)
        return False, message
    except Exception as e:
        message = f"Lỗi không xác định khi kiểm tra thư mục Drive ID '{folder_id}': {e}"
        status_callback(message)
        return False, message
