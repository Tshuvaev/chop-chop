import { useEffect, useMemo, useState } from "react";

import { getCopy, getFaqItems, getInitialLanguage, normalizeLang, persistLanguage } from "./i18n";

function Faq() {
  const [language, setLanguage] = useState(getInitialLanguage);
  const copy = useMemo(() => getCopy(language), [language]);
  const faqItems = useMemo(() => getFaqItems(language), [language]);

  useEffect(() => {
    persistLanguage(language);
  }, [language]);

  useEffect(() => {
    document.title = `Slicer ${copy.faqTitle}`;
    return () => {
      document.title = "Slicer";
    };
  }, [copy.faqTitle]);

  const handleLanguageChange = (nextLanguage) => {
    setLanguage(normalizeLang(nextLanguage));
  };

  return (
    <main className="mx-auto w-full max-w-6xl overflow-x-hidden px-4 pb-8 pt-5 sm:px-5 md:px-8 md:pt-8">
      <section className="pixel-panel w-full p-3 sm:p-4 md:p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div className="space-y-1">
            <p className="pixel-caption m-0">Slicer</p>
            <h1 className="pixel-title text-[12px] text-[var(--pixel-text)] md:text-[14px]">{copy.faqTitle}</h1>
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

            <a href="/" className="pixel-btn" style={{ height: "36px", fontSize: "18px" }}>
              {copy.back}
            </a>
          </div>
        </div>
      </section>

      <section className="mt-4 grid gap-2">
        {faqItems.map((item) => (
          <article key={item.question} className="pixel-panel p-3 sm:p-4">
            <h2 className="pixel-title text-[9px] text-[var(--pixel-text)] md:text-[10px]">{item.question}</h2>
            <p className="pixel-meta mt-2 text-[var(--pixel-muted)]">{item.answer}</p>
          </article>
        ))}
      </section>
    </main>
  );
}

export default Faq;
