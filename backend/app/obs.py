"""Observability: Langfuse v4 client + provider env bootstrap.

Soft-fails when keys are missing so local demos work without Langfuse.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager, nullcontext
from typing import Any, Iterator

from app.config import settings

logger = logging.getLogger(__name__)


def _export_provider_env() -> None:
    """LiteLLM reads provider keys from the process environment."""
    mapping = {
        "OPENAI_API_KEY": settings.openai_api_key,
        "ANTHROPIC_API_KEY": settings.anthropic_api_key,
        "GROQ_API_KEY": settings.groq_api_key,
        "COHERE_API_KEY": settings.cohere_api_key,
    }
    for key, val in mapping.items():
        if val:
            os.environ.setdefault(key, val)


_export_provider_env()

if settings.langfuse_public_key:
    os.environ.setdefault("LANGFUSE_PUBLIC_KEY", settings.langfuse_public_key)
if settings.langfuse_secret_key:
    os.environ.setdefault("LANGFUSE_SECRET_KEY", settings.langfuse_secret_key)
if settings.langfuse_host:
    os.environ.setdefault("LANGFUSE_HOST", settings.langfuse_host)

_langfuse = None
_langfuse_tried = False


def get_langfuse():
    """Return a Langfuse client when both keys are set; otherwise None."""
    global _langfuse, _langfuse_tried
    if _langfuse_tried:
        return _langfuse
    _langfuse_tried = True
    if not (
        (settings.langfuse_public_key or "").strip()
        and (settings.langfuse_secret_key or "").strip()
    ):
        _langfuse = None
        return None
    try:
        from langfuse import get_client

        client = get_client()
        _langfuse = client
        return _langfuse
    except Exception:
        logger.exception("Langfuse client init failed")
        _langfuse = None
        return None


# Back-compat name used by older imports (may be None).
langfuse = None


def _refresh_langfuse_alias() -> None:
    global langfuse
    langfuse = get_langfuse()


_refresh_langfuse_alias()


@contextmanager
def trace_span(
    name: str,
    *,
    as_type: str = "span",
    input: Any = None,
    metadata: dict | None = None,
    user_id: str | None = None,
) -> Iterator[Any]:
    """Open a Langfuse observation, or a no-op if tracing is disabled."""
    client = get_langfuse()
    if client is None:
        yield None
        return
    meta = dict(metadata or {})
    if user_id:
        meta["user_id"] = user_id
    try:
        with client.start_as_current_observation(
            name=name,
            as_type=as_type,  # type: ignore[arg-type]
            input=input,
            metadata=meta or None,
        ) as span:
            yield span
    except Exception:
        logger.debug("langfuse span %s failed", name, exc_info=True)
        yield None


def span_update(span: Any, **kwargs: Any) -> None:
    if span is None:
        return
    try:
        span.update(**{k: v for k, v in kwargs.items() if v is not None})
    except Exception:
        logger.debug("langfuse span.update failed", exc_info=True)


def span_set_io(span: Any, *, input: Any = None, output: Any = None) -> None:
    if span is None:
        return
    try:
        if hasattr(span, "set_trace_io"):
            span.set_trace_io(input=input, output=output)
        else:
            span.update(input=input, output=output)
    except Exception:
        logger.debug("langfuse set_io failed", exc_info=True)


def flush_langfuse() -> None:
    client = get_langfuse()
    if client is None:
        return
    try:
        client.flush()
    except Exception:
        logger.debug("langfuse flush failed", exc_info=True)


# Optional decorator for non-streaming helpers (evals / scripts).
try:
    from langfuse import observe as _lf_observe

    def observe(*args, **kwargs):
        if get_langfuse() is None:
            def deco(fn):
                return fn

            if args and callable(args[0]) and not kwargs:
                return args[0]
            return deco
        return _lf_observe(*args, **kwargs)

except Exception:

    def observe(*args, **kwargs):
        def deco(fn):
            return fn

        if args and callable(args[0]) and not kwargs:
            return args[0]
        return deco


# Silence unused import warning for nullcontext re-export convenience.
_ = nullcontext
