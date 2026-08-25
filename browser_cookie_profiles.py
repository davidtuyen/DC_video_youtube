from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path


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

COOKIE_SOURCE_NONE = "none"
COOKIE_SOURCE_MANAGED = "managed"
COOKIE_SOURCE_FILE = "file"
COOKIE_SOURCE_MODES = {
    COOKIE_SOURCE_NONE,
    COOKIE_SOURCE_MANAGED,
    COOKIE_SOURCE_FILE,
}
_LEGACY_BROWSER_KEYS = (
    "cookies_from_browser",
    "cookies_profile",
    "chrome_profile",
    "extracted_cookies_path",
)


def _is_google_or_youtube_domain(domain: str) -> bool:
    normalized = str(domain or "").strip().lstrip(".").casefold()
    return any(
        normalized == allowed or normalized.endswith(f".{allowed}")
        for allowed in ("google.com", "youtube.com")
    )


@dataclass(frozen=True)
class DownloadCookieSource:
    use_cookie_file: bool = False
    cookie_file_path: str = ""
    browser_spec: str = ""
    invalid_cookie_file: bool = False


def get_cookie_source_mode(settings: dict) -> str:
    explicit_mode = str(settings.get("cookie_source_mode", "") or "").strip()
    if explicit_mode in COOKIE_SOURCE_MODES:
        return explicit_mode
    if bool(settings.get("use_cookies", False)) and str(
        settings.get("cookies_file_path", "") or ""
    ).strip():
        return COOKIE_SOURCE_FILE
    if any(str(settings.get(key, "") or "").strip() for key in _LEGACY_BROWSER_KEYS):
        return COOKIE_SOURCE_MANAGED
    return COOKIE_SOURCE_NONE


def set_cookie_source_mode(settings: dict, mode: str) -> None:
    if mode not in COOKIE_SOURCE_MODES:
        raise ValueError(f"Unsupported cookie source mode: {mode}")
    settings["cookie_source_mode"] = mode
    settings["use_cookies"] = mode == COOKIE_SOURCE_FILE
    for key in _LEGACY_BROWSER_KEYS:
        settings.pop(key, None)


def migrate_cookie_source_settings(settings: dict) -> bool:
    before = dict(settings)
    set_cookie_source_mode(settings, get_cookie_source_mode(settings))
    return settings != before


def build_browser_cookie_spec(browser: str, profile: str = "") -> str:
    browser_name = (browser or "").strip().casefold()
    profile_name = (profile or "").strip()
    if not browser_name:
        return ""
    return f"{browser_name}:{profile_name}" if profile_name else browser_name


def cookie_file_has_youtube_auth(path: str | os.PathLike[str]) -> bool:
    cookie_path = Path(path)
    try:
        lines = cookie_path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return False

    now = time.time()
    for raw_line in lines:
        line = raw_line.removeprefix("#HttpOnly_")
        if not line or line.startswith("#"):
            continue
        fields = line.split("\t")
        if len(fields) < 7:
            continue
        domain, expires_text, name, value = (
            fields[0].casefold(),
            fields[4],
            fields[5],
            fields[6],
        )
        if not _is_google_or_youtube_domain(domain):
            continue
        try:
            expires = int(float(expires_text or 0))
        except ValueError:
            continue
        if expires and expires <= now:
            continue
        if name in _YOUTUBE_AUTH_COOKIE_NAMES and value.strip():
            return True
    return False


def _valid_managed_source(
    source: DownloadCookieSource | None,
) -> DownloadCookieSource | None:
    if source is None:
        return None
    if (
        source.use_cookie_file
        and source.cookie_file_path
        and cookie_file_has_youtube_auth(source.cookie_file_path)
    ):
        return source
    if source.browser_spec:
        return source
    return None


def resolve_download_cookie_source(
    settings: dict,
    *,
    managed_source: DownloadCookieSource | None = None,
) -> DownloadCookieSource:
    mode = get_cookie_source_mode(settings)
    if mode == COOKIE_SOURCE_NONE:
        return DownloadCookieSource()

    if mode == COOKIE_SOURCE_FILE:
        cookie_path = str(settings.get("cookies_file_path", "") or "").strip()
        if cookie_path and cookie_file_has_youtube_auth(cookie_path):
            return DownloadCookieSource(True, cookie_path)
        return DownloadCookieSource(invalid_cookie_file=True)

    valid_managed = _valid_managed_source(managed_source)
    if valid_managed is not None:
        return DownloadCookieSource(
            use_cookie_file=valid_managed.use_cookie_file,
            cookie_file_path=valid_managed.cookie_file_path,
            browser_spec=valid_managed.browser_spec,
        )
    return DownloadCookieSource()
