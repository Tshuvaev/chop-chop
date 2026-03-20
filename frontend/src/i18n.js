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
    question: "Что такое Slicer и для чего он нужен?",
    answer: "Slicer — инструмент для продюсеров и битмейкеров. Вставляешь ссылку на YouTube-видео (трек, сет, лупбук), сервис автоматически находит отдельные звуки и нарезает их на готовые семплы. Результат — ZIP-архив с WAV-файлами, которые можно сразу загрузить в DAW (FL Studio, Ableton, Logic и др.).",
  },
  {
    question: "Как работает анализ?",
    answer: "Анализ проходит в три этапа: 1) Скачивание аудио с YouTube через yt-dlp. 2) Конвертация в WAV 48kHz/24-bit. 3) Поиск onset-точек (моменты атаки звука) с помощью библиотеки librosa — алгоритм ищет резкие изменения энергии и спектра. Каждый найденный участок между двумя onset-точками становится отдельным семплом.",
  },
  {
    question: "Что означают типы семплов: One-shot, Loop, Tonal?",
    answer: "One-shot — одиночный удар или звук с быстрым затуханием (кик, снэр, удар по клавише). Loop — ритмически повторяющийся паттерн с несколькими атаками (барабанная петля, арпеджио). Tonal — длинный гармонический звук без явной атаки (пэд, нота синтезатора, строка). Тип определяется по форме огибающей и количеству онсетов в сегменте.",
  },
  {
    question: "Что такое транзиентный тип (Kick, Snare, Hi-Hat...)?",
    answer: "Для ударных и коротких звуков Slicer дополнительно определяет конкретный тип: Kick (кик-барабан) — доминируют суббасовые частоты; Snare — смесь среднечастотного тона и шума; Hi-Hat Closed — короткий высокочастотный шум; Hi-Hat Open — длиннее, тоже высокочастотный; Clap — шумовой импульс с высоким ZCR; Tom — среднечастотный тональный удар; Cymbal — тарелка с долгим затуханием. Анализ идёт по спектру транзиента.",
  },
  {
    question: "Что такое BPM и тональность (Key)?",
    answer: "BPM (beats per minute) — темп семпла в ударах в минуту. Определяется через beat tracking от librosa. Полезно для подбора совместимых семплов и сетки в DAW. Key (тональность) — музыкальный ключ: например 'A min' или 'C maj'. Определяется через хрома-признаки и профили Крумхансля–Шмукера. Позволяет быстро найти семплы, совместимые по гармонии.",
  },
  {
    question: "Как вручную подрезать семпл?",
    answer: "На каждом семпле отображается waveform с двумя белыми маркерами. Тяни маркеры мышью чтобы сдвинуть start и end точки. Чтобы сдвинуть весь выделенный диапазон — тяни за область между маркерами. Клавиши ← → двигают диапазон на 20мс, с Shift — на 100мс. Клик по waveform вне диапазона — тоже работает как клавиша пробел для превью.",
  },
  {
    question: "Как переименовать или удалить семпл?",
    answer: "Переименование: кликни на название семпла (SAMPLE_001 и т.д.) — оно станет редактируемым полем. Введи новое имя и нажми Enter или кликни в другое место. Удаление: кнопка DELETE у каждого семпла. Удалённый семпл не попадёт в экспортный ZIP. Это полезно если часть нарезок оказалась тишиной или артефактами.",
  },
  {
    question: "Как прослушать семпл до экспорта?",
    answer: "Кликни по waveform или нажми пробел, находясь в фокусе на семпле — он проиграется прямо в браузере. Во время воспроизведения появится бегущая линия playhead. Чтобы остановить — кликни ещё раз.",
  },
  {
    question: "Как экспортировать? Один семпл vs. весь пак?",
    answer: "Один семпл: кнопка DOWNLOAD под конкретным семплом — скачивает один WAV-файл. Весь пак: кнопка EXPORT PACK вверху раздела — скачивает ZIP-архив со всеми оставшимися (не удалёнными) семплами. В архиве каждый семпл — отдельный WAV с твоим именем или автоматическим (sample_001.wav).",
  },
  {
    question: "В каком формате сохраняются семплы?",
    answer: "WAV, 48 kHz, 24-bit PCM (pcm_s24le). Это стандарт без потерь, совместимый со всеми DAW. Частота дискретизации 48kHz выбрана для совместимости с видеопроектами и современными звуковыми библиотеками.",
  },
  {
    question: "Есть ли ограничения?",
    answer: "Максимальная длина видео — 30 минут. Минимальная длина семпла — 1 секунда, максимальная — 8 секунд. Максимум 200 семплов за один анализ. Файлы хранятся на сервере 30 минут, после чего автоматически удаляются — скачай пак до истечения этого времени.",
  },
  {
    question: "Какие ссылки поддерживаются?",
    answer: "На данный момент только YouTube (youtube.com/watch?v=... и youtu.be/...). Поддержка SoundCloud, Bandcamp и других платформ в планах.",
  },
];

const EN_FAQ_ITEMS = [
  {
    question: "What is Slicer and what is it for?",
    answer: "Slicer is a tool for producers and beatmakers. Paste a YouTube link (track, DJ set, loopbook), and the service automatically detects individual sounds and cuts them into ready-to-use samples. The result is a ZIP archive of WAV files you can instantly load into your DAW (FL Studio, Ableton, Logic, etc.).",
  },
  {
    question: "How does analysis work?",
    answer: "Analysis runs in three stages: 1) Audio download from YouTube via yt-dlp. 2) Conversion to WAV 48kHz/24-bit. 3) Onset detection using the librosa library — the algorithm finds sharp changes in energy and spectrum. Each detected section between two onset points becomes a separate sample.",
  },
  {
    question: "What do the sample types mean: One-shot, Loop, Tonal?",
    answer: "One-shot — a single hit or sound with a fast decay (kick, snare, key press). Loop — a rhythmically repeating pattern with multiple attacks (drum loop, arpeggio). Tonal — a long harmonic sound with no clear attack (pad, synth note, string). The type is determined by the shape of the amplitude envelope and the number of onsets in the segment.",
  },
  {
    question: "What is the transient type (Kick, Snare, Hi-Hat...)?",
    answer: "For percussive and short sounds, Slicer also identifies the specific hit type: Kick — dominant sub-bass frequencies; Snare — mix of mid-frequency tone and noise; Hi-Hat Closed — short high-frequency noise burst; Hi-Hat Open — longer, also high-frequency; Clap — noise impulse with high zero-crossing rate; Tom — mid-frequency tonal hit; Cymbal — cymbal with long decay. Classification is based on the transient's frequency spectrum.",
  },
  {
    question: "What are BPM and Key?",
    answer: "BPM (beats per minute) — the tempo of the sample in beats per minute, detected via librosa's beat tracking. Useful for finding compatible samples and setting up your DAW grid. Key — the musical key: e.g. 'A min' or 'C maj', detected using chroma features and the Krumhansl–Schmuckler key-finding algorithm. Lets you quickly find harmonically compatible samples.",
  },
  {
    question: "How do I trim a sample manually?",
    answer: "Each sample shows a waveform with two white markers. Drag the markers to move the start and end points. Drag the selected region between markers to shift the whole selection. Arrow keys ← → nudge the range by 20ms, Shift+Arrow by 100ms. Clicking the waveform outside the range also triggers preview (same as Space).",
  },
  {
    question: "How do I rename or delete a sample?",
    answer: "Rename: click the sample name (SAMPLE_001, etc.) — it becomes an editable field. Type a new name and press Enter or click elsewhere to save. Delete: use the DELETE button on each sample row. Deleted samples are excluded from the export ZIP. Useful for removing silence or noise artifacts.",
  },
  {
    question: "How do I preview a sample before exporting?",
    answer: "Click the waveform or press Space while the sample row is focused — it plays directly in the browser. A moving playhead line appears during playback. Click again to stop.",
  },
  {
    question: "How do I export? Single sample vs. full pack?",
    answer: "Single sample: the DOWNLOAD button on each row downloads one WAV file. Full pack: the EXPORT PACK button at the top downloads a ZIP archive with all remaining (non-deleted) samples. Each sample in the archive is a separate WAV file with your custom name or the auto-generated one (sample_001.wav).",
  },
  {
    question: "What format are samples saved in?",
    answer: "WAV, 48 kHz, 24-bit PCM (pcm_s24le). This is a lossless format compatible with all DAWs. 48kHz was chosen for compatibility with video projects and modern sound libraries.",
  },
  {
    question: "Are there any limitations?",
    answer: "Maximum video length: 30 minutes. Minimum sample length: 1 second, maximum: 8 seconds. Maximum 200 samples per analysis. Files are stored on the server for 30 minutes and then automatically deleted — download your pack before then.",
  },
  {
    question: "What links are supported?",
    answer: "Currently only YouTube (youtube.com/watch?v=... and youtu.be/...). Support for SoundCloud, Bandcamp, and other platforms is planned.",
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
    deleteSample: "Delete",
    deleteAria: "Delete sample",
    renameSample: "Rename",
    key: "Key",
    allSlices: "All",
    bestOnly: "Best Only",
    bestOnlyHint: (hidden) => `${hidden} repetitive or low-interest slices hidden`,
    pitchLabel: "Pitch",
    ideaBtn: "IDEA",
    ideaTitle: "Got an idea?",
    ideaPlaceholder: "Describe your idea or feature request...",
    ideaSend: "Send",
    ideaClose: "Close",
    ideaEmpty: "Please write something first.",
    ideaSendFailed: "Failed to send. Try again later.",
    supportTitle: "Support the developer",
    supportPhone: "89773491764",
    supportBankNote: "Any bank — transfer by phone number (Russia)",
    supportClose: "Close",
    stageLabels: {
      downloading: "Downloading audio from YouTube...",
      converting: "Converting to WAV...",
      segmenting: "Detecting sample slices...",
      done: "Done!",
    },
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
    deleteSample: "Удалить",
    deleteAria: "Удалить семпл",
    renameSample: "Переименовать",
    key: "Тональность",
    allSlices: "Все",
    bestOnly: "Лучшие",
    bestOnlyHint: (hidden) => `${hidden} повторяющихся или малоинтересных семплов скрыто`,
    pitchLabel: "Питч",
    ideaBtn: "ИДЕЯ",
    ideaTitle: "Есть идея?",
    ideaPlaceholder: "Опиши идею или пожелание...",
    ideaSend: "Отправить",
    ideaClose: "Закрыть",
    ideaEmpty: "Напиши что-нибудь сначала.",
    ideaSendFailed: "Не удалось отправить. Попробуй позже.",
    supportTitle: "Поддержать разработчика",
    supportPhone: "89773491764",
    supportBankNote: "Любой банк — перевод по номеру телефона",
    supportClose: "Закрыть",
    stageLabels: {
      downloading: "Скачиваем аудио с YouTube...",
      converting: "Конвертируем в WAV...",
      segmenting: "Ищем семплы...",
      done: "Готово!",
    },
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
