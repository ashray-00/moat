"""Default covered ticker universe — shared by seed worker and universe API."""

DEFAULT_UNIVERSE: list[str] = [
    "AAPL",
    "MSFT",
    "NVDA",
    "GOOGL",
    "AMZN",
    "META",
    "TSLA",
    "AMD",
    "INTC",
    "JPM",
]


def is_default_ticker(ticker: str) -> bool:
    return ticker.strip().upper() in DEFAULT_UNIVERSE
