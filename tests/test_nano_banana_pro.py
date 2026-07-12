"""Tests for providers/nano_banana_pro.py's delegation to the shared retry util."""

from unittest.mock import MagicMock

import pytest
from google.genai import errors as genai_errors

from providers.nano_banana_pro import NanoBananaProProvider


def _api_error(code: int) -> genai_errors.APIError:
    return genai_errors.APIError(code, {"error": {"message": "boom", "status": "ERR"}})


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-tests")
    return NanoBananaProProvider(model_name="fake-model")


def test_call_with_retry_delegates_to_shared_util(provider, monkeypatch):
    monkeypatch.setattr("utils.retry.time.sleep", lambda s: None)
    provider.client.models.generate_content = MagicMock(side_effect=[_api_error(429), "ok"])

    result = provider._call_with_retry(contents=["prompt"], config=None)

    assert result == "ok"
    assert provider.client.models.generate_content.call_count == 2
