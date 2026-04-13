from __future__ import annotations

import time
from functools import wraps
from typing import Callable, TypeVar

T = TypeVar("T")


def retry(max_attempts: int = 3, backoff_seconds: float = 0.5) -> Callable[[Callable[..., T]], Callable[..., T]]:
    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @wraps(fn)
        def wrapper(*args, **kwargs) -> T:
            last_exc: Exception | None = None
            for attempt in range(max_attempts):
                try:
                    return fn(*args, **kwargs)
                except Exception as exc:  # noqa: BLE001
                    last_exc = exc
                    if attempt < max_attempts - 1:
                        time.sleep(backoff_seconds * (2 ** attempt))
            raise last_exc or RuntimeError("Retry failed without exception.")

        return wrapper

    return decorator
