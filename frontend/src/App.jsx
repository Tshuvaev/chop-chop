import { useEffect, useMemo, useRef, useState } from "react";

import SampleRow from "./components/SampleRow";
import Spinner from "./components/Spinner";
import { getCopy, getInitialLanguage, normalizeLang, persistLanguage } from "./i18n";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";
const SUPPORT_URL = import.meta.env.VITE_SUPPORT_URL || "";
const SESSION_STORAGE_KEY = "slicer_session_id";

function createSessionId() {
  if (window.crypto?.randomUUID) {
    return window.crypto.randomUUID().replace(/-/g, "");
  }

  return `session_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

function getOrCreateSessionId() {
  const existing = window.sessionStorage.getItem(SESSION_STORAGE_KEY);
  if (existing) {
    return existing;
  }

  const created = createSessionId();
  window.sessionStorage.setItem(SESSION_STORAGE_KEY, created);
  return created;
}

async function parseApiError(response) {
  try {
    const data = await response.json();
    return data?.detail || "Unexpected API error.";
  } catch {
    return "Unexpected API error.";
  }
}

function App() {
  const [language, setLanguage] = useState(getInitialLanguage);
  const [sessionId] = useState(getOrCreateSessionId);
  const [url, setUrl] = useState("");
  const [title, setTitle] = useState("");
  const [duration, setDuration] = useState(0);
  const [segments, setSegments] = useState([]);
  const [bpm, setBpm] = useState(null);
  const [audioPath, setAudioPath] = useState("");
  const [loading, setLoading] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [downloadingId, setDownloadingId] = useState(null);
  const [playingId, setPlayingId] = useState(null);
  const [playbackTime, setPlaybackTime] = useState(null);
  const [downloadUrl, setDownloadUrl] = useState("");
  const [error, setError] = useState("");
  const [showScrollTop, setShowScrollTop] = useState(false);

  const [progressStage, setProgressStage] = useState("idle");
  const [progressPct, setProgressPct] = useState(0);
  const [bestOnly, setBestOnly] = useState(false);
  const [showSupportModal, setShowSupportModal] = useState(false);
  const [showIdeaModal, setShowIdeaModal] = useState(false);
  const [ideaText, setIdeaText] = useState("");
  const [ideaError, setIdeaError] = useState("");
  const progressPollRef = useRef(null);

  const currentAudioRef = useRef(null);
  const cleanupPlaybackRef = useRef(() => {});
  const playbackFrameRef = useRef(null);
  const copy = useMemo(() => getCopy(language), [language]);

  const visibleSegments = useMemo(() => {
    if (!bestOnly) return segments;
    return segments.filter((s) => !s.is_duplicate && (s.interest_score == null || s.interest_score >= 0.28));
  }, [segments, bestOnly]);

  useEffect(() => {
    persistLanguage(language);
  }, [language]);

  const audioUrl = useMemo(() => {
    if (!audioPath) {
      return "";
    }
    return `${API_BASE_URL}${audioPath}`;
  }, [audioPath]);

  const stopPlayback = () => {
    if (playbackFrameRef.current !== null) {
      window.cancelAnimationFrame(playbackFrameRef.current);
      playbackFrameRef.current = null;
    }

    cleanupPlaybackRef.current();
    const current = currentAudioRef.current;
    if (current) {
      current.pause();
      currentAudioRef.current = null;
    }
    setPlayingId(null);
    setPlaybackTime(null);
  };

  useEffect(() => {
    return () => {
      stopPlayback();
    };
  }, []);

  useEffect(() => {
    const onScroll = () => {
      setShowScrollTop(window.scrollY > 260);
    };

    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
    };
  }, []);

  const handleUrlKeyDown = (event) => {
    if (event.key !== "Enter") {
      return;
    }

    event.preventDefault();
    if (!loading) {
      handleAnalyze();
    }
  };

  const handleAnalyze = async () => {
    if (!url.trim()) {
      setError(copy.pasteUrlError);
      return;
    }

    setError("");
    setLoading(true);
    setDownloadUrl("");
    setBpm(null);
    setProgressStage("idle");
    setProgressPct(0);
    stopPlayback();

    try {
      // 1. Start background analysis (returns immediately — no timeout)
      const startRes = await fetch(`${API_BASE_URL}/analyze`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Session-ID": sessionId,
        },
        body: JSON.stringify({ url: url.trim() }),
      });

      if (!startRes.ok) {
        throw new Error(await parseApiError(startRes));
      }

      // 2. Poll status until done or error
      await new Promise((resolve, reject) => {
        progressPollRef.current = setInterval(async () => {
          try {
            const statusRes = await fetch(`${API_BASE_URL}/session/${sessionId}/status`);
            if (!statusRes.ok) return;
            const data = await statusRes.json();
            setProgressStage(data.stage || "idle");
            setProgressPct(Number(data.pct || 0));

            if (data.stage === "done") {
              clearInterval(progressPollRef.current);
              resolve();
            } else if (data.stage === "error") {
              clearInterval(progressPollRef.current);
              reject(new Error(data.error || copy.failedAnalyze));
            }
          } catch {}
        }, 1500);
      });

      // 3. Fetch result
      const resultRes = await fetch(`${API_BASE_URL}/session/${sessionId}/result`);
      if (!resultRes.ok) {
        throw new Error(await parseApiError(resultRes));
      }
      const result = await resultRes.json();
      setTitle(result.title || "Untitled");
      setDuration(Number(result.duration || 0));
      setBpm(result.bpm ?? null);
      setSegments(result.segments || []);
      setAudioPath(result.audio_url || "");
    } catch (requestError) {
      setSegments([]);
      setAudioPath("");
      setError(requestError.message || copy.failedAnalyze);
    } finally {
      clearInterval(progressPollRef.current);
      setLoading(false);
    }
  };

  const handleDeleteSegment = (segmentId) => {
    setSegments((prev) => prev.filter((s) => s.id !== segmentId));
  };

  const handleScrollTop = () => {
    window.scrollTo({ top: 0, behavior: "smooth" });
  };

  const handleSupportDeveloper = () => {
    setShowSupportModal(true);
  };

  const handleSendIdea = async () => {
    if (!ideaText.trim()) {
      setIdeaError(copy.ideaEmpty);
      return;
    }
    try {
      const res = await fetch(`${API_BASE_URL}/idea`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: ideaText.trim() }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setIdeaError(data.detail || copy.ideaSendFailed);
        return;
      }
      setShowIdeaModal(false);
      setIdeaText("");
      setIdeaError("");
    } catch {
      setIdeaError(copy.ideaSendFailed);
    }
  };

  const handleLanguageChange = (nextLanguage) => {
    setLanguage(normalizeLang(nextLanguage));
  };

  const handleSegmentChange = (segmentId, field, value) => {
    const numeric = Number(value);
    setSegments((prev) =>
      prev.map((segment) => {
        if (segment.id !== segmentId) {
          return segment;
        }
        return {
          ...segment,
          [field]: Number.isFinite(numeric) ? numeric : 0,
        };
      })
    );
  };

  const handlePreviewSegment = (segment) => {
    if (!audioUrl) {
      setError(copy.noAudioPreview);
      return;
    }

    stopPlayback();

    const start = Number(segment.start);
    const end = Number(segment.end);

    const pitch = Number(segment.pitch ?? 0);
    const audio = new Audio(audioUrl);
    currentAudioRef.current = audio;

    const tick = () => {
      if (currentAudioRef.current !== audio) {
        return;
      }

      const current = audio.currentTime;
      setPlaybackTime(current);

      if (current >= end) {
        stopPlayback();
        return;
      }

      playbackFrameRef.current = window.requestAnimationFrame(tick);
    };

    const startSmoothPlayhead = () => {
      if (playbackFrameRef.current !== null) {
        window.cancelAnimationFrame(playbackFrameRef.current);
      }
      playbackFrameRef.current = window.requestAnimationFrame(tick);
    };

    const onTimeUpdate = () => {
      // RAF can throttle in background tabs; keep this for reliable stopping.
      if (audio.currentTime >= end) {
        stopPlayback();
      }
    };

    const onLoadedMetadata = async () => {
      try {
        audio.currentTime = start;
        audio.playbackRate = Math.pow(2, pitch / 12);
        setPlaybackTime(start);
        await audio.play();
        startSmoothPlayhead();
      } catch {
        setError(copy.previewFailed);
        stopPlayback();
      }
    };

    const onError = () => {
      setError(copy.previewFailed);
      stopPlayback();
    };

    audio.addEventListener("loadedmetadata", onLoadedMetadata);
    audio.addEventListener("timeupdate", onTimeUpdate);
    audio.addEventListener("ended", stopPlayback);
    audio.addEventListener("error", onError);

    cleanupPlaybackRef.current = () => {
      audio.removeEventListener("loadedmetadata", onLoadedMetadata);
      audio.removeEventListener("timeupdate", onTimeUpdate);
      audio.removeEventListener("ended", stopPlayback);
      audio.removeEventListener("error", onError);
      if (currentAudioRef.current === audio && playbackFrameRef.current !== null) {
        window.cancelAnimationFrame(playbackFrameRef.current);
        playbackFrameRef.current = null;
      }
      cleanupPlaybackRef.current = () => {};
    };

    audio.load();
    setPlayingId(segment.id);
    setPlaybackTime(start);
  };

  const handleDownloadSample = async (segment) => {
    const currentSegment = segments.find((item) => item.id === segment.id) || segment;

    setError("");
    setDownloadingId(currentSegment.id);

    try {
      const payload = {
        segment: {
          id: currentSegment.id,
          name: currentSegment.name || `sample_${String(currentSegment.id || 1).padStart(3, "0")}`,
          start: Number(Number(currentSegment.start).toFixed(3)),
          end: Number(Number(currentSegment.end).toFixed(3)),
          pitch: Number(currentSegment.pitch ?? 0),
        },
      };

      const response = await fetch(`${API_BASE_URL}/export/sample`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Session-ID": sessionId,
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error(await parseApiError(response));
      }

      const data = await response.json();
      const fullDownloadUrl = `${API_BASE_URL}${data.download_url}`;

      const link = document.createElement("a");
      link.href = fullDownloadUrl;
      link.download = data.file_name || "sample.wav";
      link.rel = "noopener noreferrer";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (requestError) {
      setError(requestError.message || copy.failedDownloadSample);
    } finally {
      setDownloadingId(null);
    }
  };

  const validateSegments = () => {
    if (!segments.length) {
      return copy.noSegmentsError;
    }

    for (let idx = 0; idx < segments.length; idx += 1) {
      const segment = segments[idx];
      const start = Number(segment.start);
      const end = Number(segment.end);
      const length = end - start;

      if (!Number.isFinite(start) || !Number.isFinite(end)) {
        return copy.invalidTimingError(idx + 1);
      }

      if (start < 0 || end <= start) {
        return copy.endGreaterError(idx + 1);
      }

      if (length < 0.1 || length > 8) {
        return copy.segmentLengthError(idx + 1, 0.1, 8);
      }
    }

    return "";
  };

  const handleExport = async () => {
    const validationError = validateSegments();
    if (validationError) {
      setError(validationError);
      return;
    }

    setError("");
    setExporting(true);

    try {
      const payload = {
        segments: segments.map((segment, idx) => ({
          id: idx + 1,
          name: segment.name || `sample_${String(idx + 1).padStart(3, "0")}`,
          start: Number(Number(segment.start).toFixed(3)),
          end: Number(Number(segment.end).toFixed(3)),
          pitch: Number(segment.pitch ?? 0),
        })),
      };

      const response = await fetch(`${API_BASE_URL}/export`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "X-Session-ID": sessionId,
        },
        body: JSON.stringify(payload),
      });

      if (!response.ok) {
        throw new Error(await parseApiError(response));
      }

      const data = await response.json();
      const fullDownloadUrl = `${API_BASE_URL}${data.download_url}`;
      setDownloadUrl(fullDownloadUrl);

      const link = document.createElement("a");
      link.href = fullDownloadUrl;
      link.download = data.file_name || "sample_pack.zip";
      link.rel = "noopener noreferrer";
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
    } catch (requestError) {
      setError(requestError.message || copy.failedExportSamples);
    } finally {
      setExporting(false);
    }
  };

  return (
    <main className="mx-auto w-full max-w-6xl overflow-x-hidden px-4 pb-8 pt-5 sm:px-5 md:px-8 md:pt-8">
      <section className="pixel-panel w-full p-3 sm:p-4 md:p-6">
        <div className="mb-5 flex flex-col gap-2">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex min-h-[56px] items-center gap-3">
              <img src="/slicer-logo.svg" alt="Slicer logo" className="site-logo" />
              <p className="site-brand-text m-0">Slicer</p>
            </div>

            <div className="flex items-center gap-2">
              <div className="flex items-center gap-1" role="group" aria-label={copy.langAria}>
                <button
                  type="button"
                  onClick={() => handleLanguageChange("en")}
                  className={`pixel-chip ${language === "en" ? "pixel-chip-active" : "pixel-chip-muted"}`}
                >
                  ENG
                </button>
                <button
                  type="button"
                  onClick={() => handleLanguageChange("ru")}
                  className={`pixel-chip ${language === "ru" ? "pixel-chip-active" : "pixel-chip-muted"}`}
                >
                  RU
                </button>
              </div>

              <a href="/faq" className="pixel-btn" style={{ height: "36px", fontSize: "18px" }}>
                <img src="/icons/faq.svg" alt="" aria-hidden="true" className="pixel-btn-icon" />
                {copy.faq}
              </a>
            </div>
          </div>
          <h1 className="pixel-title text-[12px] text-[var(--pixel-muted)] md:text-[14px]">{copy.youtubeExtractor}</h1>
        </div>

        <div className="grid gap-2 md:grid-cols-[1fr_auto]">
          <div className="pixel-input-wrap">
            <img src="/icons/search.svg" alt="" aria-hidden="true" className="pixel-search-icon" />
            <input
              type="url"
              value={url}
              onChange={(event) => setUrl(event.target.value)}
              onKeyDown={handleUrlKeyDown}
              placeholder={copy.placeholder}
              className="pixel-input pixel-input-with-icon w-full"
            />
          </div>

          <button
            type="button"
            disabled={loading}
            onClick={handleAnalyze}
            className="pixel-btn pixel-btn-primary relative overflow-hidden"
          >
            {loading && (
              <span
                className="absolute inset-0 bg-white/30 transition-[width] duration-500 ease-out"
                style={{ width: `${progressPct}%` }}
                aria-hidden="true"
              />
            )}
            <span className="relative z-10">
              {loading ? copy.loading : copy.analyze}
            </span>
          </button>
        </div>

        {loading && (
          <p className="mt-2 flex items-center gap-2 text-[20px] leading-none text-[var(--pixel-muted)]">
            <span className="inline-block h-3 w-3 shrink-0 animate-spin rounded-full border-2 border-[var(--pixel-muted)] border-t-transparent" aria-hidden="true" />
            {copy.stageLabels?.[progressStage] || copy.loadingHint}
          </p>
        )}

        {error && <div className="pixel-panel pixel-panel-error mt-3 px-3 py-2 pixel-meta">{error}</div>}
      </section>

      {segments.length > 0 && (
        <section className="pixel-panel mt-4 w-full space-y-3 p-3 sm:p-4 md:p-6">
          <div className="flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
            <div className="space-y-1">
              <h2 className="pixel-title text-[10px] text-[var(--pixel-text)] md:text-[12px]">{copy.detectedSamples}</h2>
              <p className="pixel-meta text-[var(--pixel-muted)]">
                {title} // {duration.toFixed(2)}s // {segments.length} {copy.slices}{bpm !== null ? ` // ${bpm} BPM` : ""}
              </p>
              <div className="flex items-center gap-1 pt-1" role="group">
                <button
                  type="button"
                  onClick={() => setBestOnly(false)}
                  className={`pixel-chip ${!bestOnly ? "pixel-chip-active" : "pixel-chip-muted"}`}
                >
                  {copy.allSlices}
                </button>
                <button
                  type="button"
                  onClick={() => setBestOnly(true)}
                  className={`pixel-chip ${bestOnly ? "pixel-chip-active" : "pixel-chip-muted"}`}
                >
                  {copy.bestOnly}
                </button>
              </div>
              {bestOnly && visibleSegments.length < segments.length && (
                <p className="pixel-meta text-[var(--pixel-accent)]">
                  {copy.bestOnlyHint(segments.length - visibleSegments.length)}
                </p>
              )}
            </div>

            <button type="button" onClick={handleExport} disabled={exporting} className="pixel-btn pixel-btn-secondary">
              {exporting && <Spinner />}
              {exporting ? copy.exporting : copy.exportPack}
            </button>
          </div>

          <div className="space-y-2">
            {visibleSegments.map((segment) => (
              <SampleRow
                key={segment.id}
                segment={segment}
                language={language}
                onChange={handleSegmentChange}
                onPreview={handlePreviewSegment}
                onDownload={handleDownloadSample}
                onDelete={handleDeleteSegment}
                isPlaying={playingId === segment.id}
                playheadTime={playingId === segment.id ? playbackTime : null}
                isDownloading={downloadingId === segment.id}
              />
            ))}
          </div>

          {downloadUrl && (
            <div className="pixel-panel px-3 py-2 pixel-meta text-[var(--pixel-accent)]">
              {copy.samplePackReady}{" "}
              <a className="underline decoration-dotted" href={downloadUrl}>
                {copy.thisLink}
              </a>
              .
            </div>
          )}
        </section>
      )}

      <div className="pixel-fab-stack">
        {showScrollTop && (
          <button type="button" onClick={handleScrollTop} className="pixel-btn pixel-btn-fab" aria-label="Scroll to top">
            <img src="/icons/arrow_up.svg" alt="" aria-hidden="true" className="pixel-fab-icon" />
            {copy.up}
          </button>
        )}

        <button
          type="button"
          onClick={() => { setShowIdeaModal(true); setIdeaError(""); }}
          className="pixel-btn pixel-btn-fab"
          aria-label="Submit idea"
        >
          {copy.ideaBtn}
        </button>

        <button
          type="button"
          onClick={handleSupportDeveloper}
          className="pixel-btn pixel-btn-fab"
          aria-label="Support developer"
        >
          <img src="/icons/coffee.svg" alt="" aria-hidden="true" className="pixel-fab-icon" />
          {copy.supportDev}
        </button>
      </div>

      {showSupportModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          onClick={() => setShowSupportModal(false)}
        >
          <div className="pixel-panel w-full max-w-sm p-5 space-y-3" onClick={(e) => e.stopPropagation()}>
            <h2 className="pixel-title text-[11px] text-[var(--pixel-text)]">{copy.supportTitle}</h2>
            <p className="pixel-meta text-[var(--pixel-muted)]">{copy.supportBankNote}</p>
            <p className="pixel-title text-[18px] tracking-widest text-[var(--pixel-accent)]">{copy.supportPhone}</p>
            <button
              type="button"
              onClick={() => setShowSupportModal(false)}
              className="pixel-btn pixel-btn-secondary w-full justify-center"
            >
              {copy.supportClose}
            </button>
          </div>
        </div>
      )}

      {showIdeaModal && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4"
          onClick={() => setShowIdeaModal(false)}
        >
          <div className="pixel-panel w-full max-w-2xl p-5 space-y-3" onClick={(e) => e.stopPropagation()}>
            <h2 className="pixel-title text-[11px] text-[var(--pixel-text)]">{copy.ideaTitle}</h2>
            <textarea
              value={ideaText}
              onChange={(e) => { setIdeaText(e.target.value); setIdeaError(""); }}
              placeholder={copy.ideaPlaceholder}
              rows={5}
              className="pixel-input w-full resize-none p-2"
            />
            {ideaError && <p className="pixel-meta text-[var(--pixel-accent)]">{ideaError}</p>}
            <div className="flex gap-2">
              <button type="button" onClick={handleSendIdea} className="pixel-btn pixel-btn-primary flex-1 justify-center">
                {copy.ideaSend}
              </button>
              <button type="button" onClick={() => setShowIdeaModal(false)} className="pixel-btn pixel-btn-secondary flex-1 justify-center">
                {copy.ideaClose}
              </button>
            </div>
          </div>
        </div>
      )}
    </main>
  );
}

export default App;
