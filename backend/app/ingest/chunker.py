import re
import tiktoken
from bs4 import BeautifulSoup

_enc = tiktoken.get_encoding("cl100k_base")
def ntok(s: str) -> int:
    return len(_enc.encode(s))

def _table_to_markdown(table) -> str:
    rows = []
    for tr in table.find_all("tr"):
        cells = [c.get_text(strip=True) for c in tr.find_all(["td", "th"])]
        if any(cells):
            rows.append("| " + " | ".join(cells) + " |")
    if rows:
        ncol = rows[0].count("|") - 1
        rows.insert(1, "| " + " | ".join("---" * ncol) + " |")
    return "\n".join(rows)

def _parse_blocks(html: str):
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style"]):
        t.decompose()
    for t in soup.find_all(re.compile(r"^ix:")):
        t.unwrap()
    section = "Preamble"
    for el in (soup.body or soup).find_all(["h1","h2","h3","p","table"]):
        txt = el.get_text(" ", strip=True)
        if el.name in ("h1", "h2", "h3"):
            m = re.match(r"(Item\s+\d+[A-Z]?\.?\s*.*)", txt, re.I)
            section = m.group(1).strip() if m else (txt or section)
            continue
        if el.name == "table":
            md = _table_to_markdown(el)
            if md.strip():
                yield ("table", md, section)
        elif txt:
            yield ("text", txt, section)

def chunk_filing(html: str, target: int = 512, overlap: int = 80) -> list[dict]:
    """targer-token chunks. Tables are atomic. Section changes force a flush so
    every chunk carries an accurate section label for citations."""
    chunks, buf, buf_sec, buf_tok = [], [], None, 0
    def flush():
        nonlocal buf, buf_tok
        if buf:
            chunks.append({
                "section": buf_sec,
                "text": "\n\n".join(b[1] for b in buf),
                "tokens": buf_tok,
                "is_table": all(b[0] == "table" for b in buf),
            })
        buf, buf_tok = [], 0
    for kind, text, section in _parse_blocks(html):
        t = ntok(text)
        if buf_sec is None:
            buf_sec = section
        section_changed = section != buf_sec
        overflow = buf_tok + t > target
        if section_changed or overflow:
            carry = None
            if (buf and buf[-1][0] == "text" and overflow and not section_changed
                and ntok(buf[-1][1]) <= overlap * 2):
                carry = buf[-1]
            flush()
            buf_sec = section
            if carry:
                buf.append(carry); buf_tok += ntok(carry[1])
        if kind == "table" and t > target:
            flush(); chunks.append({"section": section, "text": text,
                                    "tokens": t, "is_table": True})
            buf_sec = None
            continue
        buf.append((kind, text)); buf_tok += t
    flush()
    return chunks