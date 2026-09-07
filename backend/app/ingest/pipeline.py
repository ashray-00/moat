from datetime import date

import httpx
from sqlalchemy import text
from app.config import settings
from app.db import engine
from app.ingest import edgar, facts as facts_mod
from app.ingest.chunker import chunk_filing
from app.gateway.embed import embed_texts

async def ingest_company(ticker: str, forms=("10-K", "10-Q")):
    async with httpx.AsyncClient() as client:
        cik = await edgar.ticker_to_cik(client, ticker)
        subs = await edgar.get_submissions(client, cik)
        name = subs.get("name", ticker)

        async with engine.begin() as conn:
            await conn.execute(text(
                "INSERT INTO companies (cik, ticker, name) VALUES (:c, :t, :n) "
                "ON CONFLICT (cik) DO UPDATE SET ticker=:t, name=:n"),
                {"c": cik, "t": ticker.upper(), "n": name})
            
        # --- structured facts ---
        cf = await edgar.get_company_facts(client, cik)
        for tags in (facts_mod.REVENUE_TAGS, facts_mod.NET_INCOME_TAGS):
            tag, series = facts_mod.annual_series(cf, tags)
            if not tag:
                continue
            async with engine.begin() as conn:
                for r in series:
                    await conn.execute(text(
                        "INSERT INTO facts (cik, tag, fy, period_end, val, form) "
                        "VALUES (:cik, :tag, :fy, :end, :val, :form) "
                        "ON CONFLICT DO NOTHING"),
                        {"cik": cik, "tag": tag, "fy": r["fy"],
                         "end": date.fromisoformat(r["end"]),
                         "val": r["val"], "form": r["form"]})
            
        # --- prose chunks (retrieval) ---
        for form in forms:
            meta = await edgar.latest_filing_of_type(client, cik, form)
            html = (await edgar._get(client, meta["doc_url"])).text
            async with engine.begin() as conn:
                res = await conn.execute(text(
                    "INSERT INTO filings (cik, form, accession, filing_date, doc_url) "
                    "VALUES (:cik, :form, :acc, :date, :url) "
                    "ON CONFLICT (accession) DO UPDATE SET form=:form RETURNING id"),
                    {"cik": cik, "form": form, "acc": meta["accession"],
                     "date": date.fromisoformat(meta["filing_date"]),
                     "url": meta["doc_url"]})
                filing_id = res.scalar_one()

            ch = chunk_filing(html)
            vectors = await embed_texts([c["text"] for c in ch])
            async with engine.begin() as conn:
                for c, v in zip(ch, vectors):
                    await conn.execute(text(
                        "INSERT INTO chunks (filing_id, cik, ticker, section, is_table, text, tokens, embedding) "
                        "VALUES (:fid, :cik, :tk, :sec, :tbl, :txt, :tok, :emb)"),
                        {"fid": filing_id, "cik": cik, "tk": ticker.upper(),
                         "sec": c["section"], "tbl": c["is_table"],
                         "txt": c["text"], "tok": c["tokens"], "emb": str(v)})

            print(f" {ticker} {form}: stored {len(ch)} chunks")