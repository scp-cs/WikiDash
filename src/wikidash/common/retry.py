"""The one retry policy used for every flaky network call."""

import logging
import time
from collections.abc import Callable
from functools import wraps
from typing import ParamSpec, TypeVar

P = ParamSpec("P")
T = TypeVar("T")

log = logging.getLogger(__name__)


def retry(
    attempts: int | None = 3,
    delay: float = 5.0,
    on: type[Exception] | tuple[type[Exception], ...] = Exception,
) -> Callable[[Callable[P, T]], Callable[P, T]]:
    """Retry the wrapped call on `on`; `attempts=None` retries forever.

    The last error is re-raised once attempts run out.
    """

    def decorator(func: Callable[P, T]) -> Callable[P, T]:
        @wraps(func)
        def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
            attempt = 0
            while True:
                attempt += 1
                try:
                    return func(*args, **kwargs)
                except on as err:
                    if attempts is not None and attempt >= attempts:
                        raise
                    log.warning("%s failed (attempt %d): %s", func.__name__, attempt, err)
                    time.sleep(delay)

        return wrapper

    return decorator
