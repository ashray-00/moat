from app.config import settings
import os

os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)

try:
    from langfuse import get_client, observe
    langfuse = get_client()
except Exception:
    def observe(*args, **kwargs):
        def deco(fn):
            return fn
        return deco
    langfuse = None