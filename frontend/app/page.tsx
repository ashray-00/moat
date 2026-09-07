"use client";

import { useEffect, useState } from "react";
import { askStream } from "./lib/ask";

function ThemeToggle() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    setDark(document.documentElement.classList.contains("dark"));
  }, []);

  function toggle() {
    const next = !document.documentElement.classList.contains("dark");
    document.documentElement.classList.toggle("dark", next);
    localStorage.setItem("moat-theme", next ? "dark" : "light");
    setDark(next);
  }

  return (
    <button
      type="button"
      onClick={toggle}
      aria-label={dark ? "Switch to light mode" : "Switch to dark mode"}
      className="rounded-chip border border-line px-2.5 py-1 text-xs text-mist transition-colors hover:border-accent hover:text-ink active:scale-[0.97]"
    >
      {dark ? "Light" : "Dark"}
    </button>
  );
}

export default function Home() {
  const [q, setQ] = useState("");
  const [ticker, setTicker] = useState("AAPL");
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState<
    { id: string; ticker: string; section: string }[]
  >([]);
  const [busy, setBusy] = useState(false);

  async function ask() {
    setAnswer("");
    setSources([]);
    setBusy(true);
    for await (const ev of askStream(q, ticker)) {
      if (ev.type === "sources") setSources(ev.sources);
      else if (ev.type === "answer") setAnswer((a) => a + ev.delta);
    }
    setBusy(false);
  }

  return (
    <div className="flex min-h-full flex-col">
      <header className="border-b border-line/80">
        <div className="mx-auto flex max-w-measure items-center justify-between gap-4 px-5 py-4 sm:px-6">
          <div className="min-w-0">
            <p className="font-display text-xl font-medium tracking-tight text-ink sm:text-2xl">
              Moat
            </p>
            <p className="mt-0.5 truncate text-sm text-mist">
              Equity research over SEC filings
            </p>
          </div>
          <ThemeToggle />
        </div>
      </header>

      <main className="mx-auto flex w-full max-w-measure flex-1 flex-col gap-10 px-5 py-10 sm:px-6 sm:py-14">
        <section aria-label="Ask a research question" className="space-y-3">
          <div
            className={[
              "flex flex-col gap-0 overflow-hidden rounded-search border border-line bg-surface shadow-search",
              "transition-[box-shadow,border-color] duration-200",
              "focus-within:border-accent focus-within:shadow-[0_0_0_3px_var(--moat-accent-muted),var(--moat-shadow-search)]",
              "sm:flex-row sm:items-stretch",
            ].join(" ")}
          >
            <label className="sr-only" htmlFor="ticker">
              Ticker
            </label>
            <input
              id="ticker"
              value={ticker}
              onChange={(e) => setTicker(e.target.value.toUpperCase())}
              className="w-full shrink-0 border-b border-line bg-transparent px-4 py-3.5 font-mono text-sm font-medium tracking-wide text-ink outline-none placeholder:text-stone sm:w-[5.5rem] sm:border-b-0 sm:border-r sm:py-3"
              spellCheck={false}
              autoComplete="off"
              aria-label="Ticker symbol"
            />
            <label className="sr-only" htmlFor="query">
              Question
            </label>
            <input
              id="query"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Ask about a filing…"
              className="min-w-0 flex-1 bg-transparent px-4 py-3.5 text-[0.95rem] text-ink outline-none placeholder:text-stone sm:py-3"
              onKeyDown={(e) => e.key === "Enter" && !busy && ask()}
            />
            <div className="border-t border-line p-2 sm:border-t-0 sm:p-1.5 sm:pl-0">
              <button
                type="button"
                onClick={ask}
                disabled={busy || !q.trim()}
                className={[
                  "flex w-full items-center justify-center gap-2 rounded-[0.4rem] bg-accent px-4 py-2.5 text-sm font-medium text-canvas",
                  "transition-[background-color,transform,opacity] duration-150",
                  "hover:bg-accent-hover active:scale-[0.98]",
                  "disabled:cursor-not-allowed disabled:opacity-45 disabled:active:scale-100",
                  "sm:w-auto sm:min-w-[4.75rem]",
                ].join(" ")}
              >
                {busy ? (
                  <>
                    <span
                      className="size-3.5 animate-[spin_0.7s_linear_infinite] rounded-full border-2 border-canvas/30 border-t-canvas"
                      aria-hidden
                    />
                    <span>Asking</span>
                  </>
                ) : (
                  "Ask"
                )}
              </button>
            </div>
          </div>
        </section>

        {sources.length > 0 && (
          <section
            aria-label="Cited sources"
            className="animate-fade-up space-y-3"
          >
            <h2 className="footnote-label">Sources</h2>
            <div className="flex flex-wrap gap-2">
              {sources.map((s) => (
                <span
                  key={s.id}
                  title={`${s.ticker} · ${s.section}`}
                  className={[
                    "inline-flex items-center gap-1.5 rounded-chip border border-line bg-surface px-2 py-1",
                    "text-xs text-mist shadow-none transition-[box-shadow,transform,border-color] duration-150",
                    "hover:-translate-y-px hover:border-accent/40 hover:shadow-chip",
                  ].join(" ")}
                >
                  <span className="font-mono text-[0.7rem] font-medium tracking-tight text-accent">
                    {s.id}
                  </span>
                  <span className="text-stone">·</span>
                  <span>
                    {s.ticker} · {s.section}
                  </span>
                </span>
              ))}
            </div>
          </section>
        )}

        {(answer || busy) && (
          <article
            aria-live="polite"
            className={[
              "animate-fade-up max-w-none text-[1.05rem] leading-[1.7] text-ink",
              busy && answer ? "typing-cursor" : "",
            ]
              .filter(Boolean)
              .join(" ")}
          >
            <p className="whitespace-pre-wrap">{answer}</p>
          </article>
        )}

        <footer className="mt-auto pt-6">
          <p className="footnote-label">Research only — not investment advice</p>
        </footer>
      </main>
    </div>
  );
}
