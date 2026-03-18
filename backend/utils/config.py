import os
import shutil
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
STORAGE_ROOT = PROJECT_ROOT / "storage"
DOWNLOADS_DIR = STORAGE_ROOT / "downloads"
SAMPLES_DIR = STORAGE_ROOT / "samples"
EXPORTS_DIR = STORAGE_ROOT / "exports"

MAX_VIDEO_SECONDS = 30 * 60
MIN_SEGMENT_SECONDS = 1.0
MIN_EXPORT_SEGMENT_SECONDS = 0.1
MAX_SEGMENT_SECONDS = 8.0
MAX_SEGMENTS = 200

CLEANUP_TTL_MINUTES = 30
CLEANUP_INTERVAL_SECONDS = 5 * 60

ALLOWED_ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:4173",
    "http://127.0.0.1:4173",
]


def ensure_directories() -> None:
    for path in (STORAGE_ROOT, DOWNLOADS_DIR, SAMPLES_DIR, EXPORTS_DIR):
        path.mkdir(parents=True, exist_ok=True)


def get_ffmpeg_binary() -> str:
    env_binary = os.getenv("CHOPCHOP_FFMPEG_BINARY")
    if env_binary:
        return env_binary

    in_path = shutil.which("ffmpeg")
    if in_path:
        return in_path

    common_windows_locations = [
        Path(r"C:\Program Files\Derivative\TouchDesigner\bin\ffmpeg.exe"),
        Path(r"C:\Program Files\Muse\resources\app.asar.unpacked\node_modules\ffmpeg-static\ffmpeg.exe"),
    ]
    for candidate in common_windows_locations:
        if candidate.exists():
            return str(candidate)

    return "ffmpeg"
