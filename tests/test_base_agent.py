from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from agents.base_agent import (
    DEFAULT_MODEL,
    FEEDBACK_MODEL,
    INITIAL_DRAFT_MODEL,
    THINKING_HEADROOM,
    BaseAgent,
    RefusalError,
    max_tokens_for,
)


def _response(*blocks, stop_reason="end_turn", stop_details=None):
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason,
                           stop_details=stop_details, model="m")


def _text(text):
    return SimpleNamespace(type="text", text=text)


def _agent_returning(response, model=DEFAULT_MODEL):
    agent = BaseAgent(model=model)
    agent.client = MagicMock()
    stream = agent.client.beta.messages.stream
    stream.return_value.__enter__.return_value.get_final_message.return_value = response
    return agent, stream


def test_model_tiers_are_the_5_5_family():
    assert DEFAULT_MODEL == "claude-sonnet-5-5"
    assert INITIAL_DRAFT_MODEL == "claude-opus-5-5"
    assert FEEDBACK_MODEL == "claude-haiku-4-5"


def test_opus_5_5_runs_medium_effort_with_headroom_and_no_disabled_thinking():
    agent, stream = _agent_returning(_response(_text("ok")))
    assert agent._call_claude("sys", "user", model=INITIAL_DRAFT_MODEL,
                              max_tokens=16000) == "ok"
    kwargs = stream.call_args.kwargs
    assert "thinking" not in kwargs
    assert kwargs["output_config"] == {"effort": "medium"}
    assert kwargs["max_tokens"] == 16000 + THINKING_HEADROOM
    assert kwargs["betas"] == ["server-side-fallback-2026-07-01"]
    assert kwargs["extra_body"] == {"fallbacks": "default"}


def test_sonnet_5_5_runs_adaptive_at_low_effort():
    agent, stream = _agent_returning(_response(_text("ok")))
    agent._call_claude("sys", "user")
    kwargs = stream.call_args.kwargs
    assert "thinking" not in kwargs
    assert kwargs["output_config"] == {"effort": "low"}


def test_haiku_keeps_thinking_disabled_and_its_exact_budget():
    agent, stream = _agent_returning(_response(_text("ok")), model=FEEDBACK_MODEL)
    agent._call_claude("sys", "user", max_tokens=4096)
    kwargs = stream.call_args.kwargs
    assert kwargs["thinking"] == {"type": "disabled"}
    assert kwargs["max_tokens"] == 4096
    assert "output_config" not in kwargs and "betas" not in kwargs


def test_image_call_shares_the_same_request_params(tmp_path):
    img = tmp_path / "p.png"
    img.write_bytes(b"\x89PNG")
    agent, stream = _agent_returning(_response(_text("ok")))
    agent._call_claude_with_image("sys", "user", str(img), model=INITIAL_DRAFT_MODEL)
    kwargs = stream.call_args.kwargs
    assert kwargs["output_config"] == {"effort": "medium"}
    assert kwargs["messages"][0]["content"][0]["type"] == "image"


def test_leading_thinking_block_is_skipped():
    thinking = SimpleNamespace(type="thinking", thinking="")
    agent, _ = _agent_returning(_response(thinking, _text("prose")))
    assert agent._call_claude("sys", "user") == "prose"


def test_refusal_raises_a_readable_error_naming_the_category():
    agent, _ = _agent_returning(_response(
        stop_reason="refusal",
        stop_details=SimpleNamespace(category="general_harms")))
    with pytest.raises(RefusalError, match="general_harms"):
        agent._call_claude("sys", "user")


def test_returns_floor_for_a_typical_target():
    # 8,000 words * 1.4 = 11,200, below the writer's 16000 floor.
    assert max_tokens_for("8,000 words", 16000) == 16000


def test_scales_above_the_floor_for_a_long_target():
    assert max_tokens_for("20,000 words", 16000) == 28000


def test_strips_thousands_separators():
    assert max_tokens_for("15,000 words", 8192) == 21000


def test_clamps_to_the_ceiling():
    assert max_tokens_for("500,000 words", 16000) == 32000


def test_unparseable_or_missing_target_returns_the_floor():
    assert max_tokens_for("novella length", 16000) == 16000
    assert max_tokens_for("", 16000) == 16000
    assert max_tokens_for(None, 8192) == 8192


def test_malformed_numeric_input_returns_the_floor():
    """Lone comma or comma-only string match the digit pattern but leave
    no digits after stripping. These should return floor, not raise ValueError."""
    assert max_tokens_for(",", 16000) == 16000
    assert max_tokens_for(",,,", 8192) == 8192
