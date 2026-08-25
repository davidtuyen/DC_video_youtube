from __future__ import annotations

import base64
import hashlib
import json
import os
import socket
import sqlite3
import struct
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Mapping
from urllib.parse import urlsplit

from browser_cookie_profiles import DownloadCookieSource, build_browser_cookie_spec


YOUTUBE_HOME_URL = "https://www.youtube.com/"
YOUTUBE_LOGIN_URL = (
    "https://accounts.google.com/ServiceLogin?service=youtube&"
    "continue=https%3A%2F%2Fwww.youtube.com%2F"
)

_YOUTUBE_COOKIE_DOMAINS = (
    "google.com",
    "youtube.com",
    "googlevideo.com",
    "ytimg.com",
)
_YOUTUBE_AUTH_COOKIE_NAMES = {
    "APISID",
    "HSID",
    "LOGIN_INFO",
    "SAPISID",
    "SID",
    "SSID",
    "__Secure-1PAPISID",
    "__Secure-1PSID",
    "__Secure-3PAPISID",
    "__Secure-3PSID",
}
_CHROME_EPOCH_OFFSET_SECONDS = 11_644_473_600
_MAX_CDP_FRAME_BYTES = 16 * 1024 * 1024


class ManagedChromeError(RuntimeError):
    pass


@dataclass(frozen=True)
class BrowserLaunchResult:
    success: bool
    reused: bool = False
    message: str = ""


@dataclass(frozen=True)
class ManagedChromeStatus:
    state: str
    browser_running: bool
    message: str


def find_chrome_executable(
    environment: Mapping[str, str] | None = None,
) -> Path:
    env = os.environ if environment is None else environment
    candidates = []
    for variable in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        root = str(env.get(variable, "") or "").strip()
        if root:
            candidates.append(
                Path(root) / "Google" / "Chrome" / "Application" / "chrome.exe"
            )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise ManagedChromeError(
        "Không tìm thấy Google Chrome. Hãy cài Chrome rồi thử lại."
    )


def _normalized_cookie_domain(domain: str) -> str:
    return str(domain or "").lstrip(".").casefold()


def _is_youtube_cookie_domain(domain: str) -> bool:
    normalized = _normalized_cookie_domain(domain)
    return any(
        normalized == allowed or normalized.endswith(f".{allowed}")
        for allowed in _YOUTUBE_COOKIE_DOMAINS
    )


def _is_auth_cookie_domain(domain: str) -> bool:
    normalized = _normalized_cookie_domain(domain)
    return any(
        normalized == allowed or normalized.endswith(f".{allowed}")
        for allowed in ("google.com", "youtube.com")
    )


def _cookie_is_live(cookie: dict, *, now: float | None = None) -> bool:
    try:
        expires = float(cookie.get("expires", 0) or 0)
    except (TypeError, ValueError):
        return False
    return expires <= 0 or expires > (time.time() if now is None else now)


def _is_authenticated_cookie(cookie: dict, *, now: float | None = None) -> bool:
    return (
        _is_auth_cookie_domain(str(cookie.get("domain", "") or ""))
        and str(cookie.get("name", "") or "") in _YOUTUBE_AUTH_COOKIE_NAMES
        and bool(str(cookie.get("value", "") or "").strip())
        and _cookie_is_live(cookie, now=now)
    )


def _safe_cookie_field(value: object) -> str:
    return str(value or "").replace("\t", "").replace("\r", "").replace("\n", "")


def write_authenticated_snapshot(
    cookies: Iterable[dict],
    output_path: str | os.PathLike[str],
) -> int:
    now = time.time()
    filtered = [
        dict(cookie)
        for cookie in cookies
        if _is_youtube_cookie_domain(str(cookie.get("domain", "") or ""))
        and _cookie_is_live(cookie, now=now)
    ]
    if not any(_is_authenticated_cookie(cookie, now=now) for cookie in filtered):
        raise ManagedChromeError(
            "Chrome riêng chưa có phiên đăng nhập YouTube hợp lệ."
        )

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    descriptor, staged_name = tempfile.mkstemp(
        prefix=f".{output.name}.",
        suffix=".tmp",
        dir=str(output.parent),
        text=True,
    )
    staged_path = Path(staged_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write("# Netscape HTTP Cookie File\n")
            stream.write("# Managed by YouTube Downloader Pro\n")
            stream.write(f"# Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            for cookie in sorted(
                filtered,
                key=lambda item: (
                    str(item.get("domain", "")).casefold(),
                    str(item.get("path", "/")),
                    str(item.get("name", "")),
                ),
            ):
                domain = _safe_cookie_field(cookie.get("domain", ""))
                output_domain = (
                    f"#HttpOnly_{domain}" if cookie.get("httpOnly", False) else domain
                )
                include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
                try:
                    expires = max(0, int(float(cookie.get("expires", 0) or 0)))
                except (TypeError, ValueError):
                    expires = 0
                fields = (
                    output_domain,
                    include_subdomains,
                    _safe_cookie_field(cookie.get("path", "/") or "/"),
                    "TRUE" if cookie.get("secure", False) else "FALSE",
                    str(expires),
                    _safe_cookie_field(cookie.get("name", "")),
                    _safe_cookie_field(cookie.get("value", "")),
                )
                stream.write("\t".join(fields) + "\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(staged_path, output)
    except BaseException:
        try:
            staged_path.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    return len(filtered)


def _recv_exact(connection: socket.socket, size: int) -> bytes:
    data = bytearray()
    while len(data) < size:
        chunk = connection.recv(size - len(data))
        if not chunk:
            raise ManagedChromeError("Kết nối Chrome CDP đã đóng bất ngờ.")
        data.extend(chunk)
    return bytes(data)


def _masked_client_frame(opcode: int, payload: bytes) -> bytes:
    mask = os.urandom(4)
    length = len(payload)
    frame = bytearray([0x80 | opcode])
    if length < 126:
        frame.append(0x80 | length)
    elif length < 65_536:
        frame.append(0x80 | 126)
        frame.extend(struct.pack(">H", length))
    else:
        frame.append(0x80 | 127)
        frame.extend(struct.pack(">Q", length))
    frame.extend(mask)
    frame.extend(byte ^ mask[index % 4] for index, byte in enumerate(payload))
    return bytes(frame)


def _read_server_frame(connection: socket.socket) -> tuple[bool, int, bytes]:
    first, second = _recv_exact(connection, 2)
    final = bool(first & 0x80)
    opcode = first & 0x0F
    length = second & 0x7F
    if length == 126:
        length = struct.unpack(">H", _recv_exact(connection, 2))[0]
    elif length == 127:
        length = struct.unpack(">Q", _recv_exact(connection, 8))[0]
    if length > _MAX_CDP_FRAME_BYTES:
        raise ManagedChromeError("Chrome CDP trả về frame quá lớn.")
    mask = _recv_exact(connection, 4) if second & 0x80 else b""
    payload = _recv_exact(connection, length)
    if mask:
        payload = bytes(
            byte ^ mask[index % 4] for index, byte in enumerate(payload)
        )
    return final, opcode, payload


def cdp_command(
    websocket_url: str,
    method: str,
    params: dict | None = None,
    *,
    timeout: float = 2.0,
    allow_disconnect: bool = False,
) -> dict:
    parsed = urlsplit(str(websocket_url or ""))
    if (
        parsed.scheme != "ws"
        or parsed.hostname not in {"127.0.0.1", "localhost"}
        or parsed.port is None
        or not parsed.path.startswith("/devtools/browser/")
    ):
        raise ManagedChromeError("Địa chỉ Chrome CDP không hợp lệ hoặc không phải loopback.")

    connection = socket.create_connection(
        (parsed.hostname, parsed.port),
        timeout=timeout,
    )
    connection.settimeout(timeout)
    try:
        key = base64.b64encode(os.urandom(16)).decode("ascii")
        request_path = parsed.path + (f"?{parsed.query}" if parsed.query else "")
        request = (
            f"GET {request_path} HTTP/1.1\r\n"
            f"Host: {parsed.hostname}:{parsed.port}\r\n"
            "Upgrade: websocket\r\n"
            "Connection: Upgrade\r\n"
            f"Sec-WebSocket-Key: {key}\r\n"
            "Sec-WebSocket-Version: 13\r\n\r\n"
        )
        connection.sendall(request.encode("ascii"))
        headers = bytearray()
        while b"\r\n\r\n" not in headers:
            headers.extend(_recv_exact(connection, 1))
            if len(headers) > 16_384:
                raise ManagedChromeError("WebSocket handshake từ Chrome quá lớn.")
        header_text = headers.decode("latin-1", errors="replace")
        if not header_text.startswith("HTTP/1.1 101"):
            raise ManagedChromeError("Chrome từ chối WebSocket CDP.")
        expected_accept = base64.b64encode(
            hashlib.sha1(
                (key + "258EAFA5-E914-47DA-95CA-C5AB0DC85B11").encode("ascii")
            ).digest()
        ).decode("ascii")
        if (
            f"sec-websocket-accept: {expected_accept}".casefold()
            not in header_text.casefold()
        ):
            raise ManagedChromeError("WebSocket handshake từ Chrome không hợp lệ.")

        command_id = 1
        command = {"id": command_id, "method": str(method)}
        if params is not None:
            command["params"] = params
        connection.sendall(
            _masked_client_frame(0x1, json.dumps(command).encode("utf-8"))
        )

        message = bytearray()
        for _ in range(256):
            try:
                final, opcode, payload = _read_server_frame(connection)
            except (OSError, ManagedChromeError):
                if allow_disconnect:
                    return {}
                raise
            if opcode == 0x8:
                if allow_disconnect:
                    return {}
                raise ManagedChromeError("Chrome đã đóng kênh CDP.")
            if opcode == 0x9:
                connection.sendall(_masked_client_frame(0xA, payload))
                continue
            if opcode not in {0x0, 0x1}:
                continue
            message.extend(payload)
            if not final:
                continue
            try:
                decoded = json.loads(message.decode("utf-8"))
            except (UnicodeError, json.JSONDecodeError) as exc:
                raise ManagedChromeError("Chrome trả về dữ liệu CDP không hợp lệ.") from exc
            message.clear()
            if decoded.get("id") != command_id:
                continue
            if decoded.get("error"):
                error = decoded["error"]
                detail = error.get("message", error) if isinstance(error, dict) else error
                raise ManagedChromeError(f"Chrome CDP báo lỗi: {detail}")
            return decoded
        raise ManagedChromeError("Không nhận được phản hồi lệnh từ Chrome CDP.")
    finally:
        connection.close()


class ManagedChromeSession:
    def __init__(
        self,
        browser_data_root: str | os.PathLike[str],
        *,
        chrome_path: str | os.PathLike[str] | None = None,
        headless: bool = False,
    ) -> None:
        self.browser_data_root = Path(browser_data_root)
        self.user_data_dir = self.browser_data_root / "chrome-user-data"
        self.profile_dir = self.user_data_dir / "Default"
        self.snapshot_path = self.browser_data_root / "session-cookies.txt"
        self.lease_dir = self.browser_data_root / "cookie-leases"
        stale_plaintext = [self.snapshot_path]
        stale_plaintext.extend(
            self.browser_data_root.glob(f".{self.snapshot_path.name}.*.tmp")
        )
        for stale_path in stale_plaintext:
            try:
                stale_path.unlink(missing_ok=True)
            except OSError:
                pass
        if self.lease_dir.is_dir():
            for stale_lease in self.lease_dir.iterdir():
                if not stale_lease.is_file() or stale_lease.suffix not in {".txt", ".tmp"}:
                    continue
                try:
                    stale_lease.unlink()
                except OSError:
                    pass
        self._chrome_path = Path(chrome_path) if chrome_path else None
        self._headless = bool(headless)
        self._process: subprocess.Popen | None = None
        self._lock = threading.RLock()
        self._lease_paths: set[Path] = set()
        self.last_error = ""

    def _executable(self) -> Path:
        return self._chrome_path or find_chrome_executable()

    def build_launch_arguments(
        self,
        start_url: str,
        *,
        enable_cdp: bool = True,
    ) -> list[str]:
        arguments = [
            str(self._executable()),
            f"--user-data-dir={self.user_data_dir}",
            "--profile-directory=Default",
            "--no-first-run",
            "--no-default-browser-check",
            str(start_url),
        ]
        if enable_cdp:
            arguments[1:1] = [
                "--remote-debugging-address=127.0.0.1",
                "--remote-debugging-port=0",
            ]
        if self._headless:
            arguments.insert(-1, "--headless=new")
        return arguments

    def _tracked_process_running(self) -> bool:
        process = self._process
        if process is None:
            return False
        try:
            running = process.poll() is None
        except OSError:
            running = False
        if not running:
            self._process = None
        return running

    def _read_websocket_url(self) -> str:
        endpoint_file = self.user_data_dir / "DevToolsActivePort"
        try:
            lines = endpoint_file.read_text(encoding="utf-8").splitlines()
            port = int(lines[0])
            path = lines[1]
        except (OSError, IndexError, ValueError):
            return ""
        if not 0 < port <= 65_535 or not path.startswith("/devtools/browser/"):
            return ""
        return f"ws://127.0.0.1:{port}{path}"

    def _active_websocket_url(self) -> str:
        websocket_url = self._read_websocket_url()
        if not websocket_url:
            return ""
        try:
            cdp_command(websocket_url, "Browser.getVersion", timeout=0.5)
        except (OSError, ManagedChromeError):
            return ""
        return websocket_url

    def _wait_for_active_websocket(
        self,
        process: subprocess.Popen,
        *,
        timeout: float = 5.0,
    ) -> str:
        deadline = time.monotonic() + timeout
        while True:
            websocket_url = self._active_websocket_url()
            if websocket_url:
                return websocket_url
            try:
                process_exited = process.poll() is not None
            except OSError:
                process_exited = True
            if process_exited or time.monotonic() >= deadline:
                return ""
            time.sleep(0.1)

    @staticmethod
    def _stop_exact_process(process: subprocess.Popen) -> None:
        try:
            if process.poll() is not None:
                return
            process.terminate()
        except OSError:
            return
        try:
            process.wait(timeout=1)
        except subprocess.TimeoutExpired:
            try:
                process.kill()
                process.wait(timeout=1)
            except (OSError, subprocess.TimeoutExpired):
                pass

    def _profile_has_login_cookie_record(self) -> bool:
        databases = (
            self.profile_dir / "Network" / "Cookies",
            self.profile_dir / "Cookies",
        )
        database = next((path for path in databases if path.is_file()), None)
        if database is None:
            return False
        current_chrome_time = int(
            (time.time() + _CHROME_EPOCH_OFFSET_SECONDS) * 1_000_000
        )
        placeholders = ",".join("?" for _ in _YOUTUBE_AUTH_COOKIE_NAMES)
        query = (
            "SELECT host_key, name, expires_utc, value, encrypted_value "
            f"FROM cookies WHERE name IN ({placeholders})"
        )
        try:
            connection = sqlite3.connect(
                f"file:{database.as_posix()}?mode=ro",
                uri=True,
                timeout=0.2,
            )
            try:
                rows = connection.execute(
                    query,
                    tuple(sorted(_YOUTUBE_AUTH_COOKIE_NAMES)),
                ).fetchall()
            finally:
                connection.close()
        except (OSError, sqlite3.Error):
            return False
        for host_key, _name, expires_utc, value, encrypted_value in rows:
            try:
                is_live = not expires_utc or int(expires_utc) > current_chrome_time
            except (TypeError, ValueError):
                continue
            if (
                _is_auth_cookie_domain(host_key)
                and is_live
                and bool(str(value or "").strip() or encrypted_value)
            ):
                return True
        return False

    def _lease_path(self, lease_id: str) -> Path:
        digest = hashlib.sha256(str(lease_id).encode("utf-8")).hexdigest()
        return self.lease_dir / f"{digest}.txt"

    def release_cookie_source(self, source: DownloadCookieSource) -> None:
        cookie_path = Path(source.cookie_file_path) if source.cookie_file_path else None
        with self._lock:
            if cookie_path is None or cookie_path not in self._lease_paths:
                return
            self._lease_paths.discard(cookie_path)
            try:
                cookie_path.unlink(missing_ok=True)
            except OSError:
                pass

    def open_browser(self) -> BrowserLaunchResult:
        with self._lock:
            self.browser_data_root.mkdir(parents=True, exist_ok=True)
            websocket_url = self._active_websocket_url()
            if websocket_url:
                has_login = self._profile_has_login_cookie_record()
                try:
                    response = cdp_command(websocket_url, "Storage.getCookies")
                    cookies = response.get("result", {}).get("cookies", [])
                    has_login = any(
                        _is_authenticated_cookie(cookie) for cookie in cookies
                    )
                except (OSError, ManagedChromeError):
                    # The read-only cookie database check remains a safe fallback
                    # if CDP can create a tab but cookie enumeration is unavailable.
                    pass
                start_url = YOUTUBE_HOME_URL if has_login else YOUTUBE_LOGIN_URL
                try:
                    cdp_command(
                        websocket_url,
                        "Target.createTarget",
                        {"url": start_url},
                    )
                except (OSError, ManagedChromeError) as exc:
                    self.last_error = str(exc)
                    return BrowserLaunchResult(False, reused=True, message=self.last_error)
                self.last_error = ""
                return BrowserLaunchResult(
                    True,
                    reused=True,
                    message="Đã mở YouTube trong Chrome riêng của ứng dụng.",
                )

            if self._tracked_process_running():
                return BrowserLaunchResult(
                    True,
                    reused=True,
                    message=(
                        "Chrome đăng nhập đang mở. Hãy đăng nhập YouTube rồi đóng "
                        "cửa sổ Chrome để ứng dụng hoàn tất thiết lập."
                    ),
                )

            has_login = self._profile_has_login_cookie_record()
            start_url = YOUTUBE_HOME_URL if has_login else YOUTUBE_LOGIN_URL

            try:
                flags = (
                    getattr(subprocess, "CREATE_NO_WINDOW", 0)
                    if os.name == "nt" and self._headless
                    else 0
                )
                self._process = subprocess.Popen(
                    self.build_launch_arguments(start_url, enable_cdp=has_login),
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    creationflags=flags,
                )
            except (OSError, ManagedChromeError) as exc:
                self.last_error = str(exc)
                return BrowserLaunchResult(False, message=self.last_error)

            if not has_login:
                try:
                    process_exited = self._process.poll() is not None
                except OSError:
                    process_exited = True
                if process_exited:
                    self._process = None
                    self.last_error = (
                        "Chrome riêng không khởi động được hoặc profile đang bị khóa. "
                        "Hãy đóng cửa sổ Chrome riêng rồi thử lại."
                    )
                    return BrowserLaunchResult(False, message=self.last_error)
                self.last_error = ""
                return BrowserLaunchResult(
                    True,
                    reused=False,
                    message=(
                        "Đã mở Chrome riêng ở chế độ đăng nhập an toàn. Đăng nhập "
                        "YouTube xong, hãy đóng cửa sổ Chrome rồi bấm Kiểm tra đăng nhập."
                    ),
                )

            if not self._wait_for_active_websocket(self._process):
                self._stop_exact_process(self._process)
                self._process = None
                self.last_error = (
                    "Chrome riêng không khởi động được hoặc profile đang bị khóa. "
                    "Hãy đóng cửa sổ Chrome riêng rồi thử lại."
                )
                return BrowserLaunchResult(False, message=self.last_error)
            self.last_error = ""
            return BrowserLaunchResult(
                True,
                reused=False,
                message="Đã mở Chrome riêng. Hãy đăng nhập YouTube một lần.",
            )

    def resolve_cookie_source(self, *, lease_id: str | None = None) -> DownloadCookieSource:
        with self._lock:
            websocket_url = self._active_websocket_url()
            if websocket_url:
                output_path = self._lease_path(lease_id) if lease_id else self.snapshot_path
                try:
                    response = cdp_command(websocket_url, "Storage.getCookies")
                    cookies = response.get("result", {}).get("cookies", [])
                    write_authenticated_snapshot(cookies, output_path)
                except (OSError, ManagedChromeError) as exc:
                    if lease_id:
                        self._lease_paths.discard(output_path)
                        try:
                            output_path.unlink(missing_ok=True)
                        except OSError:
                            pass
                    self.last_error = str(exc)
                    return DownloadCookieSource()
                if lease_id:
                    self._lease_paths.add(output_path)
                self.last_error = ""
                return DownloadCookieSource(
                    use_cookie_file=True,
                    cookie_file_path=str(output_path),
                )

            if self._tracked_process_running():
                self.last_error = (
                    "Hãy đăng nhập xong và đóng Chrome riêng trước khi bắt đầu tải."
                )
                return DownloadCookieSource()

            if self._profile_has_login_cookie_record():
                self.last_error = ""
                return DownloadCookieSource(
                    browser_spec=build_browser_cookie_spec(
                        "chrome",
                        str(self.profile_dir.resolve()),
                    )
                )
            self.last_error = "Chrome riêng chưa đăng nhập YouTube."
            return DownloadCookieSource()

    def check_login_status(self) -> ManagedChromeStatus:
        """Inspect the app-owned Chrome session without exporting cookies."""
        with self._lock:
            websocket_url = self._active_websocket_url()
            if websocket_url:
                try:
                    response = cdp_command(websocket_url, "Storage.getCookies")
                    cookies = response.get("result", {}).get("cookies", [])
                except (OSError, ManagedChromeError) as exc:
                    return ManagedChromeStatus(
                        "unavailable",
                        True,
                        f"Không thể kiểm tra phiên Chrome riêng: {exc}",
                    )
                if any(_is_authenticated_cookie(cookie) for cookie in cookies):
                    return ManagedChromeStatus(
                        "authenticated",
                        True,
                        "Đã đăng nhập YouTube trong Chrome riêng.",
                    )
                return ManagedChromeStatus(
                    "not_authenticated",
                    True,
                    "Chưa đăng nhập YouTube trong Chrome riêng.",
                )

            if self._tracked_process_running():
                has_login = self._profile_has_login_cookie_record()
                if has_login:
                    return ManagedChromeStatus(
                        "authenticated",
                        True,
                        "Đã nhận phiên đăng nhập. Hãy đóng Chrome để hoàn tất thiết lập.",
                    )
                return ManagedChromeStatus(
                    "not_authenticated",
                    True,
                    "Đăng nhập YouTube xong, hãy đóng Chrome rồi kiểm tra lại.",
                )

            if self._profile_has_login_cookie_record():
                return ManagedChromeStatus(
                    "authenticated",
                    False,
                    "Đã đăng nhập YouTube trong Chrome riêng.",
                )
            try:
                self._executable()
            except ManagedChromeError as exc:
                return ManagedChromeStatus("unavailable", False, str(exc))
            return ManagedChromeStatus(
                "not_authenticated",
                False,
                "Chưa đăng nhập YouTube trong Chrome riêng.",
            )

    def shutdown(self) -> None:
        with self._lock:
            websocket_url = self._active_websocket_url()
            if websocket_url:
                try:
                    cdp_command(
                        websocket_url,
                        "Browser.close",
                        allow_disconnect=True,
                    )
                except (OSError, ManagedChromeError):
                    pass
            process = self._process
            if process is not None:
                try:
                    is_running = process.poll() is None
                except OSError:
                    is_running = False
                if is_running:
                    try:
                        process.wait(timeout=3)
                    except (OSError, subprocess.TimeoutExpired):
                        self._stop_exact_process(process)
            self._process = None
            for lease_path in tuple(self._lease_paths):
                try:
                    lease_path.unlink(missing_ok=True)
                except OSError:
                    pass
            self._lease_paths.clear()
            try:
                self.snapshot_path.unlink(missing_ok=True)
            except OSError:
                pass
