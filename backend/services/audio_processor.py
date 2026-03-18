from __future__ import annotations

import subprocess
from pathlib import Path

from backend.utils.config import get_ffmpeg_binary


class AudioProcessingError(RuntimeError):
    pass


def convert_to_wav(input_audio_path: Path, output_wav_path: Path) -> Path:
    output_wav_path.parent.mkdir(parents=True, exist_ok=True)

    command = [
        get_ffmpeg_binary(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-i",
        str(input_audio_path),
        "-vn",
        "-ar",
        "48000",
        "-acodec",
        "pcm_s24le",
        str(output_wav_path),
    ]

    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise AudioProcessingError("ffmpeg is not installed or not available in PATH.") from exc
    except subprocess.CalledProcessError as exc:
        raise AudioProcessingError(f"ffmpeg failed to convert audio: {exc.stderr.strip()}") from exc

    if not output_wav_path.exists():
        raise AudioProcessingError("WAV conversion completed but output file is missing.")

    return output_wav_path
