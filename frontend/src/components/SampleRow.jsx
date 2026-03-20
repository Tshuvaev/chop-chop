import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { getCopy } from "../i18n";

const MIN_SEGMENT_SECONDS = 0.1;
const CLIP_THRESHOLD = 0.995;
const CLIP_RATIO_THRESHOLD = 0.001;
const WAVE_LEVELS = 12;
const KEYBOARD_NUDGE_SECONDS = 0.02;
const KEYBOARD_NUDGE_FAST_SECONDS = 0.1;

const SOUND_TYPE_LABELS = {
  bass: "Bass",
  lead: "Lead",
  pad: "Pad",
  pluck: "Pluck",
  chords: "Chords",
  percussion: "Percussion",
  fx: "FX",
  vocal: "Vocal",
  unknown: "Unknown",
};

const SAMPLE_TYPE_LABELS = {
  oneshot: "One-shot",
  loop: "Loop",
  tonal: "Tonal",
};

const TRANSIENT_TYPE_LABELS = {
  kick: "Kick",
  snare: "Snare",
  hihat_closed: "Hi-Hat Closed",
  hihat_open: "Hi-Hat Open",
  clap: "Clap",
  tom: "Tom",
  cymbal: "Cymbal",
  other: null,
};

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function typeChipClass(soundType, variant = "primary") {
  const normalizedType = String(soundType || "unknown").toLowerCase();
  if (normalizedType === "unknown") {
    return "pixel-chip pixel-chip-muted";
  }

  const baseClass = `pixel-chip pixel-chip-type pixel-chip-type-${normalizedType}`;
  if (variant === "secondary") {
    return `${baseClass} pixel-chip-type-soft`;
  }

  return baseClass;
}

function Waveform({ waveform = [], isClipping = false }) {
  const points = waveform.length ? waveform : new Array(72).fill(0);
  const fillColor = isClipping ? "#d4a961" : "#efefef";
  const bottomPattern = `repeating-linear-gradient(to top, ${fillColor} 0, ${fillColor} 3px, transparent 3px, transparent 4px)`;
  const topPattern = `repeating-linear-gradient(to bottom, ${fillColor} 0, ${fillColor} 3px, transparent 3px, transparent 4px)`;

  return (
    <div className="pointer-events-none absolute inset-0">
      <div
        className="absolute inset-0"
        style={{
          backgroundColor: "#070707",
          backgroundImage:
            "linear-gradient(to right, rgba(255,255,255,0.08) 1px, transparent 1px), linear-gradient(to bottom, rgba(255,255,255,0.08) 1px, transparent 1px)",
          backgroundSize: "6px 6px",
        }}
      />

      <div className="absolute inset-0 flex items-stretch gap-[1px] px-[4px] py-[4px]">
        {points.map((point, index) => {
          const normalized = clamp(Number(point) || 0, 0, 1);
          const quantized = Math.max(2, Math.round(normalized * WAVE_LEVELS));
          const halfHeight = (quantized / WAVE_LEVELS) * 50;
          const opacity = 0.4 + normalized * 0.6;

          return (
            <span key={`wf-${index}`} className="relative h-full flex-1 min-w-[2px]">
              <span
                className="absolute left-0 right-0 bottom-1/2"
                style={{ height: `${halfHeight}%`, opacity, backgroundColor: fillColor, backgroundImage: bottomPattern }}
              />
              <span
                className="absolute left-0 right-0 top-1/2"
                style={{ height: `${halfHeight}%`, opacity, backgroundColor: fillColor, backgroundImage: topPattern }}
              />
            </span>
          );
        })}
      </div>

      <div className="absolute left-0 right-0 top-1/2 h-px bg-white/60" />
    </div>
  );
}

function SampleRow({ segment, language = "en", onChange, onPreview, onDownload, onDelete, isPlaying, playheadTime, isDownloading }) {
  const sampleName = segment.name || `sample_${String(segment.id).padStart(3, "0")}`;
  const waveformRef = useRef(null);
  const rangeDragRef = useRef(null);
  const segmentTimesRef = useRef({ start: Number(segment.start), end: Number(segment.end) });
  const [dragHandle, setDragHandle] = useState(null);
  const [isEditingName, setIsEditingName] = useState(false);
  const [editedName, setEditedName] = useState(sampleName);
  const nameInputRef = useRef(null);
  const copy = useMemo(() => getCopy(language), [language]);
  const commitName = () => {
    const trimmed = editedName.trim();
    if (trimmed && trimmed !== sampleName) {
      onChange(segment.id, "name", trimmed);
    } else {
      setEditedName(sampleName);
    }
    setIsEditingName(false);
  };

  const soundType = String(segment.sound_type || "unknown").toLowerCase();
  const soundTypeLabel = SOUND_TYPE_LABELS[soundType] || segment.sound_type || "Unknown";
  const soundTypeConfidence = Number(segment.sound_type_confidence || 0);
  const soundTypeCandidates = useMemo(() => {
    if (!Array.isArray(segment.sound_type_candidates)) {
      return [];
    }

    return segment.sound_type_candidates
      .map((item) => ({
        category: String(item?.category || "").toLowerCase(),
        score: Number(item?.score || 0),
      }))
      .filter((item) => item.category && Number.isFinite(item.score))
      .slice(0, 3);
  }, [segment.sound_type_candidates]);

  const windowStart = useMemo(() => {
    if (Number.isFinite(Number(segment.window_start))) {
      return Number(segment.window_start);
    }
    return Math.max(0, Number(segment.start) - 2);
  }, [segment.start, segment.window_start]);

  const windowEnd = useMemo(() => {
    const fallback = Number(segment.end) + 2;
    const fromSegment = Number(segment.window_end);
    const value = Number.isFinite(fromSegment) ? fromSegment : fallback;
    return Math.max(windowStart + MIN_SEGMENT_SECONDS, value);
  }, [segment.end, segment.window_end, windowStart]);

  const windowDuration = Math.max(0.001, windowEnd - windowStart);
  const startPct = clamp((Number(segment.start) - windowStart) / windowDuration, 0, 1) * 100;
  const endPct = clamp((Number(segment.end) - windowStart) / windowDuration, 0, 1) * 100;
  const hasPlayhead = isPlaying && Number.isFinite(Number(playheadTime));
  const playheadPct = hasPlayhead
    ? clamp((Number(playheadTime) - windowStart) / windowDuration, 0, 1) * 100
    : 0;

  const clippingInfo = useMemo(() => {
    const fallbackRatio = Number(segment.clipping_ratio || 0);
    const fallbackIsClipping = Boolean(segment.is_clipping);
    const waveform = Array.isArray(segment.waveform)
      ? segment.waveform.map((point) => Number(point)).filter((point) => Number.isFinite(point))
      : [];

    if (!waveform.length) {
      return { ratio: fallbackRatio, isClipping: fallbackIsClipping };
    }

    const startNorm = clamp((Number(segment.start) - windowStart) / windowDuration, 0, 1);
    const endNorm = clamp((Number(segment.end) - windowStart) / windowDuration, 0, 1);
    const leftIndex = clamp(Math.floor(startNorm * waveform.length), 0, Math.max(0, waveform.length - 1));
    const rightIndex = clamp(Math.ceil(endNorm * waveform.length), leftIndex + 1, waveform.length);
    const selectedPoints = waveform.slice(leftIndex, rightIndex);

    if (!selectedPoints.length) {
      return { ratio: fallbackRatio, isClipping: fallbackIsClipping };
    }

    const clippedPoints = selectedPoints.filter((point) => point >= CLIP_THRESHOLD).length;
    const ratio = clippedPoints / selectedPoints.length;
    return {
      ratio,
      isClipping: ratio >= CLIP_RATIO_THRESHOLD,
    };
  }, [
    segment.clipping_ratio,
    segment.end,
    segment.is_clipping,
    segment.start,
    segment.waveform,
    windowDuration,
    windowStart,
  ]);

  useEffect(() => {
    segmentTimesRef.current = {
      start: Number(segment.start),
      end: Number(segment.end),
    };
  }, [segment.end, segment.start]);

  const updateByClientX = useCallback(
    (clientX, handle) => {
      const rect = waveformRef.current?.getBoundingClientRect();
      if (!rect || rect.width <= 0) {
        return;
      }

      const ratio = clamp((clientX - rect.left) / rect.width, 0, 1);
      const targetTime = windowStart + ratio * windowDuration;

      if (handle === "range") {
        const dragState = rangeDragRef.current;
        if (!dragState) {
          return;
        }

        if (Math.abs(clientX - dragState.pointerStartX) >= 2) {
          dragState.moved = true;
        }

        const length = Math.max(MIN_SEGMENT_SECONDS, dragState.initialEnd - dragState.initialStart);
        const deltaTime = targetTime - dragState.pointerStartTime;
        const nextStart = clamp(dragState.initialStart + deltaTime, windowStart, windowEnd - length);
        const nextEnd = nextStart + length;

        onChange(segment.id, "start", Number(nextStart.toFixed(3)));
        onChange(segment.id, "end", Number(nextEnd.toFixed(3)));
        return;
      }

      if (handle === "start") {
        const maxStart = segmentTimesRef.current.end - MIN_SEGMENT_SECONDS;
        const nextStart = clamp(targetTime, windowStart, maxStart);
        onChange(segment.id, "start", Number(nextStart.toFixed(3)));
        return;
      }

      const minEnd = segmentTimesRef.current.start + MIN_SEGMENT_SECONDS;
      const nextEnd = clamp(targetTime, minEnd, windowEnd);
      onChange(segment.id, "end", Number(nextEnd.toFixed(3)));
    },
    [onChange, segment.id, windowDuration, windowEnd, windowStart]
  );

  const onHandlePointerDown = (handle, event) => {
    event.preventDefault();
    event.stopPropagation();
    setDragHandle(handle);
    updateByClientX(event.clientX, handle);
  };

  const nudgeRangeBy = useCallback(
    (deltaSeconds) => {
      const currentStart = Number(segment.start);
      const currentEnd = Number(segment.end);
      const length = Math.max(MIN_SEGMENT_SECONDS, currentEnd - currentStart);
      const nextStart = clamp(currentStart + deltaSeconds, windowStart, windowEnd - length);
      const nextEnd = nextStart + length;

      onChange(segment.id, "start", Number(nextStart.toFixed(3)));
      onChange(segment.id, "end", Number(nextEnd.toFixed(3)));
    },
    [onChange, segment.end, segment.id, segment.start, windowEnd, windowStart]
  );

  const onRangePointerDown = (event) => {
    event.preventDefault();
    event.stopPropagation();

    const rect = waveformRef.current?.getBoundingClientRect();
    if (!rect || rect.width <= 0) {
      return;
    }

    const ratio = clamp((event.clientX - rect.left) / rect.width, 0, 1);
    const pointerStartTime = windowStart + ratio * windowDuration;

    rangeDragRef.current = {
      pointerStartTime,
      pointerStartX: event.clientX,
      moved: false,
      initialStart: Number(segment.start),
      initialEnd: Number(segment.end),
    };

    setDragHandle("range");
  };

  const onRangeKeyDown = (event) => {
    if (event.key === " " || event.code === "Space" || event.key === "Spacebar") {
      event.preventDefault();
      event.stopPropagation();
      onPreview(segment);
      return;
    }

    if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") {
      return;
    }

    event.preventDefault();
    event.stopPropagation();
    const step = event.shiftKey ? KEYBOARD_NUDGE_FAST_SECONDS : KEYBOARD_NUDGE_SECONDS;
    const direction = event.key === "ArrowRight" ? 1 : -1;
    nudgeRangeBy(direction * step);
  };

  const onWaveformKeyDown = (event) => {
    if (event.key === " " || event.code === "Space" || event.key === "Spacebar") {
      event.preventDefault();
      event.stopPropagation();
      onPreview(segment);
    }
  };

  useEffect(() => {
    if (!dragHandle) {
      return undefined;
    }

    const onPointerMove = (event) => {
      updateByClientX(event.clientX, dragHandle);
    };

    const onPointerUp = () => {
      const dragState = rangeDragRef.current;
      const shouldPreviewRange = dragHandle === "range" && dragState && !dragState.moved;

      setDragHandle(null);
      rangeDragRef.current = null;

      if (shouldPreviewRange) {
        onPreview(segment);
      }
    };

    window.addEventListener("pointermove", onPointerMove);
    window.addEventListener("pointerup", onPointerUp, { once: true });

    return () => {
      window.removeEventListener("pointermove", onPointerMove);
      window.removeEventListener("pointerup", onPointerUp);
    };
  }, [dragHandle, onPreview, segment, updateByClientX]);

  return (
    <div className="pixel-panel w-full grid gap-3 p-3">
      <div className="flex flex-col gap-2 md:flex-row md:items-start md:justify-between">
        <div className="min-w-0 flex-1">
          <div className="flex min-h-[22px] items-center justify-between gap-2">
            <div className="min-w-0 flex min-h-[22px] flex-1 items-center gap-2">
              {isEditingName ? (
                <input
                  ref={nameInputRef}
                  autoFocus
                  value={editedName}
                  onChange={(e) => setEditedName(e.target.value)}
                  onBlur={commitName}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") commitName();
                    if (e.key === "Escape") { setEditedName(sampleName); setIsEditingName(false); }
                  }}
                  className="pixel-title text-[9px] leading-none text-[var(--pixel-text)] md:text-[10px] bg-transparent border-b border-[var(--pixel-accent)] outline-none w-full max-w-[200px]"
                />
              ) : (
                <p
                  className="pixel-title truncate text-[9px] leading-none text-[var(--pixel-text)] md:text-[10px] cursor-pointer hover:text-[var(--pixel-accent)]"
                  title={copy.renameSample}
                  onClick={() => { setEditedName(sampleName); setIsEditingName(true); }}
                >
                  {sampleName}
                </p>
              )}
            </div>
            {isPlaying && <span className="pixel-chip pixel-chip-active pixel-chip-subtle shrink-0 md:hidden">{copy.previewing}</span>}
          </div>
          <p className="text-[20px] leading-none text-[var(--pixel-muted)] md:text-[20px]">
            {copy.sampleInstruction}
          </p>
          <div className="mt-1 flex flex-wrap items-center gap-1.5">
            <span className={typeChipClass(soundType)}>
              {copy.type}: {soundTypeLabel}
              {soundTypeConfidence > 0 ? ` ${(soundTypeConfidence * 100).toFixed(0)}%` : ""}
            </span>
            {soundTypeCandidates
              .filter((candidate) => candidate.category !== soundType)
              .slice(0, 2)
              .map((candidate) => (
                <span key={`${sampleName}-${candidate.category}`} className={typeChipClass(candidate.category, "secondary")}>
                  {SOUND_TYPE_LABELS[candidate.category] || candidate.category}
                </span>
              ))}
            {segment.sample_type && SAMPLE_TYPE_LABELS[segment.sample_type] && (
              <span className="pixel-chip pixel-chip-muted">
                {SAMPLE_TYPE_LABELS[segment.sample_type]}
              </span>
            )}
            {segment.transient_type && TRANSIENT_TYPE_LABELS[segment.transient_type] && (
              <span className="pixel-chip pixel-chip-muted">
                {TRANSIENT_TYPE_LABELS[segment.transient_type]}
              </span>
            )}
          </div>
        </div>

        <div className="hidden flex-wrap items-center gap-2 md:flex">
          {isPlaying && <span className="pixel-chip pixel-chip-active pixel-chip-subtle">{copy.previewing}</span>}
          <button
            type="button"
            onClick={() => onDownload(segment)}
            disabled={isDownloading}
            className="pixel-btn"
            style={{ height: "36px", fontSize: "20px" }}
          >
            {isDownloading ? copy.downloading : copy.download}
          </button>
          <button
            type="button"
            onClick={() => onDelete(segment.id)}
            className="pixel-btn pixel-btn-danger"
            aria-label={copy.deleteAria}
            style={{ height: "36px", fontSize: "20px" }}
          >
            {copy.deleteSample}
          </button>
        </div>
      </div>

      <div
        ref={waveformRef}
        onClick={() => onPreview(segment)}
        onKeyDown={onWaveformKeyDown}
        onMouseDown={(event) => event.currentTarget.focus()}
        tabIndex={0}
        className="group relative h-24 cursor-pointer overflow-hidden border-2 border-[var(--pixel-frame)] bg-black select-none touch-none"
        aria-label={copy.waveformAria(sampleName)}
      >
        <Waveform waveform={segment.waveform} isClipping={clippingInfo.isClipping} />

        <div
          className="pixel-selection-range pointer-events-none absolute inset-y-0 border-x transition-[background-color,border-color,box-shadow,opacity] duration-150"
          style={{ left: `${startPct}%`, width: `${Math.max(0, endPct - startPct)}%` }}
        />

        <button
          type="button"
          onClick={(event) => event.stopPropagation()}
          onPointerDown={onRangePointerDown}
          onKeyDown={onRangeKeyDown}
          className="absolute inset-y-0 z-10 min-w-[12px] -translate-x-0 cursor-grab bg-transparent focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-white/70 active:cursor-grabbing"
          style={{ left: `${startPct}%`, width: `${Math.max(0, endPct - startPct)}%` }}
          aria-label={copy.rangeAria}
          title={copy.rangeTitle}
        />

        {hasPlayhead && (
          <div
            className="pointer-events-none absolute inset-y-0 z-20 w-[2px] -translate-x-1/2 bg-black shadow-[0_0_0_1px_rgba(255,255,255,0.5)] will-change-[left]"
            style={{ left: `${playheadPct}%` }}
          />
        )}

        <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 border-t border-black/35 bg-[#d2d2d2]/95 px-2 py-0.5 opacity-0 transition group-hover:opacity-100">
          <p className="pixel-title text-[8px] text-black md:text-[9px]">{copy.clickWaveSlice}</p>
        </div>

        <button
          type="button"
          onClick={(event) => event.stopPropagation()}
          onPointerDown={(event) => onHandlePointerDown("start", event)}
          className="absolute inset-y-0 z-20 w-4 -translate-x-1/2 cursor-ew-resize touch-none bg-transparent"
          style={{ left: `${startPct}%` }}
          aria-label={copy.moveStartAria}
        >
          <span className="absolute left-1/2 top-0 h-full w-[2px] -translate-x-1/2 bg-white" />
          <span className="absolute left-1/2 top-0 h-2 w-2 -translate-x-1/2 bg-white" />
          <span className="absolute left-1/2 bottom-0 h-2 w-2 -translate-x-1/2 bg-white" />
        </button>

        <button
          type="button"
          onClick={(event) => event.stopPropagation()}
          onPointerDown={(event) => onHandlePointerDown("end", event)}
          className="absolute inset-y-0 z-20 w-4 -translate-x-1/2 cursor-ew-resize touch-none bg-transparent"
          style={{ left: `${endPct}%` }}
          aria-label={copy.moveEndAria}
        >
          <span className="absolute left-1/2 top-0 h-full w-[2px] -translate-x-1/2 bg-white" />
          <span className="absolute left-1/2 top-0 h-2 w-2 -translate-x-1/2 bg-white" />
          <span className="absolute left-1/2 bottom-0 h-2 w-2 -translate-x-1/2 bg-white" />
        </button>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <p className="pixel-chip pixel-chip-muted">{copy.start} {Number(segment.start).toFixed(3)}s</p>
        <p className="pixel-chip pixel-chip-muted">{copy.end} {Number(segment.end).toFixed(3)}s</p>
        {segment.bpm != null && (
          <p className="pixel-chip pixel-chip-muted">{Number(segment.bpm).toFixed(1)} BPM</p>
        )}
        {segment.key && (
          <p className="pixel-chip pixel-chip-muted">{copy.key}: {segment.key}</p>
        )}
      </div>

      <div className="flex items-center gap-3">
        <span className="pixel-meta text-[var(--pixel-muted)] shrink-0">{copy.pitchLabel}</span>
        <input
          type="range"
          min={-5}
          max={5}
          step={1}
          value={Number(segment.pitch ?? 0)}
          onChange={(e) => onChange(segment.id, "pitch", Number(e.target.value))}
          className="flex-1 accent-[var(--pixel-accent)]"
        />
        <span className={`pixel-chip shrink-0 min-w-[48px] text-center ${Number(segment.pitch ?? 0) !== 0 ? "pixel-chip-active" : "pixel-chip-muted"}`}>
          {Number(segment.pitch ?? 0) > 0 ? `+${segment.pitch}` : segment.pitch ?? 0}
        </span>
      </div>

      <div className="flex flex-wrap items-center gap-2 md:hidden">
        <button
          type="button"
          onClick={() => onDownload(segment)}
          disabled={isDownloading}
          className="pixel-btn flex-1 justify-center"
          style={{ height: "34px", fontSize: "18px" }}
        >
          {isDownloading ? copy.downloading : copy.download}
        </button>
        <button
          type="button"
          onClick={() => onDelete(segment.id)}
          className="pixel-btn pixel-btn-danger"
          aria-label={copy.deleteAria}
          style={{ height: "34px", fontSize: "18px" }}
        >
          {copy.deleteSample}
        </button>
      </div>
    </div>
  );
}

export default SampleRow;
