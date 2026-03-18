from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Dict, List, Optional

from backend.models.sample import SampleSegment


@dataclass
class SessionData:
    session_id: str
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    source_url: Optional[str] = None
    title: Optional[str] = None
    wav_path: Optional[Path] = None
    duration: float = 0.0
    segments: List[SampleSegment] = field(default_factory=list)


class SessionStore:
    def __init__(self) -> None:
        self._sessions: Dict[str, SessionData] = {}
        self._lock = Lock()

    def get_or_create(self, session_id: str) -> SessionData:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                session = SessionData(session_id=session_id)
                self._sessions[session_id] = session
            session.updated_at = datetime.now(timezone.utc)
            return session

    def get(self, session_id: str) -> Optional[SessionData]:
        with self._lock:
            return self._sessions.get(session_id)

    def save_analysis(
        self,
        session_id: str,
        source_url: str,
        title: str,
        wav_path: Path,
        duration: float,
        segments: List[SampleSegment],
    ) -> SessionData:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                session = SessionData(session_id=session_id)
                self._sessions[session_id] = session

            session.source_url = source_url
            session.title = title
            session.wav_path = wav_path
            session.duration = duration
            session.segments = segments
            session.updated_at = datetime.now(timezone.utc)
            return session

    def touch(self, session_id: str) -> None:
        with self._lock:
            session = self._sessions.get(session_id)
            if session:
                session.updated_at = datetime.now(timezone.utc)

    def remove(self, session_id: str) -> None:
        with self._lock:
            self._sessions.pop(session_id, None)

    def expired_session_ids(self, ttl_seconds: int) -> List[str]:
        now = datetime.now(timezone.utc)
        expired: List[str] = []
        with self._lock:
            for session_id, session in self._sessions.items():
                age = (now - session.updated_at).total_seconds()
                if age > ttl_seconds:
                    expired.append(session_id)
        return expired


session_store = SessionStore()
