from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

import librosa
import numpy as np

from backend.models.sample import CategoryScore

EPSILON = 1e-8
UNKNOWN_CATEGORY = "unknown"


@dataclass(frozen=True)
class SoundCategory:
    key: str
    label: str
    aliases: tuple[str, ...]


SOUND_CATEGORIES: tuple[SoundCategory, ...] = (
    SoundCategory(
        key="bass",
        label="Bass",
        aliases=("sub bass", "808", "reese", "mid bass", "bassline"),
    ),
    SoundCategory(
        key="lead",
        label="Lead",
        aliases=("synth lead", "mono lead", "topline", "hook lead", "solo"),
    ),
    SoundCategory(
        key="pad",
        label="Pad",
        aliases=("atmos pad", "string pad", "choir pad", "drone", "ambient pad"),
    ),
    SoundCategory(
        key="pluck",
        label="Pluck",
        aliases=("stab", "short lead", "pluck arp", "key stab"),
    ),
    SoundCategory(
        key="chords",
        label="Chords",
        aliases=("chord stab", "harmony", "comp", "keys"),
    ),
    SoundCategory(
        key="percussion",
        label="Percussion",
        aliases=("drums", "drum loop", "kick", "snare", "hat", "tom"),
    ),
    SoundCategory(
        key="fx",
        label="FX",
        aliases=("riser", "downlifter", "impact", "sweep", "noise fx", "transition"),
    ),
    SoundCategory(
        key="vocal",
        label="Vocal",
        aliases=("vox", "vocal chop", "vocal shot", "adlib"),
    ),
    SoundCategory(
        key=UNKNOWN_CATEGORY,
        label="Unknown",
        aliases=("unclear", "mixed", "other"),
    ),
)

SOUND_CATEGORY_CATALOG: List[dict[str, object]] = [
    {
        "key": category.key,
        "label": category.label,
        "aliases": list(category.aliases),
    }
    for category in SOUND_CATEGORIES
]

RECOMMENDED_AI_TOOLS: List[dict[str, object]] = [
    {
        "name": "Essentia Music Loop Instrument Role",
        "url": "https://essentia.upf.edu/models.html#music-loop-instrument-role",
        "notes": "Loop-focused classifier with bass/chords/fx/melody/percussion labels.",
    },
    {
        "name": "Essentia Nsynth Instrument",
        "url": "https://essentia.upf.edu/models.html#nsynth-instrument",
        "notes": "Instrument-family model with classes including synth_lead and bass.",
    },
    {
        "name": "YAMNet (TensorFlow Hub)",
        "url": "https://www.tensorflow.org/hub/tutorials/yamnet",
        "notes": "General audio-event model with 521 AudioSet classes.",
    },
]


def detect_sample_type(audio: np.ndarray, sample_rate: int) -> str:
    """Classify as 'oneshot', 'loop', or 'tonal'."""
    duration = len(audio) / max(sample_rate, 1)

    rms = librosa.feature.rms(y=audio, frame_length=1024, hop_length=256)[0]
    rms_mean = float(np.mean(rms)) + EPSILON
    rms_cv = float(np.std(rms)) / rms_mean

    split = max(1, len(rms) // 5)
    attack_energy = float(np.mean(rms[:split])) + EPSILON
    tail_energy = float(np.mean(rms[-split:]))
    decay_ratio = tail_energy / attack_energy

    onset_frames = librosa.onset.onset_detect(
        y=audio, sr=sample_rate, hop_length=512, backtrack=False, units="frames"
    )
    onset_count = len(onset_frames)
    onset_density = onset_count / max(duration, 0.1)

    harmonic, percussive = librosa.effects.hpss(audio)
    harmonic_energy = float(np.mean(np.abs(harmonic)))
    percussive_energy = float(np.mean(np.abs(percussive)))
    harmonic_ratio = harmonic_energy / (harmonic_energy + percussive_energy + EPSILON)

    if onset_count >= 3 and onset_density >= 1.0 and rms_cv < 0.85:
        return "loop"

    if harmonic_ratio > 0.72 and onset_count <= 2 and decay_ratio > 0.35:
        return "tonal"

    if decay_ratio < 0.35 and onset_count <= 3:
        return "oneshot"

    if onset_count >= 3:
        return "loop"

    return "oneshot"


def classify_transient_type(audio: np.ndarray, sample_rate: int) -> str:
    """Classify percussive transient: kick/snare/hihat_closed/hihat_open/clap/tom/cymbal/other."""
    duration = len(audio) / max(sample_rate, 1)

    stft = np.abs(librosa.stft(audio, n_fft=2048, hop_length=512))
    spectrum = np.mean(stft, axis=1)
    freqs = librosa.fft_frequencies(sr=sample_rate, n_fft=2048)
    total = float(np.sum(spectrum)) + EPSILON

    sub_ratio = float(np.sum(spectrum[freqs < 80]) / total)
    low_ratio = float(np.sum(spectrum[freqs < 250]) / total)
    mid_ratio = float(np.sum(spectrum[(freqs >= 250) & (freqs < 3000)]) / total)
    high_ratio = float(np.sum(spectrum[freqs >= 3000]) / total)
    very_high_ratio = float(np.sum(spectrum[freqs >= 8000]) / total)

    zcr = float(np.mean(librosa.feature.zero_crossing_rate(y=audio)))
    flatness = float(np.mean(librosa.feature.spectral_flatness(y=audio)))
    centroid = float(np.mean(librosa.feature.spectral_centroid(y=audio, sr=sample_rate)))

    if sub_ratio > 0.22 and low_ratio > 0.48 and zcr < 0.15 and centroid < 1200:
        return "kick"

    if zcr > 0.22 and flatness > 0.18 and sub_ratio < 0.12 and duration < 0.6:
        return "clap"

    if very_high_ratio > 0.28 and zcr > 0.18 and duration < 0.35:
        return "hihat_closed"

    if very_high_ratio > 0.22 and high_ratio > 0.55 and zcr > 0.14:
        return "hihat_open"

    if high_ratio > 0.5 and duration > 0.5:
        return "cymbal"

    if mid_ratio > 0.28 and zcr > 0.1 and sub_ratio < 0.22:
        return "snare"

    if low_ratio > 0.38 and mid_ratio > 0.2 and zcr < 0.15:
        return "tom"

    return "other"


_CHROMATIC = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
_MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])


def detect_key(audio: np.ndarray, sample_rate: int) -> Optional[str]:
    if audio.size < int(sample_rate * 0.5):
        return None
    try:
        chroma = librosa.feature.chroma_stft(y=audio.astype(np.float32), sr=sample_rate)
        chroma_mean = np.mean(chroma, axis=1)
        best_key: Optional[str] = None
        best_score = -np.inf
        for i in range(12):
            for profile, mode in [(_MAJOR_PROFILE, "maj"), (_MINOR_PROFILE, "min")]:
                rotated = np.roll(profile, i)
                corr = np.corrcoef(rotated, chroma_mean)
                score = float(corr[0, 1]) if corr.shape == (2, 2) else -np.inf
                if score > best_score:
                    best_score = score
                    best_key = f"{_CHROMATIC[i]} {mode}"
        return best_key
    except Exception:
        return None


def classify_sound_segment(
    audio: np.ndarray,
    sample_rate: int,
    start: float,
    end: float,
) -> tuple[str, float, List[CategoryScore]]:
    segment = _slice_audio(audio, sample_rate, start, end)
    min_frames = max(512, int(sample_rate * 0.2))
    if segment.size < min_frames:
        return UNKNOWN_CATEGORY, 0.0, [CategoryScore(category=UNKNOWN_CATEGORY, score=1.0)]

    peak = float(np.max(np.abs(segment)))
    if peak < 1e-5:
        return UNKNOWN_CATEGORY, 0.0, [CategoryScore(category=UNKNOWN_CATEGORY, score=1.0)]

    normalized = (segment / max(peak, EPSILON)).astype(np.float32)
    features = _extract_features(normalized, sample_rate)
    scores = _score_categories(features)
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)

    if not ranked:
        return UNKNOWN_CATEGORY, 0.0, [CategoryScore(category=UNKNOWN_CATEGORY, score=1.0)]

    best_key, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    if best_key == "vocal":
        vocal_gate = float(features.get("vocal_gate", 0.0))
        if vocal_gate < 0.55 or (best_score - second_score) < 0.08:
            if len(ranked) > 1:
                best_key, best_score = ranked[1]
            else:
                best_key, best_score = UNKNOWN_CATEGORY, 0.0

    if best_score < 0.36:
        best_key = UNKNOWN_CATEGORY

    confidence = _clamp(best_score, 0.0, 1.0)
    candidates = [CategoryScore(category=key, score=round(_clamp(score, 0.0, 1.0), 4)) for key, score in ranked[:3]]

    if best_key == UNKNOWN_CATEGORY and not any(item.category == UNKNOWN_CATEGORY for item in candidates):
        candidates.insert(0, CategoryScore(category=UNKNOWN_CATEGORY, score=round(_clamp(1.0 - best_score, 0.0, 1.0), 4)))
        candidates = candidates[:3]

    return best_key, round(confidence, 4), candidates


def _extract_features(segment: np.ndarray, sample_rate: int) -> Dict[str, float]:
    rms = librosa.feature.rms(y=segment, frame_length=1024, hop_length=256)[0]
    rms_mean = float(np.mean(rms))
    rms_std = float(np.std(rms))
    rms_cv = rms_std / (rms_mean + EPSILON)

    first_window = max(1, int(sample_rate * 0.08))
    first_energy = float(np.mean(np.abs(segment[:first_window])))
    total_energy = float(np.mean(np.abs(segment)))
    attack_ratio = first_energy / (total_energy + EPSILON)
    attack = _clamp((attack_ratio - 0.85) / 1.1, 0.0, 1.0)

    centroid = float(np.mean(librosa.feature.spectral_centroid(y=segment, sr=sample_rate)))
    rolloff = float(np.mean(librosa.feature.spectral_rolloff(y=segment, sr=sample_rate, roll_percent=0.85)))
    flatness = float(np.mean(librosa.feature.spectral_flatness(y=segment)))
    zcr = float(np.mean(librosa.feature.zero_crossing_rate(y=segment)))

    harmonic, percussive = librosa.effects.hpss(segment)
    harmonic_energy = float(np.mean(np.abs(harmonic)))
    percussive_energy = float(np.mean(np.abs(percussive)))
    harmonic_ratio = harmonic_energy / (harmonic_energy + percussive_energy + EPSILON)
    percussive_ratio = percussive_energy / (harmonic_energy + percussive_energy + EPSILON)

    stft = np.abs(librosa.stft(segment, n_fft=2048, hop_length=512))
    spectrum = np.mean(stft, axis=1)
    freqs = librosa.fft_frequencies(sr=sample_rate, n_fft=2048)
    total_spectrum = float(np.sum(spectrum)) + EPSILON
    dominant_freq = float(freqs[int(np.argmax(spectrum))]) if spectrum.size else 0.0

    sub_ratio = float(np.sum(spectrum[freqs < 80]) / total_spectrum)
    low_ratio = float(np.sum(spectrum[freqs < 220]) / total_spectrum)
    mid_ratio = float(np.sum(spectrum[(freqs >= 220) & (freqs < 2000)]) / total_spectrum)
    high_ratio = float(np.sum(spectrum[freqs >= 2000]) / total_spectrum)
    speech_ratio = float(np.sum(spectrum[(freqs >= 250) & (freqs <= 3500)]) / total_spectrum)
    air_ratio = float(np.sum(spectrum[freqs >= 6000]) / total_spectrum)

    nyquist = max(1.0, sample_rate / 2)
    centroid_norm = _clamp(centroid / nyquist, 0.0, 1.0)
    rolloff_norm = _clamp(rolloff / nyquist, 0.0, 1.0)
    sustain = _clamp(1.0 - min(1.0, rms_cv), 0.0, 1.0)
    bright = _clamp(0.65 * centroid_norm + 0.35 * high_ratio, 0.0, 1.0)
    noisiness = _clamp(0.7 * flatness + 0.3 * zcr, 0.0, 1.0)
    transient = _clamp(0.55 * attack + 0.45 * (1.0 - sustain), 0.0, 1.0)
    vocal_gate_raw = (
        0.45 * speech_ratio
        + 0.2 * mid_ratio
        + 0.15 * (1.0 - low_ratio)
        + 0.1 * (1.0 - percussive_ratio)
        + 0.1 * (1.0 - air_ratio)
    )
    voice_pitch_gate = _voice_pitch_gate(dominant_freq)
    vocal_gate = _clamp(((0.55 * vocal_gate_raw + 0.45 * voice_pitch_gate) - 0.52) / 0.32, 0.0, 1.0)

    return {
        "sustain": sustain,
        "attack": attack,
        "transient": transient,
        "centroid_norm": centroid_norm,
        "rolloff_norm": rolloff_norm,
        "flatness": flatness,
        "zcr": zcr,
        "harmonic_ratio": harmonic_ratio,
        "percussive_ratio": percussive_ratio,
        "sub_ratio": sub_ratio,
        "low_ratio": low_ratio,
        "mid_ratio": mid_ratio,
        "high_ratio": high_ratio,
        "speech_ratio": speech_ratio,
        "air_ratio": air_ratio,
        "dominant_freq": dominant_freq,
        "bright": bright,
        "noisiness": noisiness,
        "voice_pitch_gate": voice_pitch_gate,
        "vocal_gate": vocal_gate,
    }


def _score_categories(features: Dict[str, float]) -> Dict[str, float]:
    low_end = _clamp(0.65 * features["low_ratio"] + 0.35 * features["sub_ratio"], 0.0, 1.0)

    scores = {
        "bass": (
            0.45 * low_end
            + 0.2 * (1.0 - features["bright"])
            + 0.2 * features["harmonic_ratio"]
            + 0.15 * features["sustain"]
        ),
        "pad": (
            0.38 * features["sustain"]
            + 0.22 * features["harmonic_ratio"]
            + 0.15 * features["mid_ratio"]
            + 0.15 * (1.0 - features["transient"])
            + 0.1 * (1.0 - features["percussive_ratio"])
        ),
        "lead": (
            0.34 * features["bright"]
            + 0.26 * features["harmonic_ratio"]
            + 0.2 * features["mid_ratio"]
            + 0.2 * features["transient"]
        ),
        "pluck": (
            0.4 * features["transient"]
            + 0.25 * features["harmonic_ratio"]
            + 0.2 * features["bright"]
            + 0.15 * (1.0 - features["sustain"])
        ),
        "chords": (
            0.36 * features["sustain"]
            + 0.28 * features["harmonic_ratio"]
            + 0.22 * features["mid_ratio"]
            + 0.14 * (1.0 - features["transient"])
        ),
        "percussion": (
            0.44 * features["percussive_ratio"]
            + 0.26 * features["transient"]
            + 0.2 * features["zcr"]
            + 0.1 * features["high_ratio"]
        ),
        "fx": (
            0.36 * features["noisiness"]
            + 0.26 * features["high_ratio"]
            + 0.2 * (1.0 - features["harmonic_ratio"])
            + 0.18 * features["transient"]
        ),
        "vocal": (
            (
                0.28 * features["harmonic_ratio"]
                + 0.24 * features["speech_ratio"]
                + 0.16 * features["sustain"]
                + 0.12 * (1.0 - features["flatness"])
                + 0.12 * features["mid_ratio"]
                + 0.08 * (1.0 - features["percussive_ratio"])
            )
            * features["vocal_gate"]
        ),
    }

    return {key: _clamp(float(value), 0.0, 1.0) for key, value in scores.items()}


def _slice_audio(audio: np.ndarray, sample_rate: int, start: float, end: float) -> np.ndarray:
    start_idx = max(0, min(len(audio), int(start * sample_rate)))
    end_idx = max(start_idx + 1, min(len(audio), int(end * sample_rate)))
    return audio[start_idx:end_idx]


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return float(max(minimum, min(maximum, value)))


def _voice_pitch_gate(dominant_freq: float) -> float:
    if dominant_freq <= 70.0 or dominant_freq >= 700.0:
        return 0.0
    if dominant_freq <= 180.0:
        return _clamp((dominant_freq - 70.0) / 110.0, 0.0, 1.0)
    if dominant_freq <= 380.0:
        return 1.0
    return _clamp((700.0 - dominant_freq) / 320.0, 0.0, 1.0)
