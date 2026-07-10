"""Tool infrastructure: logging hooks, error envelopes, and convenient @tool wrappers."""

from __future__ import annotations

import functools
import logging
import time
from collections.abc import Callable
from typing import Any, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def with_observability(name: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorator: add structured logging (duration / exceptions) to a tool call.

    Once the Agent system is wired to LangSmith, each tool call automatically becomes a trace span.
    In local dev without LangSmith, you at least get stdout logs.
    """

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> T:
            start = time.perf_counter()
            try:
                result = fn(*args, **kwargs)
                ms = int((time.perf_counter() - start) * 1000)
                logger.info("tool.%s ok in %dms", name, ms)
                return result
            except Exception as exc:
                ms = int((time.perf_counter() - start) * 1000)
                logger.exception("tool.%s failed after %dms: %s", name, ms, exc)
                raise

        return wrapper

    return decorator
