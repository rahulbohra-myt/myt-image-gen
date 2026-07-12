"""Shared exponential-backoff retry wrapper for google-genai API calls. Used by both
providers/nano_banana_pro.py (image generation) and providers/prompt_refiner.py
(clarifying questions + synthesis) — extracted here once a second call site existed,
per the project's anti-premature-abstraction convention."""

import time
from typing import Callable, TypeVar

from google.genai import errors as genai_errors
from rich.console import Console

RETRY_DELAYS: tuple[int, ...] = (2, 4, 8)  # seconds, exponential backoff
MAX_RETRIES = len(RETRY_DELAYS)

T = TypeVar("T")


def is_retryable(error: Exception) -> bool:
    """True for HTTP 429/5xx API errors or timeouts — the only errors worth retrying."""
    if isinstance(error, genai_errors.APIError):
        return error.code == 429 or (isinstance(error.code, int) and 500 <= error.code < 600)
    return "timeout" in type(error).__name__.lower()


def call_with_retry(fn: Callable[[], T], console: Console) -> T:
    """Call fn(), retrying with exponential backoff on 429/5xx/timeout errors only.

    fn takes no arguments — callers close over whatever the actual API call needs,
    e.g. `lambda: client.models.generate_content(...)`.
    """
    for attempt in range(1, MAX_RETRIES + 2):
        try:
            return fn()
        except Exception as e:
            if attempt > MAX_RETRIES or not is_retryable(e):
                raise
            delay = RETRY_DELAYS[attempt - 1]
            console.print(
                f"[yellow]API call failed, retrying in {delay}s... (attempt {attempt}/{MAX_RETRIES})[/yellow]"
            )
            time.sleep(delay)
    raise RuntimeError("unreachable")  # loop always returns or raises
