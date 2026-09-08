"use client";

import { useEffect, useState } from "react";
import type { User } from "@supabase/supabase-js";
import { AccountPanel } from "./AccountPanel";
import {
  AskHttpError,
  addWatchlistTicker,
  askStream,
  fetchWatchlist,
  runAgent,
} from "../lib/ask";
import { getAccessToken, signOut } from "../lib/auth";
import { ThemeToggle } from "./ThemeToggle";

type ResearchWorkspaceProps = {
  accessToken: string;
  displayName: string;
  user: User;
};

export function ResearchWorkspace({
  accessToken,
  displayName,
  user,
}: ResearchWorkspaceProps) {
  const [q, setQ] = useState("");
  const [ticker, setTicker] = useState("AAPL");
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState<
    { id: string; ticker: string; section: string }[]
  >([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [mode, setMode] = useState<"ask" | "agent">("ask");
  const [watchlist, setWatchlist] = useState<string[]>([]);
  const [prior, setPrior] = useState<{ q: string; a: string } | null>(null);
  const [lastQuestion, setLastQuestion] = useState("");
  const [accountOpen, setAccountOpen] = useState(false);

  const threadId = "research";

  useEffect(() => {
    let cancelled = false;
    fetchWatchlist(accessToken)
      .then((list) => {
        if (!cancelled) setWatchlist(list);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  async function ask() {
    const question = q.trim();
    if (!question) return;
    const token = (await getAccessToken()) ?? accessToken;
    if (!token) {
      setError("Sign in required.");
      return;
    }
    if (answer.trim() && lastQuestion) {
      setPrior({ q: lastQuestion, a: answer });
    }
    setLastQuestion(question);
    setAnswer("");
    setSources([]);
    setError(null);
    setBusy(true);
    try {
      if (mode === "agent") {
        const res = await runAgent(token, question, threadId);
        setAnswer(res.answer || "No response.");
        return;
      }
      for await (const ev of askStream(question, ticker, {
        token,
        threadId,
      })) {
        if (ev.type === "sources") setSources(ev.sources);
        else if (ev.type === "answer") setAnswer((a) => a + ev.delta);
        else if (ev.type === "error") setError(ev.message);
      }
    } catch (e) {
      if (e instanceof AskHttpError) {
        if (e.status === 402) {
          setError(e.message);
          setAccountOpen(true);
        } else if (e.status === 401) setError("Sign in required.");
        else setError(e.message);
      } else {
        setError(e instanceof Error ? e.message : "Request failed");
      }
    } finally {
      setBusy(false);
    }
  }

  async function onAddWatch() {
    try {
      setWatchlist(await addWatchlistTicker(accessToken, ticker));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not update watchlist");
    }
  }

  return (
    <div className="flex min-h-full flex-col">
      <header className="border-b border-line/80">
        <div className="mx-auto flex max-w-measure flex-col gap-3 px-5 py-4 sm:px-6">
          <div className="flex items-center justify-between gap-4">
            <div className="min-w-0">
              <p className="font-display text-xl font-medium tracking-tight text-ink sm:text-2xl">
                Moat
              </p>
              <p className="mt-0.5 truncate text-sm text-mist">
                Equity research over SEC filings
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <button
                type="button"
                onClick={() => setAccountOpen(true)}
                className="rounded-chip border border-line px-2.5 py-1 text-xs text-mist transition-colors hover:border-accent hover:text-ink"
              >
                Account
              </button>
              <ThemeToggle />
            </div>
          </div>
          <div className="flex items-center justify-between gap-3 text-xs text-mist">
            <div className="min-w-0 truncate">
              <span className="text-ink">{displayName}</span>
              {user.email && displayName !== user.email && (
                <span className="text-stone"> · {user.email}</span>
              )}
            </div>
            <button
              type="button"
              onClick={() => signOut()}
              className="shrink-0 rounded-chip border border-line px-2 py-1 hover:border-accent hover:text-ink"
            >
              Sign out
            </button>
          </div>
        </div>
      </header>

      {accountOpen && (
        <AccountPanel
          accessToken={accessToken}
          displayName={displayName}
          email={user.email}
          onClose={() => setAccountOpen(false)}
        />
      )}

      <main className="mx-auto flex w-full max-w-measure flex-1 flex-col gap-10 px-5 py-10 sm:px-6 sm:py-14">
        <section className="flex flex-wrap items-center gap-2 text-xs">
          <button
            type="button"
            onClick={() => setMode("ask")}
            className={`rounded-chip border px-2.5 py-1 ${
              mode === "ask"
                ? "border-accent text-ink"
                : "border-line text-mist"
            }`}
          >
            Ask
          </button>
          <button
            type="button"
            onClick={() => setMode("agent")}
            className={`rounded-chip border px-2.5 py-1 ${
              mode === "agent"
                ? "border-accent text-ink"
                : "border-line text-mist"
            }`}
          >
            Agent
          </button>
          <button
            type="button"
            onClick={onAddWatch}
            className="rounded-chip border border-line px-2.5 py-1 text-mist hover:border-accent hover:text-ink"
          >
            Watch {ticker}
          </button>
          {watchlist.length > 0 && (
            <span className="font-mono text-stone">
              {watchlist.join(" · ")}
            </span>
          )}
        </section>

        {error && (
          <div
            role="alert"
            className="animate-fade-up rounded-search border border-line bg-surface px-4 py-3 text-sm text-ink"
          >
            {error}
            {error.toLowerCase().includes("limit") && (
              <button
                type="button"
                className="ml-2 underline underline-offset-2"
                onClick={() => setAccountOpen(true)}
              >
                View plans
              </button>
            )}
          </div>
        )}

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
              placeholder={
                mode === "agent"
                  ? "Ask the research agent…"
                  : "Ask about a filing…"
              }
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
                    <span>{mode === "agent" ? "Running" : "Asking"}</span>
                  </>
                ) : mode === "agent" ? (
                  "Run"
                ) : (
                  "Ask"
                )}
              </button>
            </div>
          </div>
        </section>

        {prior && (
          <section
            aria-label="Previous answer"
            className="animate-fade-up space-y-2 border-b border-line/70 pb-8"
          >
            <h2 className="footnote-label">Earlier</h2>
            <p className="text-sm text-mist">{prior.q}</p>
            <p className="whitespace-pre-wrap text-sm leading-relaxed text-stone line-clamp-6">
              {prior.a}
            </p>
          </section>
        )}

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
              busy && answer && mode === "ask" ? "typing-cursor" : "",
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
