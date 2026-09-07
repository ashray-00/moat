"""Batched embeddings via the gateway. Swap embed_model to a local
sentence-transformer model for $0 cost.
"""

import litellm
from app.config import settings

async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    resp = await litellm.aembedding(model=settings.embed_model, input=texts)
    return [d["embedding"] for d in resp["data"]]