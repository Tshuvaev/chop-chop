from __future__ import annotations

import re
import tempfile
import urllib.request
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import yt_dlp
from yt_dlp.utils import DownloadError as YtDlpDownloadError

from backend.utils.config import MAX_VIDEO_SECONDS, YOUTUBE_COOKIES

# Public Invidious instances used as fallback when yt-dlp is blocked
_INVIDIOUS_INSTANCES = [
    "https://yewtu.be",
    "https://invidious.kavin.rocks",
    "https://inv.riverside.rocks",
    "https://invidious.nerdvpn.de",
]


class InvalidYouTubeUrlError(ValueError):
    pass


class VideoTooLongError(ValueError):
    pass


class YouTubeDownloadError(RuntimeError):
    pass


def _extract_video_id(url: str) -> str | None:
    parsed = urlparse(url)
    if parsed.netloc in ("youtu.be",) or parsed.netloc.endswith(".youtu.be"):
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


def _base_opts() -> dict:
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["web_embedded", "tv_embedded", "android_music", "android"],
                "skip": ["translated_subs"],
            }
        },
        "http_headers": {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Cookie": "CONSENT=YES+cb; SOCS=CAI",
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
# Invidious fallback
# ---------------------------------------------------------------------------

def _invidious_fetch(video_id: str) -> dict | None:
    """Try each Invidious instance and return the JSON response or None."""
    import json
    for instance in _INVIDIOUS_INSTANCES:
        api_url = f"{instance}/api/v1/videos/{video_id}?fields=title,lengthSeconds,adaptiveFormats"
        try:
            req = urllib.request.Request(api_url, headers={"User-Agent": "chop-chop/1.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                return json.loads(resp.read().decode())
        except Exception:  # noqa: BLE001
            continue
    return None


def _invidious_best_audio_url(data: dict) -> str | None:
    """Pick the highest-bitrate audio-only stream from Invidious adaptive formats."""
    formats = data.get("adaptiveFormats") or []
    audio = [f for f in formats if f.get("type", "").startswith("audio/")]
    if not audio:
        return None
    best = max(audio, key=lambda f: int(f.get("bitrate", 0)))
    return best.get("url")


def _download_url_to_file(audio_url: str, dest: Path) -> None:
    req = urllib.request.Request(audio_url, headers={"User-Agent": "chop-chop/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as out:
        while chunk := resp.read(65536):
            out.write(chunk)


def _try_invidious(url: str, session_download_dir: Path, session_id: str) -> tuple[Path, str, float] | None:
    """Attempt metadata + download via Invidious. Returns (path, title, duration) or None."""
    video_id = _extract_video_id(url)
    if not video_id:
        return None

    data = _invidious_fetch(video_id)
    if not data:
        return None

    title = str(data.get("title") or "Untitled YouTube Audio")
    duration = float(data.get("lengthSeconds") or 0)
    if duration <= 0:
        return None

    audio_url = _invidious_best_audio_url(data)
    if not audio_url:
        return None

    dest = session_download_dir / f"{session_id}.webm"
    _download_url_to_file(audio_url, dest)

    if not dest.exists() or dest.stat().st_size < 1024:
        return None

    return dest, title, duration


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
        raise InvalidYouTubeUrlError("Invalid YouTube URL. Please provide a youtube.com or youtu.be link.")


def fetch_metadata(url: str) -> tuple[str, float]:
    options = {**_base_opts(), "skip_download": True, "extract_flat": False}
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

    return str(info.get("title") or "Untitled YouTube Audio"), duration


def download_audio(url: str, session_id: str, downloads_root: Path) -> tuple[Path, str, float]:
    validate_youtube_url(url)

    session_download_dir = downloads_root / session_id
    session_download_dir.mkdir(parents=True, exist_ok=True)

    # --- Try yt-dlp first ---
    ytdlp_error: Exception | None = None
    try:
        title, duration = fetch_metadata(url)
        if duration > MAX_VIDEO_SECONDS:
            raise VideoTooLongError("Video is longer than 30 minutes. Please choose a shorter video.")

        output_template = str(session_download_dir / f"{session_id}.%(ext)s")
        options = {
            **_base_opts(),
            "format": "bestaudio/best",
            "outtmpl": output_template,
            "restrictfilenames": True,
            "overwrites": True,
        }
        with yt_dlp.YoutubeDL(options) as ydl:
            ydl.extract_info(url, download=True)

        downloaded = _find_latest_download(session_download_dir)
        if downloaded:
            return downloaded, title, duration
    except (VideoTooLongError, InvalidYouTubeUrlError):
        raise
    except Exception as exc:  # noqa: BLE001
        ytdlp_error = exc

    # --- Fallback: Invidious ---
    try:
        result = _try_invidious(url, session_download_dir, session_id)
        if result:
            path, title, duration = result
            if duration > MAX_VIDEO_SECONDS:
                raise VideoTooLongError("Video is longer than 30 minutes. Please choose a shorter video.")
            return path, title, duration
    except (VideoTooLongError, InvalidYouTubeUrlError):
        raise
    except Exception:  # noqa: BLE001
        pass

    raise YouTubeDownloadError(
        "Could not download audio from YouTube. "
        "Please try again later or use a different video."
    )


def _find_latest_download(folder: Path) -> Path | None:
    candidates = [
        item for item in folder.iterdir()
        if item.is_file() and item.suffix.lower() not in {".part", ".tmp"}
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)
