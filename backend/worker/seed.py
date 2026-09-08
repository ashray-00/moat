from app.ingest.pipeline import ingest_company
from app.ingest.universe import default_universe
import asyncio


async def main():
    for t in default_universe():
        print("Ingesting", t)
        await ingest_company(t)


if __name__ == "__main__":
    asyncio.run(main())
