"""Tests for the shared retry/backoff wrapper in utils/retry.py."""

from unittest.mock import MagicMock

import pytest
from google.genai import errors as genai_errors
from rich.console import Console

from utils.retry import RETRY_DELAYS, call_with_retry, is_retryable


def _api_error(code: int) -> genai_errors.APIError:
    return genai_errors.APIError(code, {"error": {"message": "boom", "status": "ERR"}})


def test_is_retryable_true_for_429():
    assert is_retryable(_api_error(429)) is True


def test_is_retryable_true_for_5xx():
    assert is_retryable(_api_error(503)) is True


def test_is_retryable_false_for_400():
    assert is_retryable(_api_error(400)) is False


def test_is_retryable_true_for_timeout_like_exception():
    class RequestTimeout(Exception):
        pass

    assert is_retryable(RequestTimeout()) is True


def test_call_with_retry_succeeds_after_transient_errors(monkeypatch):
    sleeps: list[int] = []
    monkeypatch.setattr("utils.retry.time.sleep", lambda s: sleeps.append(s))

    call_count = {"n": 0}

    def flaky():
        call_count["n"] += 1
        if call_count["n"] < 3:
            raise _api_error(429)
        return "ok"

    result = call_with_retry(flaky, console=Console())

    assert result == "ok"
    assert call_count["n"] == 3
    assert sleeps == [RETRY_DELAYS[0], RETRY_DELAYS[1]]


def test_call_with_retry_raises_immediately_on_non_retryable_error(monkeypatch):
    sleeps: list[int] = []
    monkeypatch.setattr("utils.retry.time.sleep", lambda s: sleeps.append(s))
    fn = MagicMock(side_effect=_api_error(400))

    with pytest.raises(genai_errors.APIError):
        call_with_retry(fn, console=Console())

    assert sleeps == []
    assert fn.call_count == 1


def test_call_with_retry_gives_up_after_max_retries(monkeypatch):
    monkeypatch.setattr("utils.retry.time.sleep", lambda s: None)
    fn = MagicMock(side_effect=_api_error(429))

    with pytest.raises(genai_errors.APIError):
        call_with_retry(fn, console=Console())

    assert fn.call_count == len(RETRY_DELAYS) + 1
