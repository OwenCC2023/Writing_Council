from agents.base_agent import max_tokens_for


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
