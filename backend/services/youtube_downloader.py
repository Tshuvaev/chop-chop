from __future__ import annotations

import json
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

def _extract_video_id(url: str) -> str | None:
    parsed = urlparse(url)
    host = (parsed.netloc or "").lower()
    if host in ("youtu.be",) or host.endswith(".youtu.be"):
        return parsed.path.lstrip("/").split("/")[0] or None
    qs = parse_qs(parsed.query)
    return (qs.get("v") or [None])[0]


def _write_cookies_file() -> str | None:
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
                    "clientName": "ANDROID",
                    "clientVersion": "19.29.37",
                    "androidSdkVersion": 30,
                    "hl": "en",
                    "gl": "US",
                }
            },
            "videoId": "dQw4w9WgXcQ",
        }).encode()
        req = urllib.request.Request(
            "https://www.youtube.com/youtubei/v1/player",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "com.google.android.youtube/19.29.37 (Linux; U; Android 11) gzip",
                "X-YouTube-Client-Name": "3",
                "X-YouTube-Client-Version": "19.29.37",
            },
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            ctx = data.get("responseContext", {})
            return ctx.get("visitorData")
    except Exception:  # noqa: BLE001
        return None


def _base_opts(visitor_data: str | None = None) -> dict:
    extractor_args: dict = {
        "player_client": ["android", "android_music", "mweb", "web_creator"],
        "skip": ["translated_subs"],
    }
    if visitor_data:
        extractor_args["visitor_data"] = [visitor_data]

    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "extractor_args": {"youtube": extractor_args},
        "http_headers": {
            "User-Agent": (
                "com.google.android.youtube/19.29.37 (Linux; U; Android 11) gzip"
            ),
        },
        "retries": 3,
        "extractor_retries": 3,
        "socket_timeout": 30,
    }
    cookie_path = _write_cookies_file()
    if cookie_path:
        opts["cookiefile"] = cookie_path
    return opts


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

    # Get fresh visitor_data to help bypass bot check
    visitor_data = _fetch_visitor_data()

    opts = _base_opts(visitor_data)
    output_template = str(session_download_dir / f"{session_id}.%(ext)s")

    download_opts = {
        **opts,
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "restrictfilenames": True,
        "overwrites": True,
    }

    last_error: Exception | None = None

    try:
        with yt_dlp.YoutubeDL(download_opts) as ydl:
            info = ydl.extract_info(url, download=True)

        if info is None:
            raise YouTubeDownloadError("No info returned from yt-dlp.")

        duration = float(info.get("duration") or 0.0)
        if duration <= 0:
            raise YouTubeDownloadError("Could not determine video duration.")
        if duration > MAX_VIDEO_SECONDS:
            raise VideoTooLongError("Video is longer than 30 minutes.")

        title = str(info.get("title") or "Untitled YouTube Audio")
        downloaded = _find_latest_download(session_download_dir)
        if downloaded:
            return downloaded, title, duration

    except (VideoTooLongError, InvalidYouTubeUrlError):
        raise
    except Exception as exc:  # noqa: BLE001
        last_error = exc

    raise YouTubeDownloadError(
        "Could not download audio from YouTube. "
        "YouTube is blocking server requests. "
        "Try adding YOUTUBE_COOKIES to Railway environment variables."
    )


def _find_latest_download(folder: Path) -> Path | None:
    candidates = [
        item for item in folder.iterdir()
        if item.is_file() and item.suffix.lower() not in {".part", ".tmp"}
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)
