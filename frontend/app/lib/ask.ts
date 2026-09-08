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

export async function addWatchlistTicker(
  token: string,
  ticker: string,
): Promise<string[]> {
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/watchlist`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ ticker }),
  });
  if (!res.ok) throw new Error("Failed to update watchlist");
  const data = await res.json();
  return data.tickers ?? [];
}

export async function runAgent(
  token: string,
  query: string,
  threadId = "research",
): Promise<{ status: string; answer: string; thread_id?: string }> {
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/agent/run`, {
    method: "POST",
    headers: {
      "content-type": "application/json",
      authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ query, thread_id: threadId }),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const message = body?.detail || `Agent failed (${res.status})`;
    throw new AskHttpError(res.status, String(message));
  }
  return res.json();
}

export type BillingPlanCard = {
  id: string;
  label: string;
  monthly_asks: number;
  rpm: number;
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
  stripe_checkout_available: boolean;
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

export async function billingStatus(): Promise<{
  configured: boolean;
  pro_price_configured?: boolean;
  team_price_configured?: boolean;
}> {
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/billing/status`);
  if (!res.ok) return { configured: false };
  return res.json();
}
