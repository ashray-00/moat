import asyncio, httpx
from app.config import settings

BASE_DATA = "https://data.sec.gov"
BASE_WWW = "https://www.sec.gov"

class RateLimiter:
    """Token-bucker-ish limiter. We targer 8 req/s to stay under SEC's 10 req/s."""
    def __init__(self, rate_per_sec: float = 8.0):
        self._min_interval = 1.0 / rate_per_sec
        self._lock = asyncio.Lock()
        self._last = 0.0

    async def wait(self):
        async with self._lock:
            now = asyncio.get_event_loop().time()
            delay = self._min_interval - (now - self._last)
            if delay > 0:
                await asyncio.sleep(delay)
            self._last = asyncio.get_event_loop().time()

_limiter = RateLimiter(8.0)

def _headers():
    return {"User-Agent": settings.sec_user_agent, "Accept-Encoding": "gzip, deflate"}

async def _get(client: httpx.AsyncClient, url: str) -> httpx.Response:
    await _limiter.wait()
    r = await client.get(url, headers=_headers(), timeout=30.0)
    r.raise_for_status()
    return r

async def ticker_to_cik(client: httpx.AsyncClient, ticker: str) -> str:
    r = await _get(client, f"{BASE_WWW}/files/company_tickers.json")
    for row in r.json().values():
        if row["ticker"].upper() == ticker.upper():
            return str(row["cik_str"]).zfill(10)
    raise ValueError(f"ticker not found: {ticker}")

async def get_submissions(client: httpx.AsyncClient, cik10: str) -> dict:
    r = await _get(client, f"{BASE_DATA}/submissions/CIK{cik10}.json")
    return r.json()

async def get_company_facts(client: httpx.AsyncClient, cik10: str) -> dict:
    r = await _get(client, f"{BASE_DATA}/api/xbrl/companyfacts/CIK{cik10}.json")
    return r.json()

async def latest_filing_of_type(client, cik10: str, form: str = "10-K") -> dict:
    """Return meradata (accession, primary doc URL) for the most recent 10-K/10-Q/8-K."""
    subs = await get_submissions(client, cik10)
    recent = subs["filings"]["recent"]
    for i, f in enumerate(recent["form"]):
        if f == form:
            accession = recent["accessionNumber"][i].replace("-", "")
            doc = recent["primaryDocument"][i]
            cik_int = int(cik10)
            url = f"{BASE_WWW}/Archives/edgar/data/{cik_int}/{accession}/{doc}"
            return {"accession": recent["accessionNumber"][i], "form": form,
                    "filing_date": recent["filingDate"][i], "doc_url": url}
    raise ValueError(f"no {form} found for {cik10}")