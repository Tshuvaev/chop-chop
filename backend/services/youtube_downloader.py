from __future__ import annotations

import tempfile
from pathlib import Path
from urllib.parse import urlparse

import yt_dlp
from yt_dlp.utils import DownloadError as YtDlpDownloadError

from backend.utils.config import MAX_VIDEO_SECONDS, YOUTUBE_COOKIES


class InvalidYouTubeUrlError(ValueError):
    pass


class VideoTooLongError(ValueError):
    pass


class YouTubeDownloadError(RuntimeError):
    pass


def _write_cookies_file() -> str | None:
    """Write YOUTUBE_COOKIES env var content to a temp file, return path or None."""
    if not YOUTUBE_COOKIES:
        return None
    tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8")
    tmp.write(YOUTUBE_COOKIES)
    tmp.close()
    return tmp.name


def _base_opts() -> dict:
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["ios", "mweb"],
            }
        },
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
            ),
        },
        "retries": 5,
        "extractor_retries": 5,
        "socket_timeout": 30,
    }
    cookie_path = _write_cookies_file()
    if cookie_path:
        opts["cookiefile"] = cookie_path
    return opts


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
        raise InvalidYouTubeUrlError("Invalid YouTube URL. Please provide a youtube.com or youtu.be link.")


def fetch_metadata(url: str) -> tuple[str, float]:
    options = {
        **_base_opts(),
        "skip_download": True,
        "extract_flat": False,
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            info = ydl.extract_info(url, download=False)
    except YtDlpDownloadError as exc:
        raise YouTubeDownloadError("Could not fetch video metadata from YouTube.") from exc
    except Exception as exc:  # noqa: BLE001
        raise YouTubeDownloadError("Unexpected error while reading YouTube metadata.") from exc

    if not info:
        raise YouTubeDownloadError("No metadata received from YouTube.")

    duration = float(info.get("duration") or 0.0)
    if duration <= 0:
        raise YouTubeDownloadError("Could not determine video duration.")

    if duration > MAX_VIDEO_SECONDS:
        raise VideoTooLongError("Video is longer than 30 minutes. Please choose a shorter video.")

    title = str(info.get("title") or "Untitled YouTube Audio")
    return title, duration


def download_audio(url: str, session_id: str, downloads_root: Path) -> tuple[Path, str, float]:
    validate_youtube_url(url)
    title, duration = fetch_metadata(url)

    session_download_dir = downloads_root / session_id
    session_download_dir.mkdir(parents=True, exist_ok=True)

    output_template = str(session_download_dir / f"{session_id}.%(ext)s")
    options = {
        **_base_opts(),
        "format": "bestaudio/best",
        "outtmpl": output_template,
        "restrictfilenames": True,
        "overwrites": True,
    }

    try:
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.extract_info(url, download=True)
    except YtDlpDownloadError as exc:
        raise YouTubeDownloadError("Failed to download audio from YouTube.") from exc
    except Exception as exc:  # noqa: BLE001
        raise YouTubeDownloadError("Unexpected error while downloading YouTube audio.") from exc

    downloaded_file = _find_latest_download(session_download_dir)
    if downloaded_file is None:
        raise YouTubeDownloadError("Audio file was not created after download.")

    return downloaded_file, title, duration


def _find_latest_download(folder: Path) -> Path | None:
    candidates = [
        item
        for item in folder.iterdir()
        if item.is_file() and item.suffix.lower() not in {".part", ".tmp"}
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda file_path: file_path.stat().st_mtime)
