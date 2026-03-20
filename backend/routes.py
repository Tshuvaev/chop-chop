from __future__ import annotations

import re
import smtplib
from email.mime.text import MIMEText
from uuid import uuid4

from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request, status
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
    IDEA_EMAIL_FROM,
    IDEA_EMAIL_PASSWORD,
    IDEA_EMAIL_TO,
    MAX_SEGMENT_SECONDS,
    MIN_EXPORT_SEGMENT_SECONDS,
    MIN_SEGMENT_SECONDS,
)

router = APIRouter()
SESSION_ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]{8,128}$")


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.post("/receive-cookies")
async def receive_cookies(request: Request) -> dict[str, str]:
    """Receive YouTube cookies from browser and store them for yt-dlp."""
    import os
    body = await request.body()
    text = body.decode("utf-8", errors="replace").strip()
    if not text or "youtube.com" not in text:
        raise HTTPException(status_code=400, detail="Invalid cookie data.")
    cookie_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "yt_cookies.txt")
    with open(cookie_path, "w", encoding="utf-8") as f:
        f.write(text + "\n")
    os.environ["YOUTUBE_COOKIES_FILE"] = cookie_path
    return {"status": "saved", "count": text.count(".youtube.com")}


@router.post("/idea")
async def submit_idea(payload: dict) -> dict[str, str]:
    text = str(payload.get("text", "")).strip()
    if not text:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Idea text is empty.")
    if len(text) > 4000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Text too long.")

    if not IDEA_EMAIL_FROM or not IDEA_EMAIL_PASSWORD:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="Email not configured.")

    try:
        msg = MIMEText(text, "plain", "utf-8")
        msg["Subject"] = "Slicer — идея от пользователя"
        msg["From"] = IDEA_EMAIL_FROM
        msg["To"] = IDEA_EMAIL_TO

        with smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10) as server:
            server.login(IDEA_EMAIL_FROM, IDEA_EMAIL_PASSWORD)
            server.sendmail(IDEA_EMAIL_FROM, IDEA_EMAIL_TO, msg.as_string())
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Failed to send email.") from exc

    return {"status": "sent"}


@router.get("/sound-categories")
def sound_categories() -> dict[str, object]:
    return {
        "categories": SOUND_CATEGORY_CATALOG,
        "recommended_ai_tools": RECOMMENDED_AI_TOOLS,
    }


@router.post("/analyze")
async def analyze_video(
    payload: AnalyzeRequest,
    background_tasks: BackgroundTasks,
    x_session_id: str | None = Header(default=None, alias="X-Session-ID"),
) -> dict[str, str]:
    """Start analysis in the background and return immediately."""
    session_id = _resolve_session_id(x_session_id)
    session_store.get_or_create(session_id)
    session_store.update_progress(session_id, "queued", 1)
    background_tasks.add_task(_run_analysis_pipeline_bg, payload.url, session_id)
    return {"status": "started", "session_id": session_id}


@router.get("/session/{session_id}/status")
def session_status(session_id: str) -> dict[str, object]:
    session = session_store.get(session_id)
    if session is None:
        return {"stage": "idle", "pct": 0, "error": None}
    return {
        "stage": session.progress_stage,
        "pct": session.progress_pct,
        "error": session.error,
    }


@router.get("/session/{session_id}/result", response_model=AnalyzeResponse)
def session_result(session_id: str) -> AnalyzeResponse:
    session = session_store.get(session_id)
    if session is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session not found.")
    if session.progress_stage == "error":
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=session.error or "Analysis failed.")
    if session.progress_stage != "done":
        raise HTTPException(status_code=status.HTTP_202_ACCEPTED, detail="Analysis still in progress.")

    return AnalyzeResponse(
        session_id=session_id,
        title=session.title or "Untitled",
        duration=round(session.duration, 3),
        bpm=session.bpm,
        audio_url=f"/session/{session_id}/audio",
        segments=session.segments,
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
    segment_index = max(1, int(payload.segment.id or 1))

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


def _run_analysis_pipeline_bg(url: str, session_id: str) -> None:
    """Background task: full analysis pipeline. Stores result in session_store."""
    try:
        purge_session_files(session_id)
        session_store.update_progress(session_id, "downloading", 5)

        downloaded_audio, title, downloaded_duration = download_audio(
            url=url, session_id=session_id, downloads_root=DOWNLOADS_DIR
        )
        session_store.update_progress(session_id, "converting", 45)

        wav_path = DOWNLOADS_DIR / session_id / "source.wav"
        convert_to_wav(downloaded_audio, wav_path)
        session_store.update_progress(session_id, "segmenting", 65)

        segments, actual_duration, bpm = detect_segments(
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
            bpm=bpm,
            segments=segments,
        )
        session_store.update_progress(session_id, "done", 100)
        cleanup_storage(CLEANUP_TTL_MINUTES)

    except (InvalidYouTubeUrlError, VideoTooLongError) as exc:
        session_store.set_error(session_id, str(exc))
    except (YouTubeDownloadError, AudioProcessingError, SegmentationError) as exc:
        session_store.set_error(session_id, str(exc))
    except Exception as exc:  # noqa: BLE001
        session_store.set_error(session_id, "Unexpected analysis error.")


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
