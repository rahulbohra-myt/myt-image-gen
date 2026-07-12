"""Tests for providers/prompt_refiner.py — mocks the google-genai client the same way tests/test_retry.py does."""

from unittest.mock import MagicMock

import pytest
from google.genai import errors as genai_errors

from providers.prompt_refiner import ClarifyingQuestion, PromptRefiner, QuestionsResponse


def _api_error(code: int) -> genai_errors.APIError:
    return genai_errors.APIError(code, {"error": {"message": "boom", "status": "ERR"}})


@pytest.fixture
def refiner(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "fake-key-for-tests")
    return PromptRefiner(model_name="fake-refiner-model")


def _fake_response(parsed=None, text=None):
    resp = MagicMock()
    resp.parsed = parsed
    resp.text = text
    return resp


def test_generate_questions_returns_parsed_list(refiner):
    parsed = QuestionsResponse(
        questions=[ClarifyingQuestion(question="What setting?", recommended_answer="A home living room")]
    )
    refiner.client.models.generate_content = MagicMock(return_value=_fake_response(parsed=parsed))

    questions = refiner.generate_questions(
        "a woman doing yoga", "test-campaign", ["cobra.png"], "brand guide text", max_questions=4
    )

    assert questions == parsed.questions


def test_generate_questions_returns_empty_when_unambiguous(refiner):
    refiner.client.models.generate_content = MagicMock(
        return_value=_fake_response(parsed=QuestionsResponse(questions=[]))
    )

    assert refiner.generate_questions("p", "c", [], "", max_questions=4) == []


def test_generate_questions_truncates_to_max_questions(refiner):
    many = [ClarifyingQuestion(question=f"Q{i}", recommended_answer=f"A{i}") for i in range(6)]
    refiner.client.models.generate_content = MagicMock(
        return_value=_fake_response(parsed=QuestionsResponse(questions=many))
    )

    result = refiner.generate_questions("p", "c", [], "", max_questions=4)

    assert len(result) == 4


def test_generate_questions_falls_back_to_manual_json_parse_when_unparsed(refiner):
    payload = QuestionsResponse(
        questions=[ClarifyingQuestion(question="What mood?", recommended_answer="Calm")]
    )
    refiner.client.models.generate_content = MagicMock(
        return_value=_fake_response(parsed=None, text=payload.model_dump_json())
    )

    result = refiner.generate_questions("p", "c", [], "", max_questions=4)

    assert result == payload.questions


def test_generate_questions_raises_after_retries_exhausted(refiner, monkeypatch):
    monkeypatch.setattr("utils.retry.time.sleep", lambda s: None)
    refiner.client.models.generate_content = MagicMock(side_effect=_api_error(429))

    with pytest.raises(genai_errors.APIError):
        refiner.generate_questions("p", "c", [], "", max_questions=4)


def test_synthesize_prompt_returns_stripped_text(refiner):
    refiner.client.models.generate_content = MagicMock(return_value=_fake_response(text="  a polished paragraph.  \n"))

    result = refiner.synthesize_prompt(
        "p", "c", [{"question": "What setting?", "recommended_answer": "home", "answer": "home"}]
    )

    assert result == "a polished paragraph."


def test_synthesize_prompt_raises_on_non_retryable_error(refiner):
    refiner.client.models.generate_content = MagicMock(side_effect=_api_error(400))

    with pytest.raises(genai_errors.APIError):
        refiner.synthesize_prompt("p", "c", [])


def test_synthesize_prompt_omits_guide_instruction_when_not_provided(refiner):
    mock = MagicMock(return_value=_fake_response(text="polished."))
    refiner.client.models.generate_content = mock

    refiner.synthesize_prompt("p", "c", [])

    sent_prompt = mock.call_args.kwargs["contents"][0]
    assert "Prompting guide:" not in sent_prompt


def test_synthesize_prompt_includes_guide_instruction_when_provided(refiner):
    mock = MagicMock(return_value=_fake_response(text="polished."))
    refiner.client.models.generate_content = mock

    refiner.synthesize_prompt("p", "c", [], prompting_guide="1. Medium — always state this first.")

    sent_prompt = mock.call_args.kwargs["contents"][0]
    assert "Prompting guide:" in sent_prompt
    assert "1. Medium — always state this first." in sent_prompt
