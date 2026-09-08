"use client";

import { useEffect, useState } from "react";
import type { User } from "@supabase/supabase-js";
import {
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { AccountPanel } from "./AccountPanel";
import {
  AskHttpError,
  addUniverseTicker,
  agentStream,
  askStream,
  fetchBillingMe,
  fetchUniverse,
  removeUniverseTicker,
  resumeAgentStream,
  type UniverseResponse,
} from "../lib/ask";
import { getAccessToken, signOut } from "../lib/auth";
import { ThemeToggle } from "./ThemeToggle";

type ResearchWorkspaceProps = {
  accessToken: string;
  displayName: string;
  user: User;
};

type MetricSeries = {
  ticker?: string;
  metric?: string;
  unit?: string;
  series: { fiscal_year: number; value: number }[];
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
  const [universe, setUniverse] = useState<UniverseResponse | null>(null);
  const [addTicker, setAddTicker] = useState("");
  const [universeBusy, setUniverseBusy] = useState(false);
  const [prior, setPrior] = useState<{ q: string; a: string } | null>(null);
  const [lastQuestion, setLastQuestion] = useState("");
  const [accountOpen, setAccountOpen] = useState(false);
  const [toolTrail, setToolTrail] = useState<string[]>([]);
  const [series, setSeries] = useState<MetricSeries | null>(null);
  const [pendingRunId, setPendingRunId] = useState<string | null>(null);
  const [agentEnabled, setAgentEnabled] = useState(false);

  const threadId = "research";

  useEffect(() => {
    let cancelled = false;
    async function load() {
      try {
        const data = await fetchUniverse(accessToken);
        if (!cancelled) setUniverse(data);
      } catch {
        /* ignore initial load errors */
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  useEffect(() => {
    let cancelled = false;
    fetchBillingMe(accessToken)
      .then((me) => {
        if (!cancelled) {
          // Prefer API flag; if older API omits it, Free stays off / paid on.
          const on =
            typeof me.agent_enabled === "boolean"
              ? me.agent_enabled
              : me.plan !== "free";
          setAgentEnabled(on);
          if (!on) setMode("ask");
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [accessToken]);

  useEffect(() => {
    const inflight = universe?.added.some(
      (a) => a.status === "pending" || a.status === "running",
    );
    if (!inflight) return;
    let cancelled = false;
    const id = window.setInterval(() => {
      fetchUniverse(accessToken)
        .then((data) => {
          if (!cancelled) setUniverse(data);
        })
        .catch(() => {});
    }, 2500);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [accessToken, universe?.added]);

  async function consumeAgentEvents(
    events: AsyncGenerator<
      import("../lib/ask").AgentEv,
      void,
      unknown
    >,
  ) {
    for await (const ev of events) {
      if (ev.type === "tool_start") {
        setToolTrail((t) => [...t, `${ev.name}…`]);
      } else if (ev.type === "tool_result") {
        setToolTrail((t) => {
          const next = [...t];
          const last = next.length - 1;
          if (last >= 0 && next[last]!.endsWith("…")) {
            next[last] = next[last]!.replace(
              /…$/,
              ev.ok === false ? " ✕" : " ✓",
            );
          }
          return next;
        });
      } else if (ev.type === "answer") {
        setAnswer(ev.delta);
      } else if (ev.type === "sources") {
        setSources(ev.sources);
      } else if (ev.type === "series") {
        setSeries(ev.series as MetricSeries);
      } else if (ev.type === "done") {
        if (ev.answer) setAnswer(ev.answer);
        if (ev.sources?.length) setSources(ev.sources);
        if (ev.status === "needs_human_review" && ev.run_id) {
          setPendingRunId(ev.run_id);
        } else {
          setPendingRunId(null);
        }
        if (ev.grounding_ok === false) {
          setError("Draft used tools but has no [cite:…] markers.");
        }
      } else if (ev.type === "warning") {
        setError(ev.message);
      } else if (ev.type === "error") {
        setError(ev.message);
      }
    }
  }

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
    setSeries(null);
    setToolTrail([]);
    setPendingRunId(null);
    setError(null);
    setBusy(true);
    try {
      if (mode === "agent") {
        if (!agentEnabled) {
          setError("Agent is not included on Free. Upgrade to Pro or use Ask.");
          return;
        }
        await consumeAgentEvents(agentStream(token, question, threadId));
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

  async function onHitl(action: "approve" | "rewrite") {
    if (!pendingRunId) return;
    const token = (await getAccessToken()) ?? accessToken;
    if (!token) {
      setError("Sign in required.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (action === "rewrite") {
        setToolTrail([]);
      }
      await consumeAgentEvents(
        resumeAgentStream(token, pendingRunId, action, threadId),
      );
      if (action === "approve") {
        setPendingRunId(null);
      }
    } catch (e) {
      if (e instanceof AskHttpError) setError(e.message);
      else setError(e instanceof Error ? e.message : "Resume failed");
    } finally {
      setBusy(false);
    }
  }

  async function onAddCoverage() {
    const t = addTicker.trim().toUpperCase();
    if (!t) return;
    setUniverseBusy(true);
    setError(null);
    try {
      await addUniverseTicker(accessToken, t);
      setAddTicker("");
      setUniverse(await fetchUniverse(accessToken));
    } catch (e) {
      if (e instanceof AskHttpError) {
        setError(e.message);
        if (e.status === 403 || e.message.toLowerCase().includes("limit")) {
          setAccountOpen(true);
        }
      } else {
        setError(e instanceof Error ? e.message : "Could not add ticker");
      }
    } finally {
      setUniverseBusy(false);
    }
  }

  async function onRemoveCoverage(t: string) {
    setUniverseBusy(true);
    setError(null);
    try {
      setUniverse(await removeUniverseTicker(accessToken, t));
    } catch (e) {
      if (e instanceof AskHttpError) setError(e.message);
      else setError(e instanceof Error ? e.message : "Could not remove ticker");
    } finally {
      setUniverseBusy(false);
    }
  }

  const ingestInFlight = universe?.added.some(
    (a) => a.status === "pending" || a.status === "running",
  );
  const atAddCap =
    !!universe && universe.limit > 0 && universe.used >= universe.limit;

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
            onClick={() => agentEnabled && setMode("agent")}
            disabled={!agentEnabled}
            title={
              agentEnabled
                ? undefined
                : "Agent is not included on Free — upgrade to Pro"
            }
            className={`rounded-chip border px-2.5 py-1 ${
              mode === "agent"
                ? "border-accent text-ink"
                : "border-line text-mist"
            } disabled:cursor-not-allowed disabled:opacity-45`}
          >
            Agent
          </button>
          {!agentEnabled && (
            <span className="text-stone">Agent · Pro+</span>
          )}
        </section>

        <section aria-label="Coverage" className="space-y-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 className="footnote-label">Coverage</h2>
            {universe && universe.can_modify && (
              <p className="font-mono text-xs text-stone">
                {universe.used}/{universe.limit} custom
              </p>
            )}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {(universe?.default ?? ["AAPL"]).map((t) => (
              <button
                key={`d-${t}`}
                type="button"
                onClick={() => setTicker(t)}
                className={`rounded-chip border px-2 py-1 font-mono text-xs ${
                  ticker === t
                    ? "border-accent text-ink"
                    : "border-line text-mist hover:border-accent hover:text-ink"
                }`}
              >
                {t}
              </button>
            ))}
          </div>
          {universe && universe.added.length > 0 && (
            <div className="flex flex-wrap gap-1.5">
              {universe.added.map((a) => {
                const loading =
                  a.status === "pending" || a.status === "running";
                return (
                  <span
                    key={`a-${a.ticker}`}
                    className="inline-flex items-center gap-1 rounded-chip border border-line px-2 py-1 font-mono text-xs text-mist"
                    title={a.error || a.status}
                  >
                    <button
                      type="button"
                      onClick={() => setTicker(a.ticker)}
                      className={
                        ticker === a.ticker ? "text-ink" : "hover:text-ink"
                      }
                    >
                      {a.ticker}
                      {loading
                        ? "…"
                        : a.status === "failed"
                          ? " !"
                          : ""}
                    </button>
                    {universe.can_modify && (
                      <button
                        type="button"
                        disabled={universeBusy || loading}
                        onClick={() => void onRemoveCoverage(a.ticker)}
                        className="text-stone hover:text-ink disabled:opacity-40"
                        aria-label={`Remove ${a.ticker}`}
                      >
                        ×
                      </button>
                    )}
                  </span>
                );
              })}
            </div>
          )}
          {universe?.can_modify ? (
            <div className="flex flex-wrap items-center gap-2">
              <input
                value={addTicker}
                onChange={(e) => setAddTicker(e.target.value.toUpperCase())}
                placeholder="Add ticker"
                maxLength={10}
                disabled={universeBusy || atAddCap || !!ingestInFlight}
                className="w-28 rounded-chip border border-line bg-transparent px-2 py-1 font-mono text-xs text-ink placeholder:text-stone disabled:opacity-45"
              />
              <button
                type="button"
                disabled={
                  universeBusy ||
                  atAddCap ||
                  !!ingestInFlight ||
                  !addTicker.trim()
                }
                onClick={() => void onAddCoverage()}
                className="rounded-chip border border-line px-2.5 py-1 text-xs text-mist hover:border-accent hover:text-ink disabled:opacity-45"
              >
                {ingestInFlight
                  ? "Ingesting…"
                  : universeBusy
                    ? "Adding…"
                    : "Add & ingest"}
              </button>
              {atAddCap && (
                <button
                  type="button"
                  className="text-xs text-mist underline underline-offset-2"
                  onClick={() => setAccountOpen(true)}
                >
                  Limit reached — view plans
                </button>
              )}
            </div>
          ) : (
            <p className="text-xs text-stone">
              Default coverage only.{" "}
              <button
                type="button"
                className="underline underline-offset-2 hover:text-ink"
                onClick={() => setAccountOpen(true)}
              >
                Upgrade
              </button>{" "}
              to add tickers (ingest from SEC).
            </p>
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

        {pendingRunId && (
          <section
            aria-label="Review draft"
            className="animate-fade-up rounded-search border border-line bg-surface px-4 py-3 space-y-3"
          >
            <p className="text-sm text-ink">
              This draft looks like investment advice. You can keep it or ask
              the agent to rewrite as research-only.
            </p>
            <div className="flex flex-wrap gap-2">
              <button
                type="button"
                disabled={busy}
                onClick={() => void onHitl("approve")}
                className="rounded-chip border border-accent px-3 py-1.5 text-xs text-ink hover:bg-accent/10 disabled:opacity-45"
              >
                Approve draft
              </button>
              <button
                type="button"
                disabled={busy}
                onClick={() => void onHitl("rewrite")}
                className="rounded-chip border border-line px-3 py-1.5 text-xs text-mist hover:border-accent hover:text-ink disabled:opacity-45"
              >
                Rewrite without advice
              </button>
            </div>
          </section>
        )}

        {toolTrail.length > 0 && (
          <section aria-label="Agent steps" className="animate-fade-up space-y-2">
            <h2 className="footnote-label">Working</h2>
            <ol className="space-y-1 font-mono text-xs text-mist">
              {toolTrail.map((step, i) => (
                <li key={`${step}-${i}`}>{step}</li>
              ))}
            </ol>
          </section>
        )}

        {series && series.series?.length > 0 && (
          <section aria-label="Metric series" className="animate-fade-up space-y-3">
            <h2 className="footnote-label">
              {series.ticker} · {series.metric} ({series.unit || "USD"})
            </h2>
            <div className="h-40 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart
                  data={series.series.map((row) => ({
                    fy: row.fiscal_year,
                    value: row.value,
                  }))}
                  margin={{ top: 4, right: 8, left: 0, bottom: 0 }}
                >
                  <XAxis
                    dataKey="fy"
                    tick={{ fontSize: 11 }}
                    stroke="currentColor"
                    className="text-mist"
                  />
                  <YAxis
                    tick={{ fontSize: 11 }}
                    stroke="currentColor"
                    className="text-mist"
                    width={56}
                    tickFormatter={(v: number) =>
                      v >= 1e9
                        ? `${(v / 1e9).toFixed(1)}B`
                        : v >= 1e6
                          ? `${(v / 1e6).toFixed(1)}M`
                          : String(v)
                    }
                  />
                  <Tooltip
                    contentStyle={{
                      fontSize: 12,
                      borderRadius: 8,
                      border: "1px solid var(--moat-line, #ccc)",
                    }}
                  />
                  <Line
                    type="monotone"
                    dataKey="value"
                    stroke="var(--moat-accent, #2563eb)"
                    strokeWidth={2}
                    dot={{ r: 3 }}
                    isAnimationActive={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
            <table className="w-full text-left text-sm text-ink">
              <thead>
                <tr className="border-b border-line text-xs text-mist">
                  <th className="py-1.5 font-normal">FY</th>
                  <th className="py-1.5 font-normal">Value</th>
                </tr>
              </thead>
              <tbody>
                {series.series.map((row) => (
                  <tr key={row.fiscal_year} className="border-b border-line/60">
                    <td className="py-1.5 font-mono text-xs">{row.fiscal_year}</td>
                    <td className="py-1.5 font-mono text-xs">
                      {row.value.toLocaleString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
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
