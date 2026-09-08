import asyncio
from app.ingest.pipeline import ingest_company
from app.ingest.universe import DEFAULT_UNIVERSE


async def main():
    for t in DEFAULT_UNIVERSE:
        print("Ingesting", t)
        await ingest_company(t)


if __name__ == "__main__":
    asyncio.run(main())
