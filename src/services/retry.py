"""
src/services/retry.py
Small retry helper with exponential backoff for transient network errors.
"""

import functools
import logging
import time
from collections.abc import Callable
from typing import TypeVar

import requests

logger = logging.getLogger(__name__)

T = TypeVar("T")

TRANSIENT_EXCEPTIONS = (
    requests.exceptions.ConnectionError,
    requests.exceptions.Timeout,
)


def call_with_retries(
    func: Callable[..., T],
    *args,
    retries: int = 3,
    backoff: float = 0.5,
    transient: tuple = TRANSIENT_EXCEPTIONS,
    **kwargs,
) -> T:
    """
    Call func(*args, **kwargs), retrying transient failures with
    exponential backoff (backoff * 2^(attempt-1)).

    Re-raises the last transient exception once retries are exhausted.
    Non-transient exceptions propagate immediately.
    """
    for attempt in range(1, retries + 1):
        try:
            return func(*args, **kwargs)
        except transient as exc:
            if attempt >= retries:
                raise
            delay = backoff * (2 ** (attempt - 1))
            logger.warning(
                "%s failed (attempt %d/%d): %s — retrying in %.2fs",
                getattr(func, "__name__", str(func)),
                attempt, retries, exc, delay,
            )
            time.sleep(delay)
    raise RuntimeError("unreachable")  # pragma: no cover


def retryable(retries: int = 3, backoff: float = 0.5, transient: tuple = TRANSIENT_EXCEPTIONS):
    """Decorator form of call_with_retries."""
    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> T:
            return call_with_retries(
                fn, *args,
                retries=retries, backoff=backoff, transient=transient,
                **kwargs,
            )
        return wrapper
    return decorator
