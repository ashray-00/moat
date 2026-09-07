import asyncio
from app.ingest.pipeline import ingest_company

UNIVERSE = ["AAPL","MSFT","NVDA","GOOGL","AMZN","META","TSLA","AMD","INTC","JPM"]

async def main():
    for t in UNIVERSE:
        print("Ingesting", t)
        await ingest_company(t)

if __name__ == "__main__":
    asyncio.run(main())