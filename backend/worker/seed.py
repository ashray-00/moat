from app.ingest.pipeline import ingest_company
from app.ingest.universe import default_universe
import argparse
import asyncio


async def main(tickers: list[str] | None):
    targets = tickers if tickers else default_universe()
    for t in targets:
        print("Ingesting", t)
        await ingest_company(t)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed SEC filings into Moat")
    parser.add_argument(
        "--tickers",
        type=str,
        default="",
        help="Comma-separated tickers (default: MOAT_DEFAULT_UNIVERSE / builtin)",
    )
    args = parser.parse_args()
    tickers = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    asyncio.run(main(tickers or None))
