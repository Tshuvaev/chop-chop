from __future__ import annotations

import shutil
import time
from pathlib import Path

from backend.services.session_store import session_store
from backend.utils.config import CLEANUP_TTL_MINUTES, DOWNLOADS_DIR, EXPORTS_DIR, SAMPLES_DIR


def cleanup_storage(ttl_minutes: int = CLEANUP_TTL_MINUTES) -> None:
    ttl_seconds = ttl_minutes * 60
    now = time.time()

    for root_dir in (DOWNLOADS_DIR, SAMPLES_DIR, EXPORTS_DIR):
        _cleanup_directory(root_dir, now, ttl_seconds)

    for session_id in session_store.expired_session_ids(ttl_seconds):
        purge_session_files(session_id)
        session_store.remove(session_id)


def purge_session_files(session_id: str) -> None:
    for root_dir in (DOWNLOADS_DIR, SAMPLES_DIR, EXPORTS_DIR):
        path = root_dir / session_id
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)


def _cleanup_directory(root_dir: Path, now: float, ttl_seconds: int) -> None:
    if not root_dir.exists():
        return

    for child in root_dir.iterdir():
        try:
            age = now - child.stat().st_mtime
        except FileNotFoundError:
            continue

        if age <= ttl_seconds:
            continue

        if child.is_dir():
            shutil.rmtree(child, ignore_errors=True)
        else:
            child.unlink(missing_ok=True)
