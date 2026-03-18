from __future__ import annotations

import re
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse

from backend.models.sample import (
    AnalyzeRequest,
    AnalyzeResponse,
    ExportRequest,
    ExportResponse,
    SampleSegment,
    SingleExportRequest,
)
from backend.services.ai_segmenter import SegmentationError, detect_segments
from backend.services.audio_processor import AudioProcessingError, convert_to_wav
from backend.services.exporter import ExportError, export_samples_to_zip, export_single_sample
from backend.services.session_store import session_store
from backend.services.sound_classifier import RECOMMENDED_AI_TOOLS, SOUND_CATEGORY_CATALOG
from backend.services.youtube_downloader import (
    InvalidYouTubeUrlError,
    VideoTooLongError,
    YouTubeDownloadError,
    download_audio,
)
from backend.utils.cleanup import cleanup_storage, purge_session_files
from backend.utils.config import (
    CLEANUP_TTL_MINUTES,
    DOWNLOADS_DIR,
    EXPORTS_DIR,
    MAX_SEGMENT_SECONDS,
    MIN_EXPORT_SEGMENT_SECONDS,
    MIN_SEGMENT_SECONDS,
)

router = APIRouter()
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/sound-categories")
def sound_categories() -> dict[str, object]:
    return {
        "categories": SOUND_CATEGORY_CATALOG,
        "recommended_ai_tools": RECOMMENDED_AI_TOOLS,
    }


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_video(
    payload: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
) -> AnalyzeResponse:
    session_id = _resolve_session_id(x_session_id)

    try:
        title, duration, segments = await run_in_threadpool(_run_analysis_pipeline, payload.url, session_id)
    except InvalidYouTubeUrlError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except VideoTooLongError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except (YouTubeDownloadError, AudioProcessingError, SegmentationError) as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected analysis error.") from exc

    background_tasks.add_task(cleanup_storage, CLEANUP_TTL_MINUTES)

    return AnalyzeResponse(
        session_id=session_id,
        title=title,
        duration=round(duration, 3),
        audio_url=f"/session/{session_id}/audio",
        segments=segments,
    )


@router.post("/export", response_model=ExportResponse)
async def export_samples(
    payload: ExportRequest,
    background_tasks: BackgroundTasks,
    x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
) -> ExportResponse:
    session_id = _resolve_session_id(x_session_id)
    session = session_store.get(session_id)

    if session is None or session.wav_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No analyzed audio found for this session. Analyze a video first.",
        )

    normalized_segments = _normalize_segments(payload.segments)
    if not normalized_segments:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="No valid segments to export.")

    try:
        zip_path = await run_in_threadpool(export_samples_to_zip, session_id, session.wav_path, normalized_segments)
    except ExportError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected export error.") from exc

    session_store.touch(session_id)
    background_tasks.add_task(cleanup_storage, CLEANUP_TTL_MINUTES)

    relative_zip_path = zip_path.relative_to(EXPORTS_DIR).as_posix()
    return ExportResponse(
        download_url=f"/download/{relative_zip_path}",
        file_name=zip_path.name,
    )


@router.post("/export/sample", response_model=ExportResponse)
async def export_single(
    payload: SingleExportRequest,
    background_tasks: BackgroundTasks,
    x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
) -> ExportResponse:
    session_id = _resolve_session_id(x_session_id)
    session = session_store.get(session_id)

    if session is None or session.wav_path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No analyzed audio found for this session. Analyze a video first.",
        )

    start = round(float(payload.segment.start), 3)
    end = round(float(payload.segment.end), 3)
    duration = end - start
    if start < 0 or end <= start:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid segment timing.")
    if duration < MIN_EXPORT_SEGMENT_SECONDS or duration > MAX_SEGMENT_SECONDS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Segment must be between {MIN_EXPORT_SEGMENT_SECONDS:g} and {MAX_SEGMENT_SECONDS:g} seconds.",
        )

    segment = SampleSegment(
        id=int(payload.segment.id or 1),
        name=payload.segment.name or "sample",
        start=start,
        end=end,
    )
    segment_index = int(payload.segment.id or 1)
    segment_index = max(1, segment_index)

    try:
        sample_path = await run_in_threadpool(
            export_single_sample,
            session_id,
            session.wav_path,
            segment,
            segment_index,
        )
    except ExportError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Unexpected single export error.") from exc

    session_store.touch(session_id)
    background_tasks.add_task(cleanup_storage, CLEANUP_TTL_MINUTES)

    relative_path = sample_path.relative_to(EXPORTS_DIR).as_posix()
    return ExportResponse(
        download_url=f"/download/{relative_path}",
        file_name=sample_path.name,
    )


@router.get("/download/{file_path:path}")
def download_export(file_path: str) -> FileResponse:
    exports_root = EXPORTS_DIR.resolve()
    requested_path = (EXPORTS_DIR / file_path).resolve()

    if not requested_path.is_relative_to(exports_root):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

    if not requested_path.exists() or not requested_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

    media_type = "application/zip"
    if requested_path.suffix.lower() == ".wav":
        media_type = "audio/wav"

    return FileResponse(
        path=requested_path,
        filename=requested_path.name,
        media_type=media_type,
    )


@router.get("/session/{session_id}/audio")
def stream_session_audio(session_id: str) -> FileResponse:
    session = session_store.get(session_id)
    if session is None or session.wav_path is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session audio not found.")

    if not session.wav_path.exists():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session audio file is missing.")

    return FileResponse(path=session.wav_path, media_type="audio/wav", filename=f"{session_id}.wav")


def _run_analysis_pipeline(url: str, session_id: str) -> tuple[str, float, list[SampleSegment]]:
    purge_session_files(session_id)

    downloaded_audio, title, downloaded_duration = download_audio(url=url, session_id=session_id, downloads_root=DOWNLOADS_DIR)

    wav_path = DOWNLOADS_DIR / session_id / "source.wav"
    convert_to_wav(downloaded_audio, wav_path)

    segments, actual_duration = detect_segments(
        wav_path=wav_path,
        min_length=MIN_SEGMENT_SECONDS,
        max_length=MAX_SEGMENT_SECONDS,
    )

    session_store.save_analysis(
        session_id=session_id,
        source_url=url,
        title=title,
        wav_path=wav_path,
        duration=downloaded_duration or actual_duration,
        segments=segments,
    )

    return title, downloaded_duration or actual_duration, segments


def _resolve_session_id(session_id: str | None) -> str:
    if not session_id:
        return uuid4().hex

    clean_value = session_id.strip()
    if not SESSION_ID_PATTERN.fullmatch(clean_value):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid X-Session-ID header format.",
        )

    return clean_value


def _normalize_segments(segments: list[SampleSegment]) -> list[SampleSegment]:
    normalized: list[SampleSegment] = []

    for idx, segment in enumerate(segments, start=1):
        start = round(float(segment.start), 3)
        end = round(float(segment.end), 3)

        if end <= start:
            continue

        duration = end - start
        if duration < MIN_EXPORT_SEGMENT_SECONDS or duration > MAX_SEGMENT_SECONDS:
            continue

        normalized.append(
            SampleSegment(
                id=idx,
                name=f"sample_{idx:03d}",
                start=start,
                end=end,
            )
        )

    return normalized
