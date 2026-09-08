export type Ev =
  | { type: "sources"; sources: { id: string; ticker: string; section: string }[] }
  | { type: "answer"; delta: string }
  | { type: "error"; message: string }
  | { type: "done" }
  | { type: "meta"; model?: string };

export class AskHttpError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export async function* askStream(
  query: string,
  ticker?: string,
  opts?: { token?: string | null; threadId?: string | null },
): AsyncGenerator<Ev> {
  const headers: Record<string, string> = {
    "content-type": "application/json",
  };
  if (opts?.token) headers.authorization = `Bearer ${opts.token}`;

  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/ask`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      query,
      ticker,
      thread_id: opts?.threadId || undefined,
    }),
  });

  if (!res.ok) {
    let message = `Request failed (${res.status})`;
    try {
      const body = await res.json();
      if (body?.detail) message = String(body.detail);
    } catch {
      /* ignore */
    }
    throw new AskHttpError(res.status, message);
  }

  const reader = res.body!.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const frames = buf.split("\n\n");
    buf = frames.pop() ?? "";
    for (const f of frames) {
      const line = f.replace(/^data: /, "").trim();
      if (line) yield JSON.parse(line) as Ev;
    }
  }
}

export async function fetchWatchlist(token: string): Promise<string[]> {
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/watchlist`, {
    headers: { authorization: `Bearer ${token}` },
  });
  if (!res.ok) return [];
  const data = await res.json();
  return data.tickers ?? [];
}

export type UniverseAdd = {
  ticker: string;
  status: "pending" | "running" | "ready" | "failed" | string;
  error?: string;
};

export type UniverseResponse = {
  default: string[];
  added: UniverseAdd[];
  limit: number;
  used: number;
  can_modify: boolean;
  plan: string;
  ingest_per_hour: number;
};

async function readApiError(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    if (body?.detail) return String(body.detail);
  } catch {
    /* ignore */
  }
  return fallback;
}

export async function fetchUniverse(token: string): Promise<UniverseResponse> {
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/universe`, {
    headers: { authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    throw new AskHttpError(
      res.status,
      await readApiError(res, `Universe failed (${res.status})`),
    );
  }
  return res.json();
}

export async function addUniverseTicker(
  token: string,
  ticker: string,
): Promise<{
  ticker: string;
  status: string;
  error?: string;
  started_ingest: boolean;
}> {
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/universe/tickers`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ ticker }),
  });
  if (!res.ok) {
    throw new AskHttpError(
      res.status,
      await readApiError(res, `Add ticker failed (${res.status})`),
    );
  }
  return res.json();
}

export async function removeUniverseTicker(
  token: string,
  ticker: string,
): Promise<UniverseResponse> {
  const res = await fetch(
    `${process.env.NEXT_PUBLIC_API_URL}/universe/tickers/${encodeURIComponent(ticker)}`,
    {
      method: "DELETE",
      headers: { authorization: `Bearer ${token}` },
    },
  );
  if (!res.ok) {
    throw new AskHttpError(
      res.status,
      await readApiError(res, `Remove ticker failed (${res.status})`),
    );
  }
  return res.json();
}

export type AgentEv =
  | { type: "tool_start"; name: string; args?: Record<string, unknown> }
  | { type: "tool_result"; name: string; ok?: boolean }
  | { type: "answer"; delta: string }
  | { type: "sources"; sources: { id: string; ticker: string; section: string }[] }
  | {
      type: "series";
      series: {
        ticker?: string;
        metric?: string;
        unit?: string;
        series: { fiscal_year: number; value: number }[];
      };
    }
  | {
      type: "done";
      status: string;
      answer: string;
      run_id?: string;
      grounding_ok?: boolean;
      sources?: { id: string; ticker: string; section: string }[];
      series?: {
        ticker?: string;
        metric?: string;
        unit?: string;
        series: { fiscal_year: number; value: number }[];
      };
    }
  | { type: "warning"; code?: string; message: string }
  | { type: "error"; message: string; status?: number };

export async function* agentStream(
  token: string,
  query: string,
  threadId = "research",
): AsyncGenerator<AgentEv> {
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/agent/stream`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ query, thread_id: threadId }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new AskHttpError(
      res.status,
      String(body?.detail || `Agent failed (${res.status})`),
    );
  }
  yield* readSse(res);
}

export async function* resumeAgentStream(
  token: string,
  runId: string,
  action: "approve" | "rewrite",
  threadId = "research",
): AsyncGenerator<AgentEv> {
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/agent/resume`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ run_id: runId, action, thread_id: threadId }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new AskHttpError(
      res.status,
      String(body?.detail || `Resume failed (${res.status})`),
    );
  }
  const ctype = res.headers.get("content-type") || "";
  if (ctype.includes("text/event-stream")) {
    yield* readSse(res);
    return;
  }
  const data = await res.json();
  yield {
    type: "done",
    status: data.status || "ok",
    answer: data.answer || "",
    run_id: data.run_id,
    sources: data.sources,
    series: data.series,
  };
}

async function* readSse(res: Response): AsyncGenerator<AgentEv> {
  const reader = res.body!.getReader();
  const dec = new TextDecoder();
  let buf = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const frames = buf.split("\n\n");
    buf = frames.pop() ?? "";
    for (const f of frames) {
      const line = f.replace(/^data: /, "").trim();
      if (line) yield JSON.parse(line) as AgentEv;
    }
  }
}

/** @deprecated Prefer agentStream for desk UX */
export async function runAgent(
  token: string,
  query: string,
  threadId = "research",
): Promise<{ status: string; answer: string; thread_id?: string; run_id?: string }> {
  let answer = "";
  let status = "ok";
  let runId: string | undefined;
  for await (const ev of agentStream(token, query, threadId)) {
    if (ev.type === "answer") answer = ev.delta;
    else if (ev.type === "done") {
      answer = ev.answer || answer;
      status = ev.status;
      runId = ev.run_id;
    } else if (ev.type === "error") {
      throw new AskHttpError(ev.status || 500, ev.message);
    }
  }
  return { status, answer, thread_id: threadId, run_id: runId };
}

export type BillingPlanCard = {
  id: string;
  label: string;
  monthly_asks: number;
  rpm: number;
  universe_add_limit?: number;
  ingest_per_hour?: number;
  checkout: boolean;
  checkout_ready: boolean;
  current: boolean;
};

export type BillingMe = {
  plan: string;
  label: string;
  used: number;
  limit: number;
  remaining: number;
  rpm: number;
  period_start: string;
  universe_adds_used?: number;
  universe_add_limit?: number;
  ingest_per_hour?: number;
  stripe_checkout_available: boolean;
  has_stripe_customer?: boolean;
  has_active_subscription?: boolean;
  plans: BillingPlanCard[];
};

export async function fetchBillingMe(token: string): Promise<BillingMe> {
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/billing/me`, {
    headers: { authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail || `Billing failed (${res.status})`);
  }
  return res.json();
}

export async function startCheckout(
  token: string,
  plan: "pro" | "team",
): Promise<{ url: string; plan: string }> {
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/billing/checkout`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ plan }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail || `Checkout failed (${res.status})`);
  }
  return res.json();
}

export async function openBillingPortal(
  token: string,
): Promise<{ url: string }> {
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/billing/portal`, {
    method: "POST",
    headers: { authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail || `Portal failed (${res.status})`);
  }
  return res.json();
}

export async function billingStatus(): Promise<{
  configured: boolean;
  pro_price_configured?: boolean;
  team_price_configured?: boolean;
}> {
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/billing/status`);
  if (!res.ok) return { configured: false };
  return res.json();
}
