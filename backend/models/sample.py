from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field, field_validator


class CategoryScore(BaseModel):
    category: str = Field(..., min_length=1)
    score: float = Field(..., ge=0, le=1)


class SampleSegment(BaseModel):
    id: Optional[int] = None
    name: Optional[str] = None
    start: float = Field(..., ge=0)
    end: float = Field(..., gt=0)
    waveform: Optional[List[float]] = None
    clipping_ratio: Optional[float] = Field(default=None, ge=0, le=1)
    is_clipping: Optional[bool] = None
    window_start: Optional[float] = Field(default=None, ge=0)
    window_end: Optional[float] = Field(default=None, gt=0)
    sound_type: Optional[str] = None
    sound_type_confidence: Optional[float] = Field(default=None, ge=0, le=1)
    sound_type_candidates: Optional[List[CategoryScore]] = None
    bpm: Optional[float] = None
    sample_type: Optional[str] = None
    transient_type: Optional[str] = None
    key: Optional[str] = None
    interest_score: Optional[float] = Field(default=None, ge=0, le=1)
    is_duplicate: Optional[bool] = None
    pitch: Optional[int] = Field(default=0, ge=-5, le=5)

    @field_validator("start", "end", mode="before")
    @classmethod
    def _coerce_to_float(cls, value: float | int | str) -> float:
        return float(value)

    @field_validator("end")
    @classmethod
    def _validate_end_after_start(cls, value: float, info) -> float:
        start = info.data.get("start", 0)
        if value <= start:
            raise ValueError("end must be greater than start")
        return value


class AnalyzeRequest(BaseModel):
    url: str = Field(..., min_length=1)

    @field_validator("url", mode="before")
    @classmethod
    def _strip_url(cls, value: str) -> str:
        return str(value).strip()


class AnalyzeResponse(BaseModel):
    session_id: str
    title: str
    duration: float
    bpm: Optional[float] = None
    audio_url: str
    segments: List[SampleSegment]


class ExportRequest(BaseModel):
    segments: List[SampleSegment]


class ExportResponse(BaseModel):
    download_url: str
    file_name: str


class SingleExportRequest(BaseModel):
    segment: SampleSegment
