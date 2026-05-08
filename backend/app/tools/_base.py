"""工具基础设施：日志 hook、错误信封、便捷的 @tool 包装。"""
from __future__ import annotations

import functools
import logging
import time
from typing import Any, Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def with_observability(name: str) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """装饰器：给工具调用加结构化日志（耗时 / 异常）。

    Agent 系统接入 LangSmith 之后，每次工具调用都会自动转 trace span。
    在没有 LangSmith 的本地开发环境，至少也能看到 stdout 日志。
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
