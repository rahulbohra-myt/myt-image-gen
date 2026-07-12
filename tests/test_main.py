"""Tests for main.py's deterministic helpers: answers-file loading, campaign/refs
resolution, and the non-interactive branch of _refine_prompt. Interactive Typer command
bodies (generate, refine_questions, list_refs, history) stay untested per existing
project precedent — only non-interactive logic is covered here."""

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import typer

from main import RefinementResult, _load_answers_file, _refine_prompt, _resolve_campaign_refs


def test_load_answers_file_passes_through_valid_answers(tmp_path):
    path = tmp_path / "answers.json"
    path.write_text(
        json.dumps([{"question": "What setting?", "recommended_answer": "home", "answer": "studio"}]),
        encoding="utf-8",
    )

    result = _load_answers_file(path)

    assert result == [{"question": "What setting?", "recommended_answer": "home", "answer": "studio"}]


def test_load_answers_file_falls_back_to_recommended_when_answer_missing(tmp_path):
    path = tmp_path / "answers.json"
    path.write_text(json.dumps([{"question": "What mood?", "recommended_answer": "calm"}]), encoding="utf-8")

    result = _load_answers_file(path)

    assert result == [{"question": "What mood?", "recommended_answer": "calm", "answer": "calm"}]


def test_load_answers_file_falls_back_to_recommended_when_answer_blank(tmp_path):
    path = tmp_path / "answers.json"
    path.write_text(
        json.dumps([{"question": "What mood?", "recommended_answer": "calm", "answer": "  "}]), encoding="utf-8"
    )

    result = _load_answers_file(path)

    assert result[0]["answer"] == "calm"


def test_load_answers_file_empty_list_returns_empty(tmp_path):
    path = tmp_path / "answers.json"
    path.write_text("[]", encoding="utf-8")

    assert _load_answers_file(path) == []


def test_load_answers_file_missing_file_raises(tmp_path):
    with pytest.raises(ValueError, match="not found"):
        _load_answers_file(tmp_path / "does-not-exist.json")


def test_load_answers_file_invalid_json_raises(tmp_path):
    path = tmp_path / "answers.json"
    path.write_text("{not json", encoding="utf-8")

    with pytest.raises(ValueError, match="not valid JSON"):
        _load_answers_file(path)


def test_load_answers_file_non_list_raises(tmp_path):
    path = tmp_path / "answers.json"
    path.write_text(json.dumps({"question": "x"}), encoding="utf-8")

    with pytest.raises(ValueError, match="JSON array"):
        _load_answers_file(path)


def test_load_answers_file_missing_required_key_raises_with_item_index(tmp_path):
    path = tmp_path / "answers.json"
    path.write_text(
        json.dumps(
            [
                {"question": "ok", "recommended_answer": "ok", "answer": "ok"},
                {"question": "missing recommended_answer"},
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="item #2"):
        _load_answers_file(path)


def test_resolve_campaign_refs_defaults_to_collect_reference_images(tmp_path):
    campaign_dir = tmp_path / "refs" / "my-campaign"
    campaign_dir.mkdir(parents=True)
    (campaign_dir / "b.png").touch()
    (campaign_dir / "a.png").touch()
    (campaign_dir / "notes.txt").touch()
    settings = {"reference_dir": str(tmp_path / "refs")}

    result = _resolve_campaign_refs("my-campaign", None, settings)

    assert [p.name for p in result] == ["a.png", "b.png"]


def test_resolve_campaign_refs_uses_explicit_refs_in_given_order(tmp_path):
    campaign_dir = tmp_path / "refs" / "my-campaign"
    campaign_dir.mkdir(parents=True)
    settings = {"reference_dir": str(tmp_path / "refs")}

    result = _resolve_campaign_refs("my-campaign", "b.png, a.png", settings)

    assert [p.name for p in result] == ["b.png", "a.png"]


def test_resolve_campaign_refs_missing_campaign_raises_exit(tmp_path):
    settings = {"reference_dir": str(tmp_path / "refs")}

    with pytest.raises(typer.Exit):
        _resolve_campaign_refs("does-not-exist", None, settings)


@pytest.fixture
def fake_refiner(monkeypatch):
    """Patch main.PromptRefiner so _refine_prompt never touches the real API."""
    instance = MagicMock()
    monkeypatch.setattr("main.PromptRefiner", MagicMock(return_value=instance))
    return instance


@pytest.fixture
def block_interactive_prompts(monkeypatch):
    """Make Prompt.ask/Confirm.ask fail loudly if the answers-file path ever calls them."""

    def _boom(*args, **kwargs):
        raise AssertionError("interactive prompt should not be called when answers_qa is supplied")

    monkeypatch.setattr("main.Prompt.ask", _boom)
    monkeypatch.setattr("main.Confirm.ask", _boom)


SETTINGS = {"refiner_model_string": "fake-refiner-model", "max_refinement_questions": 4}


def test_refine_prompt_with_answers_qa_skips_generate_questions(fake_refiner, block_interactive_prompts):
    fake_refiner.synthesize_prompt.return_value = "a polished paragraph."
    answers_qa = [{"question": "What setting?", "recommended_answer": "home", "answer": "studio"}]

    result = _refine_prompt("raw prompt", "campaign", [], SETTINGS, answers_qa=answers_qa)

    fake_refiner.generate_questions.assert_not_called()
    assert result == RefinementResult(
        final_prompt="a polished paragraph.", refined_prompt="a polished paragraph.", qa=answers_qa
    )


def test_refine_prompt_with_empty_answers_qa_uses_raw_prompt(fake_refiner, block_interactive_prompts):
    result = _refine_prompt("raw prompt", "campaign", [], SETTINGS, answers_qa=[])

    fake_refiner.generate_questions.assert_not_called()
    fake_refiner.synthesize_prompt.assert_not_called()
    assert result == RefinementResult(final_prompt="raw prompt")


def test_refine_prompt_with_answers_qa_falls_back_when_synthesis_fails(fake_refiner, block_interactive_prompts):
    fake_refiner.synthesize_prompt.side_effect = RuntimeError("boom")
    answers_qa = [{"question": "What setting?", "recommended_answer": "home", "answer": "studio"}]

    result = _refine_prompt("raw prompt", "campaign", [], SETTINGS, answers_qa=answers_qa)

    assert result == RefinementResult(final_prompt="raw prompt", qa=answers_qa)
    assert result.aborted is False
