from __future__ import annotations

import json
import os
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yt_dlp
from yt_dlp.utils import DownloadError as YtDlpDownloadError

from backend.utils.config import MAX_VIDEO_SECONDS, YOUTUBE_COOKIES

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class InvalidYouTubeUrlError(ValueError):
    pass


class VideoTooLongError(ValueError):
    pass


class YouTubeDownloadError(RuntimeError):
    pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

_BROWSER_HEADERS = {
    "User-Agent": _BROWSER_UA,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Sec-Ch-Ua": '"Chromium";v="131", "Not_A Brand";v="24"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

# Proxy for YouTube (set YOUTUBE_PROXY=socks5://... or http://...)
_YOUTUBE_PROXY = os.getenv("YOUTUBE_PROXY", "").strip()


def _extract_video_id(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if host in ("youtu.be",) or host.endswith(".youtu.be"):
        return parsed.path.lstrip("/").split("/")[0] or None
    qs = parse_qs(parsed.query)
    return (qs.get("v") or [None])[0]


def _write_cookies_file() -> str | None:
    # 1. Check for file saved by /receive-cookies endpoint
    saved_file = os.environ.get("YOUTUBE_COOKIES_FILE", "").strip()
    if saved_file and os.path.isfile(saved_file):
        return saved_file
    # 2. Check for browser-received cookie file in project root
    project_cookie = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "yt_cookies.txt")
    if os.path.isfile(project_cookie):
        return project_cookie
    # 3. Fall back to env var with inline cookies
    if not YOUTUBE_COOKIES:
        return None
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
    tmp.write(YOUTUBE_COOKIES)
    tmp.close()
    return tmp.name


def _fetch_visitor_data() -> str | None:
    """Get a fresh visitorData token from YouTube InnerTube API."""
    try:
        payload = json.dumps({
            "context": {
                "client": {
                    "clientName": "WEB",
                    "clientVersion": "2.20241126.01.00",
                    "hl": "en",
                    "gl": "US",
                }
            },
        }).encode()
        req = urllib.request.Request(
            "https://www.youtube.com/youtubei/v1/visitor_id",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": _BROWSER_UA,
                "X-YouTube-Client-Name": "1",
                "X-YouTube-Client-Version": "2.20241126.01.00",
                "Origin": "https://www.youtube.com",
                "Referer": "https://www.youtube.com/",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data.get("responseContext", {}).get("visitorData")
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Attempt strategies (ordered by reliability)
# ---------------------------------------------------------------------------

def _make_opts(
    *,
    visitor_data: str | None = None,
    cookie_path: str | None = None,
    use_proxy: bool = False,
    player_clients: list[str] | None = None,
) -> dict:
    if player_clients is None:
        player_clients = ["web", "mweb"]

    extractor_args: dict = {
        "player_client": player_clients,
        "skip": ["translated_subs"],
    }
    if visitor_data:
        extractor_args["visitor_data"] = [visitor_data]

    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "extractor_args": {"youtube": extractor_args},
        "http_headers": {**_BROWSER_HEADERS},
        "retries": 3,
        "extractor_retries": 3,
        "socket_timeout": 30,
    }

    if cookie_path:
        opts["cookiefile"] = cookie_path

    if use_proxy and _YOUTUBE_PROXY:
        opts["proxy"] = _YOUTUBE_PROXY

    return opts


def _build_attempts(visitor_data: str | None, cookie_path: str | None) -> list[dict]:
    """Return a list of yt-dlp option dicts to try in order."""
    attempts = []

    # 1. Cookies + web client (best if cookies are available)
    if cookie_path:
        attempts.append(
            _make_opts(
                visitor_data=visitor_data,
                cookie_path=cookie_path,
                player_clients=["web", "mweb"],
            )
        )

    # 2. Web client without cookies (works if IP is not blocked)
    attempts.append(
        _make_opts(
            visitor_data=visitor_data,
            cookie_path=cookie_path,
            player_clients=["web", "mweb"],
        )
    )

    # 3. Android clients (different bot-detection path)
    attempts.append(
        _make_opts(
            visitor_data=visitor_data,
            cookie_path=cookie_path,
            player_clients=["android", "android_music"],
        )
    )

    # 4. tv_embedded + web_creator (minimal bot-detection)
    attempts.append(
        _make_opts(
            visitor_data=visitor_data,
            cookie_path=cookie_path,
            player_clients=["tv_embedded", "web_creator"],
        )
    )

    # 5. Proxy fallback (if YOUTUBE_PROXY is set)
    if _YOUTUBE_PROXY:
        attempts.append(
            _make_opts(
                visitor_data=visitor_data,
                cookie_path=cookie_path,
                use_proxy=True,
                player_clients=["web", "mweb"],
            )
        )

    return attempts


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def validate_youtube_url(url: str) -> None:
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower().split(":")[0]
    is_youtube_host = (
        host == "youtu.be"
        or host.endswith(".youtu.be")
        or host == "youtube.com"
        or host.endswith(".youtube.com")
    )
    if parsed.scheme not in {"http", "https"} or not is_youtube_host:
        raise InvalidYouTubeUrlError(
            "Invalid YouTube URL. Please provide a youtube.com or youtu.be link."
        )


def download_audio(url: str, session_id: str, downloads_root: Path) -> tuple[Path, str, float]:
    validate_youtube_url(url)

    session_download_dir = downloads_root / session_id
    session_download_dir.mkdir(parents=True, exist_ok=True)

    visitor_data = _fetch_visitor_data()
    cookie_path = _write_cookies_file()

    output_template = str(session_download_dir / f"{session_id}.%(ext)s")
    attempts = _build_attempts(visitor_data, cookie_path)
    last_error: Exception | None = None

    for opts in attempts:
        download_opts = {
            **opts,
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "restrictfilenames": True,
            "overwrites": True,
        }

        try:
            with yt_dlp.YoutubeDL(download_opts) as ydl:
                info = ydl.extract_info(url, download=True)

            if info is None:
                continue

            duration = float(info.get("duration") or 0.0)
            if duration <= 0:
                continue
            if duration > MAX_VIDEO_SECONDS:
                raise VideoTooLongError("Video is longer than 30 minutes.")

            title = str(info.get("title") or "Untitled YouTube Audio")
            downloaded = _find_latest_download(session_download_dir)
            if downloaded:
                return downloaded, title, duration

        except (VideoTooLongError, InvalidYouTubeUrlError):
            raise
        except Exception as exc:
            last_error = exc
            continue

    # Clean up temp cookie file
    if cookie_path:
        try:
            os.unlink(cookie_path)
        except OSError:
            pass

    hint = (
        "Try setting YOUTUBE_COOKIES or YOUTUBE_PROXY environment variables."
        if not YOUTUBE_COOKIES and not _YOUTUBE_PROXY
        else "All download strategies failed."
    )
    raise YouTubeDownloadError(
        f"Could not download audio from YouTube. {hint}"
    )


def _find_latest_download(folder: Path) -> Path | None:
    candidates = [
        item for item in folder.iterdir()
        if item.is_file() and item.suffix.lower() not in {".part", ".tmp"}
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)
