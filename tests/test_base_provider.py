"""Tests for providers/base.py: validate_params, build_output_path, GenerationResult."""

import pytest

from providers.base import BaseImageProvider, GenerationResult, ImageOutcome


class _FakeProvider(BaseImageProvider):
    SUPPORTED_ASPECT_RATIOS = ("1:1", "16:9")

    def generate(self, *args, **kwargs):
        raise NotImplementedError


def test_validate_params_accepts_supported_values():
    provider = _FakeProvider(model_name="fake-model")
    provider.validate_params(aspect_ratio="1:1", resolution="2K")  # should not raise


def test_validate_params_rejects_unsupported_resolution():
    provider = _FakeProvider(model_name="fake-model")
    with pytest.raises(ValueError):
        provider.validate_params(aspect_ratio="1:1", resolution="8K")


def test_validate_params_rejects_unsupported_aspect_ratio():
    provider = _FakeProvider(model_name="fake-model")
    with pytest.raises(ValueError):
        provider.validate_params(aspect_ratio="2:1", resolution="2K")


def test_build_output_path_increments_suffix_on_collision(tmp_path):
    provider = _FakeProvider(model_name="fake-model")
    base = tmp_path / "campaign_20260101-0000_1.png"
    base.write_bytes(b"x")

    result = provider.build_output_path("campaign", "20260101-0000", 1, tmp_path)

    assert result == tmp_path / "campaign_20260101-0000_1_1.png"


def test_generation_result_status_success_when_all_succeed():
    result = GenerationResult(outcomes=[ImageOutcome(success=True), ImageOutcome(success=True)])
    assert result.status == "success"


def test_generation_result_status_partial_when_some_fail():
    result = GenerationResult(outcomes=[ImageOutcome(success=True), ImageOutcome(success=False, error="boom")])
    assert result.status == "partial"
    assert result.errors == ["boom"]


def test_generation_result_status_failed_when_all_fail():
    result = GenerationResult(outcomes=[ImageOutcome(success=False, error="boom")])
    assert result.status == "failed"
    assert result.output_paths == []
