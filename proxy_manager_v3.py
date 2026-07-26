# proxy_manager_v3.py
import asyncio
import json
import logging
import time
from pathlib import Path # <<< THÊM THƯ VIỆN NÀY
from typing import Dict, Any
from urllib.parse import quote
import sys

import requests

log = logging.getLogger(__name__)

class _M2ProxyClient:
    """Client cấp thấp để giao tiếp với API của M2Proxy."""

    def __init__(self, base_url: str, user_token: str, package_api_key: str):
        self.base_url = base_url
        self.user_token = user_token
        self.package_api_key = package_api_key
        self.change_ip_url = f"{self.base_url}/user/package/changeip?package_api_key={self.package_api_key}"

    async def change_ip(self) -> bool:
        """Gửi yêu cầu đổi IP và trả về True nếu thành công."""
        log.info("[M2ProxyClient] Đang gửi yêu cầu đổi IP...")
        try:
            response = await asyncio.to_thread(requests.get, self.change_ip_url, timeout=20)
            response.raise_for_status()
            data = response.json()
            if data.get("Status", "").lower() == "success":
                log.warning(f"[M2ProxyClient] ĐỔI IP THÀNH CÔNG. Phản hồi: {data.get('Message', 'N/A')}")
                return True
            log.warning(f"[M2ProxyClient] Đổi IP không thành công. Phản hồi: {data.get('Message', 'N/A')}")
            return False
        except requests.RequestException as e:
            log.error(f"[M2ProxyClient] Lỗi kết nối khi đổi IP: {e}")
            return False

    async def set_user_pass_authentication(self, username: str, password: str) -> bool:
        """Send request to enable USER/PASS authentication for the proxy package."""
        log.info("[M2ProxyClient] Dang cau hinh xac thuc USER/PASS cho proxy...")
        safe_user = quote(str(username))
        safe_pass = quote(str(password))
        edit_url = (
            f"{self.base_url}/user/package/edit?"
            f"package_api_key={self.package_api_key}&"
            "proxy_auth_type=USER_PASS&"
            f"proxy_auth_username={safe_user}&"
            f"proxy_auth_password={safe_pass}&"
            "auto_renew=true"
        )
        try:
            response = await asyncio.to_thread(requests.get, edit_url, timeout=20)
            response.raise_for_status()
            data = response.json()
            if data.get("Status", "").lower() == "success":
                log.warning(f"[M2ProxyClient] Cau hinh USER/PASS thanh cong. Phan hoi: {data.get('Message', 'N/A')}")
                return True
            log.error(f"[M2ProxyClient] Cau hinh USER/PASS that bai. Phan hoi: {data.get('Message', 'N/A')}")
            return False
        except requests.RequestException as e:
            log.error(f"[M2ProxyClient] Loi ket noi khi cau hinh USER/PASS: {e}")
            return False

    def set_user_pass_authentication_sync(self, username: str, password: str) -> bool:
        """Synchronous version of USER/PASS authentication setup for the proxy package."""
        log.info("[M2ProxyClient] Dang cau hinh xac thuc USER/PASS (SYNC) cho proxy...")
        safe_user = quote(str(username))
        safe_pass = quote(str(password))
        edit_url = (
            f"{self.base_url}/user/package/edit?"
            f"package_api_key={self.package_api_key}&"
            "proxy_auth_type=USER_PASS&"
            f"proxy_auth_username={safe_user}&"
            f"proxy_auth_password={safe_pass}&"
            "auto_renew=true"
        )
        try:
            response = requests.get(edit_url, timeout=20)
            response.raise_for_status()
            data = response.json()
            if data.get("Status", "").lower() == "success":
                log.warning(f"[M2ProxyClient] Cau hinh USER/PASS (SYNC) thanh cong. Phan hoi: {data.get('Message', 'N/A')}")
                return True
            log.error(f"[M2ProxyClient] Cau hinh USER/PASS (SYNC) that bai. Phan hoi: {data.get('Message', 'N/A')}")
            return False
        except requests.RequestException as e:
            log.error(f"[M2ProxyClient] Loi ket noi khi cau hinh USER/PASS (SYNC): {e}")
            return False
class ProxyManager:
    """Lớp quản lý proxy cấp cao, xử lý cooldown và cung cấp các phương thức tiện ích."""

    def __init__(self, m2_config: Dict[str, Any], proxy_connection: Dict[str, Any], cooldown_seconds: int, ip_checker_url: str):
        self.proxy_connection = proxy_connection
        self.cooldown_seconds = cooldown_seconds
        self._m2_client = _M2ProxyClient(
            base_url=m2_config['base_url'],
            user_token=m2_config['user_token'],
            package_api_key=m2_config['package_api_key']
        )
        self.ip_checker_url = ip_checker_url # <<< THÊM DÒNG NÀY
        self.last_ip_change_time: float = 0
        self.lock = asyncio.Lock()
        log.info(f"ProxyManager đã được khởi tạo. Cooldown: {cooldown_seconds}s.")

    @classmethod
    def from_config(cls, settings: Dict[str, Any]):
        """
        Khởi tạo ProxyManager từ dictionary cấu hình lồng nhau (đọc trực tiếp từ JSON).
        """
        log.info("Khởi tạo ProxyManager từ đối tượng config...")
        
        m2_conf = settings.get("M2_CONFIG", {})
        proxy_conn = settings.get("PROXY_CONNECTION", {})
        
        # Chuẩn hoá key: hỗ trợ cả username/password => user/pass
        if isinstance(proxy_conn, dict):
            if "username" in proxy_conn and "user" not in proxy_conn:
                proxy_conn["user"] = proxy_conn.get("username")
            if "password" in proxy_conn and "pass" not in proxy_conn:
                proxy_conn["pass"] = proxy_conn.get("password")
        
        # Kiểm tra các key bắt buộc
        if not m2_conf.get("package_api_key") or not proxy_conn.get("host") or not proxy_conn.get("port"):
            raise ValueError(
                "File cấu hình thiếu các key bắt buộc: "
                "'M2_CONFIG.package_api_key', 'PROXY_CONNECTION.host', hoặc 'PROXY_CONNECTION.port'"
            )
        
        # Gán giá trị mặc định nếu thiếu
        m2_conf.setdefault("base_url", "https://api.m2proxy.com")
        m2_conf.setdefault("user_token", None) # Có thể không cần cho một số API
        
        cooldown = settings.get("proxy_cooldown_seconds", 30)
        # Đọc URL dịch vụ IP từ config, nếu không có thì dùng api.ipify.org
        ip_checker = settings.get("ip_checker_service_url", "https://api.ipify.org?format=json")

        return cls(
            m2_config=m2_conf,
            proxy_connection=proxy_conn,
            cooldown_seconds=cooldown,
            ip_checker_url=ip_checker # <<< THÊM DÒNG NÀY
        )

    def authorize_user_pass(self, log_callback=print) -> bool:
        """Configure USER/PASS authentication for the proxy package using stored credentials."""
        log_callback("[ProxyManager] Bắt đầu cấu hình xác thực USER/PASS cho proxy...")
        try:
            user = self.proxy_connection.get("user") or self.proxy_connection.get("username")
            password = self.proxy_connection.get("pass") or self.proxy_connection.get("password")
            if not user or not password:
                log_callback("[ProxyManager] Lỗi: Thiếu username/password trong cấu hình proxy.")
                return False

            log_callback("[ProxyManager] ... Đang gửi yêu cầu USER/PASS đến M2Proxy...")
            auth_success = self._m2_client.set_user_pass_authentication_sync(user, password)
            if auth_success:
                log_callback("[ProxyManager] ... Xác thực USER/PASS thành công.")
                log_callback("[ProxyManager] ... Chờ 5 giây để M2Proxy cập nhật.")
                time.sleep(5)
                log_callback("[ProxyManager] ... Hoàn tất quá trình xác thực proxy (USER/PASS).")
                return True

            log_callback("[ProxyManager] Lỗi: Xác thực USER/PASS thất bại.")
            return False
        except Exception as e:
            log_callback(f"[ProxyManager] Lỗi: Gặp sự cố khi xác thực USER/PASS: {e}")
            return False
    async def change_ip_with_cooldown(self) -> bool:
        """Thực hiện đổi IP với cơ chế chờ (cooldown)."""
        success = False
        async with self.lock:
            elapsed = time.time() - self.last_ip_change_time
            if elapsed < self.cooldown_seconds:
                wait_time = self.cooldown_seconds - elapsed
                log.info(f"[ProxyManager] Đang trong thời gian chờ đổi IP, vui lòng đợi {wait_time:.1f} giây...")
                await asyncio.sleep(wait_time)
            
            if time.time() - self.last_ip_change_time >= self.cooldown_seconds:
                log.info("[ProxyManager] Thời gian chờ đã hết, bắt đầu đổi IP...")
                success = await self._m2_client.change_ip()
                if success:
                    self.last_ip_change_time = time.time()
            else:
                log.info("[ProxyManager] Một tác vụ khác đã đổi IP trong lúc chờ. Bỏ qua lần đổi này.")
        return success

    def get_proxy_url(self) -> str:
        """
        Trả về URL của proxy.
        Tự động thêm thông tin xác thực (username/password) nếu có trong cấu hình.
        """
        p_info = self.proxy_connection
        host = p_info.get('host')
        port = p_info.get('port')
        user = p_info.get('user')
        password = p_info.get('pass')

        if not host or not port:
            log.error("[ProxyManager] Cấu hình proxy thiếu 'host' hoặc 'port'.")
            return ""

        if user and password:
            safe_user = quote(str(user))
            safe_pass = quote(str(password))
            return f"http://{safe_user}:{safe_pass}@{host}:{port}"
        
        return f"http://{host}:{port}"

    def get_proxy_dict(self) -> Dict[str, str]:
        """Trả về một dictionary chứa thông tin proxy cho thư viện requests."""
        proxy_url = self.get_proxy_url()
        return {
            "http": proxy_url,
            "https": proxy_url
        }

    def check_public_ip(self) -> str | None:
        """
        Kiểm tra IP public hiện tại qua proxy (sử dụng ip_checker_url từ config).
        Trả về IP (string) hoặc None nếu không thể lấy được.
        """
        try:
            response = requests.get(
                self.ip_checker_url,
                proxies=self.get_proxy_dict(),
                timeout=10
            )
            response.raise_for_status()

            ip_value = None
            try:
                data = response.json()
                if isinstance(data, dict):
                    ip_value = data.get("ip") or data.get("origin")
            except ValueError:
                ip_value = None

            if not ip_value:
                ip_value = (response.text or "").strip()

            return ip_value or None
        except requests.RequestException as e:
            log.error(f"[ProxyManager] Lỗi khi kiểm tra IP qua proxy: {e}")
            return None
        except Exception as e:
            log.error(f"[ProxyManager] Lỗi không xác định khi kiểm tra IP: {e}")
            return None

# --- PHẦN KIỂM TRA PROXY ---
if __name__ == "__main__":

    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

    # Bổ sung màu để hiển thị thông tin cấu hình
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    RESET = '\033[0m'
    # Thiết lập encoding UTF-8 an toàn cho Windows console
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass
    
    def offline_config_smoke_test():
        """Kiểm tra offline: đọc JSON, khởi tạo manager, in ra URL proxy."""
        print("\n--- [OFFLINE CONFIG TEST] ---")
        settings_path = ""
        try:
            script_dir = Path(__file__).parent.resolve()
            settings_path = script_dir / "data" / "proxy_settings.json"
            print(f"Đang đọc file cấu hình tại: {settings_path}")

            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)

            manager = ProxyManager.from_config(settings)

            p_conn = manager.proxy_connection
            m2_client = manager._m2_client
            print(f"{YELLOW}--- [Thông tin cấu hình Proxy] ---")
            print(f"  - API Key M2Proxy : {m2_client.package_api_key}")
            print(f"  - Host            : {p_conn.get('host')}")
            print(f"  - Port            : {p_conn.get('port')}")
            print(f"  - User            : {p_conn.get('user')}")
            print(f"  - Pass            : {p_conn.get('pass')}")
            print(f"  - URL Proxy đầy đủ: {manager.get_proxy_url()}")
            print(f"------------------------------------{RESET}")
            print("✅ Offline test OK")
        except FileNotFoundError:
            print(f"{RED}❌ LỖI: Không tìm thấy file 'proxy_settings.json' tại thư mục 'data'.{RESET}")
            print(f"   Vui lòng đảm bảo file tồn tại tại đường dẫn: {settings_path}")
        except ValueError as e:
            print(f"{RED}❌ LỖI CẤU HÌNH: {e}{RESET}")
            print("   Vui lòng kiểm tra lại các giá trị trong file 'proxy_settings.json'.")
        except Exception as e:
            print(f"{RED}❌ ĐÃ XẢY RA LỖI KHÔNG XÁC ĐỊNH.{RESET}")
            log.error(f"   Chi tiết lỗi: {e}")
        finally:
            print("--- [OFFLINE TEST COMPLETE] ---\n")

    async def test_proxy_connection():
        """Ham kiem tra ket noi proxy va xac thuc USER/PASS."""
        print("\n--- [PROXY CONNECTION TEST] ---")
        settings_path = ""  # Khoi tao de tranh loi neu try that bai som
        try:
            script_dir = Path(__file__).parent.resolve()
            settings_path = script_dir / "data" / "proxy_settings.json"
            print(f"Dang doc file cau hinh tai: {settings_path}")

            with open(settings_path, 'r', encoding='utf-8') as f:
                settings = json.load(f)

            manager = ProxyManager.from_config(settings)

            # --- IN THONG TIN CAU HINH DE KIEM TRA ---
            p_conn = manager.proxy_connection
            m2_conf = manager._m2_client
            print(f"{YELLOW}--- [Thong tin cau hinh Proxy] ---")
            print(f"  - API Key M2Proxy : {m2_conf.package_api_key}")
            print(f"  - Host            : {p_conn.get('host')}")
            print(f"  - Port            : {p_conn.get('port')}")
            print(f"  - User            : {p_conn.get('user')}")
            print(f"  - Pass            : {p_conn.get('pass')}")
            print(f"  - URL Proxy day du: {manager.get_proxy_url()}")
            print(f"------------------------------------{RESET}")

            # --- BUOC 1: CAU HINH USER/PASS TREN M2PROXY ---
            print("\nBuoc 1: Cau hinh USER/PASS tren M2Proxy...")
            auth_success = await asyncio.to_thread(manager.authorize_user_pass)
            if not auth_success:
                print(f"{RED}!! CAU HINH USER/PASS THAT BAI!{RESET}")
                print("   Vui long kiem tra API key, username va password trong file cau hinh.")
                return

            # --- BUOC 2: KIEM TRA KET NOI QUA PROXY ---
            print("\nBuoc 2: Kiem tra ket noi qua proxy...")
            proxies = manager.get_proxy_dict()
            print(f"   Dang thu ket noi qua proxy: {proxies.get('http')}...")
            test_url = "http://httpbin.org/ip"
            proxy_response = await asyncio.to_thread(
                requests.get, test_url, proxies=proxies, timeout=15
            )
            proxy_response.raise_for_status()

            proxy_ip_address = proxy_response.json().get("origin")
            print(f"{GREEN}>> KIEM TRA THANH CONG!{RESET}")
            print(f"   Proxy hoat dong binh thuong. IP public qua proxy la: {proxy_ip_address}")

        except FileNotFoundError:
            print(f"{RED}LOI: Khong tim thay file 'proxy_settings.json' tai thu muc 'data'.{RESET}")
            print(f"   Vui long dam bao file ton tai tai duong dan: {settings_path}")
        except ValueError as e:
            print(f"{RED}LOI CAU HINH: {e}{RESET}")
            print("   Vui long kiem tra lai cac gia tri trong file 'proxy_settings.json'.")
        except (requests.exceptions.ProxyError, requests.exceptions.RequestException) as e:
            print(f"{RED}LOI KIEM TRA THAT BAI!{RESET}")
            print("   Khong the ket noi qua proxy. Vui long kiem tra lai host, port, user, pass.")
            log.error(f"   Chi tiet loi: {e}")
        except Exception as e:
            print(f"{RED}DA XAY RA LOI KHONG XAC DINH.{RESET}")
            log.error(f"   Chi tiet loi: {e}")
        finally:
            print("--- [TEST COMPLETE] ---\n")
    # Chế độ kiểm tra offline nếu có tham số dòng lệnh
    if any(arg in ("--offline", "--offline-test") for arg in sys.argv[1:]):
        offline_config_smoke_test()
    else:
        asyncio.run(test_proxy_connection())
