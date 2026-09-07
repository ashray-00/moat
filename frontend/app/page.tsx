"use client";
import { useState } from "react";
import { askStream } from "./lib/ask";

export default function Home() {
  const [q, setQ] = useState("");
  const [ticker, setTicker] = useState("AAPL");
  const [answer, setAnswer] = useState("");
  const [sources, setSources] = useState<{id:string;ticker:string;section:string}[]>([]);
  const [busy, setBusy] = useState(false);

  async function ask() {
    setAnswer(""); setSources([]); setBusy(true);
    for await (const ev of askStream(q, ticker)) {
      if (ev.type === "sources") setSources(ev.sources);
      else if (ev.type === "answer") setAnswer(a => a + ev.delta);   // token-by-token
    }
    setBusy(false);
  }

  return (
    <main className="max-w-3xl mx-auto p-8 space-y-4">
      <h1 className="text-2xl font-semibold">Moat — SEC filing research</h1>
      <div className="flex gap-2">
        <input value={ticker} onChange={e=>setTicker(e.target.value.toUpperCase())}
               className="border rounded px-2 w-24" />
        <input value={q} onChange={e=>setQ(e.target.value)} placeholder="Ask about a filing…"
               className="border rounded px-3 flex-1"
               onKeyDown={e=>e.key==="Enter"&&ask()} />
        <button onClick={ask} disabled={busy}
                className="bg-black text-white rounded px-4">{busy?"…":"Ask"}</button>
      </div>
      {sources.length>0 && (
        <div className="flex flex-wrap gap-1 text-xs">
          {sources.map(s=>(
            <span key={s.id} className="bg-gray-100 rounded px-2 py-0.5">
              {s.ticker} · {s.section} · {s.id}
            </span>))}
        </div>
      )}
      <article className="whitespace-pre-wrap leading-relaxed">{answer}</article>
      <p className="text-xs text-gray-400">Research only — not investment advice.</p>
    </main>
  );
}