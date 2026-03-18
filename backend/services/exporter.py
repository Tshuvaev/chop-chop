from __future__ import annotations

import shutil
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import List

from backend.models.sample import SampleSegment
from backend.utils.config import (
    EXPORTS_DIR,
    MAX_SEGMENT_SECONDS,
    MIN_EXPORT_SEGMENT_SECONDS,
    SAMPLES_DIR,
    get_ffmpeg_binary,
)


class ExportError(RuntimeError):
    pass


def export_samples_to_zip(
    session_id: str,
    source_wav_path: Path,
    segments: List[SampleSegment],
) -> Path:
    if not source_wav_path.exists():
        raise ExportError("Source WAV file is missing. Please analyze the video again.")

    session_samples_dir = SAMPLES_DIR / session_id
    session_exports_dir = EXPORTS_DIR / session_id

    if session_samples_dir.exists():
        shutil.rmtree(session_samples_dir, ignore_errors=True)
    session_samples_dir.mkdir(parents=True, exist_ok=True)

    session_exports_dir.mkdir(parents=True, exist_ok=True)

    generated_files: List[Path] = []
    for idx, segment in enumerate(segments, start=1):
        start = float(segment.start)
        end = float(segment.end)
        _validate_segment_length(idx, start, end)

        output_file = session_samples_dir / f"sample_{idx:03d}.wav"
        _cut_wav_segment(source_wav_path, output_file, start, end)
        generated_files.append(output_file)

    zip_path = session_exports_dir / "sample_pack.zip"
    with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        for file_path in generated_files:
            archive.write(file_path, arcname=file_path.name)

    return zip_path


def export_single_sample(
    session_id: str,
    source_wav_path: Path,
    segment: SampleSegment,
    sample_index: int,
) -> Path:
    if not source_wav_path.exists():
        raise ExportError("Source WAV file is missing. Please analyze the video again.")

    start = float(segment.start)
    end = float(segment.end)
    _validate_segment_length(sample_index, start, end)

    session_exports_dir = EXPORTS_DIR / session_id / "single"
    session_exports_dir.mkdir(parents=True, exist_ok=True)

    start_ms = int(round(start * 1000))
    end_ms = int(round(end * 1000))
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    output_file = session_exports_dir / f"sample_{sample_index:03d}_{start_ms}_{end_ms}_{timestamp}.wav"
    _cut_wav_segment(source_wav_path, output_file, start, end)
    return output_file


def _cut_wav_segment(source: Path, destination: Path, start: float, end: float) -> None:
    command = [
        get_ffmpeg_binary(),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start:.3f}",
        "-to",
        f"{end:.3f}",
        "-i",
        str(source),
        "-ar",
        "48000",
        "-acodec",
        "pcm_s24le",
        str(destination),
    ]

    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError as exc:
        raise ExportError("ffmpeg is not installed or not available in PATH.") from exc
    except subprocess.CalledProcessError as exc:
        raise ExportError(f"ffmpeg failed while exporting samples: {exc.stderr.strip()}") from exc


def _validate_segment_length(segment_index: int, start: float, end: float) -> None:
    length = end - start
    if length < MIN_EXPORT_SEGMENT_SECONDS:
        raise ExportError(
            f"Segment {segment_index} is shorter than {MIN_EXPORT_SEGMENT_SECONDS:g} second. "
            "Please increase the segment length before exporting."
        )

    if length > MAX_SEGMENT_SECONDS:
        raise ExportError(
            f"Segment {segment_index} is longer than {MAX_SEGMENT_SECONDS:.0f} seconds. "
            "Please shorten the segment before exporting."
        )
