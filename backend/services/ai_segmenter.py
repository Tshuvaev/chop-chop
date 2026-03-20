from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

import librosa
import numpy as np

from backend.models.sample import SampleSegment
from backend.services.sound_classifier import classify_sound_segment, classify_transient_type, detect_sample_type, detect_key
from backend.utils.config import MAX_SEGMENTS

WAVEFORM_POINTS = 96
CLIP_THRESHOLD = 0.995
CLIP_RATIO_THRESHOLD = 0.001
EDIT_WINDOW_PADDING_SECONDS = 2.0


class SegmentationError(RuntimeError):
    pass


def detect_bpm(audio: np.ndarray, sample_rate: int) -> float:
    tempo, _ = librosa.beat.beat_track(y=audio, sr=sample_rate)
    return round(float(np.atleast_1d(tempo)[0]), 1)


def detect_segments(
    wav_path: Path,
    min_length: float,
    max_length: float,
    max_segments: int = MAX_SEGMENTS,
) -> tuple[List[SampleSegment], float, float]:
    try:
        audio, sample_rate = librosa.load(str(wav_path), sr=None, mono=True)
    except Exception as exc:  # noqa: BLE001
        raise SegmentationError("Failed to load WAV file for AI segmentation.") from exc

    if audio.size == 0:
        raise SegmentationError("Audio file is empty. Cannot detect segments.")

    duration = float(librosa.get_duration(y=audio, sr=sample_rate))
    if duration < min_length:
        raise SegmentationError("Audio is too short to extract samples.")

    bpm = detect_bpm(audio, sample_rate)
    onset_times = _detect_onsets(audio, sample_rate)
    segment_pairs = _build_segments(onset_times, duration, min_length, max_length)

    if not segment_pairs:
        segment_pairs = _fallback_segments(duration, min_length, max_length)

    segment_pairs = segment_pairs[:max_segments]

    interest_scores = _compute_interest_scores(audio, sample_rate, segment_pairs)
    mfcc_sigs = _compute_mfcc_signatures(audio, sample_rate, segment_pairs)
    duplicate_flags = _mark_duplicates(interest_scores, mfcc_sigs)

    segments: List[SampleSegment] = []
    for index, (start, end) in enumerate(segment_pairs, start=1):
        window_start = max(0.0, start - EDIT_WINDOW_PADDING_SECONDS)
        window_end = min(duration, end + EDIT_WINDOW_PADDING_SECONDS)
        waveform = _extract_waveform(audio, sample_rate, window_start, window_end)
        clipping_ratio, is_clipping = _segment_clipping(audio, sample_rate, start, end)
        sound_type, sound_confidence, sound_candidates = classify_sound_segment(audio, sample_rate, start, end)
        segment_audio = _slice_audio(audio, sample_rate, start, end)
        segment_bpm = detect_bpm(segment_audio, sample_rate) if segment_audio.size >= sample_rate else None
        seg_interest = interest_scores[index - 1] if (index - 1) < len(interest_scores) else None
        seg_is_dup = duplicate_flags[index - 1] if (index - 1) < len(duplicate_flags) else False
        sample_type = detect_sample_type(segment_audio, sample_rate) if segment_audio.size >= int(sample_rate * 0.3) else None
        transient_type = classify_transient_type(segment_audio, sample_rate) if segment_audio.size >= int(sample_rate * 0.05) else None
        segment_key = detect_key(segment_audio, sample_rate) if segment_audio.size >= int(sample_rate * 0.5) else None

        segments.append(
            SampleSegment(
                id=index,
                name=f"sample_{index:03d}",
                start=round(start, 3),
                end=round(end, 3),
                waveform=waveform,
                clipping_ratio=round(clipping_ratio, 4),
                is_clipping=is_clipping,
                window_start=round(window_start, 3),
                window_end=round(window_end, 3),
                sound_type=sound_type,
                sound_type_confidence=round(sound_confidence, 4),
                sound_type_candidates=sound_candidates,
                bpm=segment_bpm,
                sample_type=sample_type,
                transient_type=transient_type,
                key=segment_key,
                interest_score=seg_interest,
                is_duplicate=seg_is_dup,
            )
        )

    return segments, duration, bpm


def _detect_onsets(audio: np.ndarray, sample_rate: int) -> List[float]:
    hop_length = 512
    onset_times = librosa.onset.onset_detect(
        y=audio,
        sr=sample_rate,
        hop_length=hop_length,
        units="time",
        backtrack=False,
        pre_max=20,
        post_max=20,
        pre_avg=100,
        post_avg=100,
        delta=0.2,
        wait=0,
    )

    cleaned = sorted(float(time_point) for time_point in onset_times if time_point >= 0)
    deduped: List[float] = []
    for onset in cleaned:
        if not deduped or (onset - deduped[-1]) > 0.15:
            deduped.append(onset)

    if not deduped or deduped[0] > 0.25:
        deduped.insert(0, 0.0)
    else:
        deduped[0] = 0.0

    return deduped


def _build_segments(
    onsets: List[float],
    duration: float,
    min_length: float,
    max_length: float,
) -> List[Tuple[float, float]]:
    segments: List[Tuple[float, float]] = []

    for i, start in enumerate(onsets):
        if start >= duration:
            continue

        is_last = i == len(onsets) - 1
        if is_last:
            end = min(duration, start + max_length)
        else:
            next_onset = onsets[i + 1]
            end = min(next_onset, start + max_length)

        length = end - start
        if length < min_length:
            continue

        segments.append((start, end))

    return _remove_overlaps(segments)


def _remove_overlaps(segments: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    if not segments:
        return segments

    cleaned: List[Tuple[float, float]] = []
    last_end = -1.0

    for start, end in segments:
        if start < last_end:
            start = last_end
        if end <= start:
            continue
        cleaned.append((start, end))
        last_end = end

    return cleaned


def _fallback_segments(duration: float, min_length: float, max_length: float) -> List[Tuple[float, float]]:
    segments: List[Tuple[float, float]] = []
    cursor = 0.0

    while cursor + min_length <= duration:
        end = min(duration, cursor + max_length)
        segments.append((cursor, end))
        cursor = end

    return segments


def _extract_waveform(
    audio: np.ndarray,
    sample_rate: int,
    start: float,
    end: float,
) -> List[float]:
    window = _slice_audio(audio, sample_rate, start, end)
    if window.size == 0:
        return [0.0] * WAVEFORM_POINTS
    return _downsample_waveform(window, WAVEFORM_POINTS)


def _segment_clipping(
    audio: np.ndarray,
    sample_rate: int,
    start: float,
    end: float,
) -> tuple[float, bool]:
    segment = _slice_audio(audio, sample_rate, start, end)
    if segment.size == 0:
        return 0.0, False

    clipping_ratio = float(np.mean(np.abs(segment) >= CLIP_THRESHOLD))
    return clipping_ratio, clipping_ratio >= CLIP_RATIO_THRESHOLD


def _slice_audio(audio: np.ndarray, sample_rate: int, start: float, end: float) -> np.ndarray:
    start_idx = max(0, min(len(audio), int(start * sample_rate)))
    end_idx = max(start_idx + 1, min(len(audio), int(end * sample_rate)))
    return audio[start_idx:end_idx]


def _downsample_waveform(window: np.ndarray, points: int) -> List[float]:
    if points <= 0:
        return []

    boundaries = np.linspace(0, window.size, num=points + 1, dtype=int)
    result: List[float] = []

    for i in range(points):
        left = boundaries[i]
        right = boundaries[i + 1]
        chunk = window[left:right]
        if chunk.size == 0:
            result.append(0.0)
            continue

        amplitude = float(np.max(np.abs(chunk)))
        result.append(round(min(1.0, max(0.0, amplitude)), 4))

    return result


def _compute_interest_scores(
    audio: np.ndarray,
    sample_rate: int,
    segment_pairs: List[Tuple[float, float]],
) -> List[float]:
    hop_length = 512
    oenv = librosa.onset.onset_strength(y=audio, sr=sample_rate, hop_length=hop_length)
    oenv_max = float(np.max(oenv)) + 1e-8

    rms_global = librosa.feature.rms(y=audio, frame_length=1024, hop_length=256)[0]
    global_rms = float(np.mean(rms_global)) + 1e-8

    scores: List[float] = []
    for start, end in segment_pairs:
        seg = _slice_audio(audio, sample_rate, start, end)
        if seg.size == 0:
            scores.append(0.0)
            continue

        start_frame = int(start * sample_rate / hop_length)
        end_frame = max(start_frame + 1, int(end * sample_rate / hop_length))
        seg_oenv = oenv[start_frame:min(end_frame, len(oenv))]
        novelty = float(np.max(seg_oenv)) / oenv_max if seg_oenv.size > 0 else 0.0

        seg_rms = float(np.mean(librosa.feature.rms(y=seg, frame_length=512, hop_length=128)[0]))
        energy = min(1.0, seg_rms / (global_rms * 1.5))

        try:
            contrast = librosa.feature.spectral_contrast(y=seg, sr=sample_rate, n_bands=4)
            contrast_score = float(np.clip(np.mean(contrast) / 35.0, 0.0, 1.0))
        except Exception:
            contrast_score = 0.4

        score = 0.45 * novelty + 0.30 * energy + 0.25 * contrast_score
        scores.append(round(float(np.clip(score, 0.0, 1.0)), 4))

    return scores


def _compute_mfcc_signatures(
    audio: np.ndarray,
    sample_rate: int,
    segment_pairs: List[Tuple[float, float]],
) -> List[np.ndarray]:
    sigs: List[np.ndarray] = []
    for start, end in segment_pairs:
        seg = _slice_audio(audio, sample_rate, start, end)
        if seg.size < int(sample_rate * 0.1):
            sigs.append(np.zeros(13))
            continue
        try:
            mfcc = librosa.feature.mfcc(y=seg, sr=sample_rate, n_mfcc=13)
            sigs.append(np.mean(mfcc, axis=1))
        except Exception:
            sigs.append(np.zeros(13))
    return sigs


def _mark_duplicates(
    interest_scores: List[float],
    signatures: List[np.ndarray],
    similarity_threshold: float = 0.82,
) -> List[bool]:
    n = len(interest_scores)
    is_dup = [False] * n
    order = sorted(range(n), key=lambda i: interest_scores[i], reverse=True)
    kept: List[np.ndarray] = []
    for idx in order:
        sig = signatures[idx]
        sig_norm = float(np.linalg.norm(sig))
        duplicate = False
        for k in kept:
            k_norm = float(np.linalg.norm(k))
            denom = sig_norm * k_norm
            if denom < 1e-8:
                continue
            if float(np.dot(sig, k) / denom) > similarity_threshold:
                duplicate = True
                break
        if duplicate:
            is_dup[idx] = True
        else:
            kept.append(sig)
    return is_dup
