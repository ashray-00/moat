export type Ev =
  | { type: "sources"; sources: {id:string;ticker:string;section:string}[] }
  | { type: "answer"; delta: string }
  | { type: "done" };

export async function* askStream(query: string, ticker?: string): AsyncGenerator<Ev> {
  const res = await fetch(`${process.env.NEXT_PUBLIC_API_URL}/ask`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ query, ticker }),
  });
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