export const LANGUAGE_STORAGE_KEY = "slicer_language";

function normalizeLanguage(value) {
  if (String(value || "").toLowerCase() === "ru") {
    return "ru";
  }
  return "en";
}

export function getInitialLanguage() {
  if (typeof window === "undefined") {
    return "en";
  }

  const saved = window.localStorage.getItem(LANGUAGE_STORAGE_KEY);
  if (saved) {
    return normalizeLanguage(saved);
  }

  const browser = String(window.navigator?.language || "").toLowerCase();
  if (browser.startsWith("ru")) {
    return "ru";
  }
  return "en";
}

export function persistLanguage(language) {
  if (typeof window === "undefined") {
    return;
  }
  window.localStorage.setItem(LANGUAGE_STORAGE_KEY, normalizeLanguage(language));
}

const RU_FAQ_ITEMS = [
  {
    question: "Какие ссылки поддерживаются?",
    answer: "Сейчас поддерживаются только YouTube URL.",
  },
  {
    question: "Почему анализ может занять время?",
    answer: "Сервис скачивает аудио, конвертирует его в WAV и выполняет сегментацию по onset и энергии.",
  },
  {
    question: "Можно ли вручную подрезать семплы?",
    answer: "Да. Перемещай две вертикальные полосы на waveform, чтобы настроить Start/End.",
  },
  {
    question: "Можно ли скачать один семпл отдельно?",
    answer: "Да. У каждого семпла есть отдельная кнопка Download.",
  },
  {
    question: "В каком формате экспортируется аудио?",
    answer: "WAV, 48kHz, 24-bit PCM.",
  },
  {
    question: "Есть ли ограничение по длине видео?",
    answer: "Да. Для MVP — максимум 30 минут на видео.",
  },
];

const EN_FAQ_ITEMS = [
  {
    question: "What links are supported?",
    answer: "At the moment, only YouTube URLs are supported.",
  },
  {
    question: "Why can analysis take some time?",
    answer: "The service downloads audio, converts it to WAV, and runs onset/energy-based segmentation.",
  },
  {
    question: "Can I trim samples manually?",
    answer: "Yes. Move the two vertical bars on the waveform to set Start/End.",
  },
  {
    question: "Can I download a single sample?",
    answer: "Yes. Every sample row has its own Download button.",
  },
  {
    question: "What export format is used?",
    answer: "WAV, 48kHz, 24-bit PCM.",
  },
  {
    question: "Is there a video length limit?",
    answer: "Yes. For MVP the maximum is 30 minutes per video.",
  },
];

const COPY = {
  en: {
    faqTitle: "FAQ",
    faq: "FAQ",
    back: "Back",
    youtubeExtractor: "YouTube Sample Extractor",
    placeholder: "Paste a YouTube URL, auto-detect slices, trim with dual bars, and export WAV pack.",
    analyze: "Analyze",
    loading: "Loading...",
    loadingHint: "Downloading audio and detecting sample slices...",
    supportLinkMissing: "Support link is not configured yet. Add VITE_SUPPORT_URL in frontend/.env.",
    pasteUrlError: "Paste a YouTube URL before running analysis.",
    failedAnalyze: "Failed to analyze video.",
    noAudioPreview: "No audio preview available. Run analysis first.",
    previewFailed: "Audio preview failed to play.",
    failedDownloadSample: "Failed to download sample.",
    noSegmentsError: "No segments available. Analyze a video first.",
    invalidTimingError: (idx) => `Sample ${idx} has invalid timing values.`,
    endGreaterError: (idx) => `Sample ${idx} must have end time greater than start time.`,
    segmentLengthError: (idx, min, max) => `Sample ${idx} must be between ${min} and ${max} seconds.`,
    exporting: "Exporting",
    exportPack: "Export Pack",
    detectedSamples: "Detected Samples",
    slices: "slices",
    samplePackReady: "Sample pack ready. Download again from",
    thisLink: "this link",
    up: "UP",
    supportDev: "SUPPORT DEV",
    previewing: "Previewing",
    sampleInstruction: "Click waveform to preview. Drag bars or range. Use Arrow keys to move slice.",
    type: "Type",
    download: "Download",
    downloading: "Downloading",
    start: "Start",
    end: "End",
    clickWaveSlice: "Click waveform to preview slice",
    rangeAria: "Move selected range. Drag with mouse or use Arrow Left/Right.",
    rangeTitle: "Drag selected area or use Arrow Left/Right",
    waveformAria: (sampleName) => `Waveform for ${sampleName}. Press Space to preview.`,
    moveStartAria: "Move start marker",
    moveEndAria: "Move end marker",
    langAria: "Language switch",
  },
  ru: {
    faqTitle: "FAQ",
    faq: "FAQ",
    back: "Назад",
    youtubeExtractor: "Извлечение семплов из YouTube",
    placeholder: "Вставь YouTube URL, найди слайсы, подрежь двумя полосами и экспортируй WAV pack.",
    analyze: "Анализ",
    loading: "Загрузка...",
    loadingHint: "Скачиваем аудио и ищем семплы...",
    supportLinkMissing: "Ссылка для поддержки не настроена. Добавь VITE_SUPPORT_URL в frontend/.env.",
    pasteUrlError: "Вставь YouTube URL перед запуском анализа.",
    failedAnalyze: "Не удалось проанализировать видео.",
    noAudioPreview: "Нет аудио для предпрослушивания. Сначала запусти анализ.",
    previewFailed: "Не удалось воспроизвести предпрослушивание.",
    failedDownloadSample: "Не удалось скачать семпл.",
    noSegmentsError: "Семплы отсутствуют. Сначала проанализируй видео.",
    invalidTimingError: (idx) => `У семпла ${idx} некорректные значения времени.`,
    endGreaterError: (idx) => `У семпла ${idx} время окончания должно быть больше старта.`,
    segmentLengthError: (idx, min, max) => `Длина семпла ${idx} должна быть от ${min} до ${max} секунд.`,
    exporting: "Экспорт",
    exportPack: "Экспорт пака",
    detectedSamples: "Найденные семплы",
    slices: "слайсов",
    samplePackReady: "Пак готов. Скачать снова можно по",
    thisLink: "этой ссылке",
    up: "ВВЕРХ",
    supportDev: "ПОДДЕРЖАТЬ",
    previewing: "Прослушивание",
    sampleInstruction: "Кликни по waveform для превью. Тяни полосы или область. Стрелками двигай срез.",
    type: "Тип",
    download: "Скачать",
    downloading: "Скачивание",
    start: "Старт",
    end: "Конец",
    clickWaveSlice: "Кликни по waveform, чтобы прослушать отрезок",
    rangeAria: "Переместить выбранный диапазон. Перетаскивай мышью или используй стрелки влево и вправо.",
    rangeTitle: "Перетаскивай выделение или используй стрелки влево и вправо",
    waveformAria: (sampleName) => `Waveform для ${sampleName}. Нажми пробел для прослушивания.`,
    moveStartAria: "Переместить стартовый маркер",
    moveEndAria: "Переместить конечный маркер",
    langAria: "Переключение языка",
  },
};

export function getCopy(language) {
  const normalized = normalizeLanguage(language);
  return COPY[normalized];
}

export function getFaqItems(language) {
  const normalized = normalizeLanguage(language);
  return normalized === "ru" ? RU_FAQ_ITEMS : EN_FAQ_ITEMS;
}

export function normalizeLang(language) {
  return normalizeLanguage(language);
}
