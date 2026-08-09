from unittest.mock import patch

from agents.sectionizer_agent import (
    SectionizerAgent, insert_markers, fallback_sectionize, sectionize,
)

_STORY = (
    "Owen Cardwell-Copenhefer\napprox. 900 words\n\n"
    "The fleet dropped out of the lane.\nLigatto watched the plot.\n\n"
    "By morning the line had bent.\nNobody called it a retreat.\n\n"
    "At Frankfurt the timing simply failed him."
)


def test_insert_markers_places_markers_and_drops_front_matter():
    out = insert_markers(_STORY, ["The fleet dropped out", "By morning the line",
                                  "At Frankfurt the timing"])
    assert out.startswith("<<<SECTION 1>>>\nThe fleet dropped out")
    assert "<<<SECTION 2>>>\nBy morning the line" in out
    assert "<<<SECTION 3>>>\nAt Frankfurt the timing" in out
    assert "Owen Cardwell-Copenhefer" not in out
    assert "approx. 900 words" not in out


def test_insert_markers_does_not_alter_the_prose():
    out = insert_markers(_STORY, ["The fleet dropped out", "At Frankfurt the timing"])
    assert "Ligatto watched the plot." in out
    assert "Nobody called it a retreat." in out


def test_insert_markers_rejects_a_missing_anchor():
    assert insert_markers(_STORY, ["The fleet dropped out", "no such text here"]) is None


def test_insert_markers_rejects_a_duplicate_anchor():
    story = "Alpha beta.\n\nAlpha beta.\n\nGamma delta."
    assert insert_markers(story, ["Alpha beta", "Gamma delta"]) is None


def test_insert_markers_rejects_out_of_order_anchors():
    assert insert_markers(_STORY, ["At Frankfurt the timing", "The fleet dropped out"]) is None


def test_fallback_sectionize_splits_on_glyph_breaks():
    story = "One.\n\n***\n\nTwo.\n\n***\n\nThree."
    out = fallback_sectionize(story, 3)
    assert out.count("<<<SECTION") == 3
    assert "One." in out and "Two." in out and "Three." in out
    assert "***" not in out


def test_fallback_sectionize_splits_on_blank_lines_when_no_glyphs():
    story = "One.\n\nTwo.\n\nThree.\n\nFour."
    out = fallback_sectionize(story, 2)
    assert out.count("<<<SECTION") == 2
    assert "Four." in out


def test_fallback_sectionize_never_emits_more_sections_than_chunks():
    out = fallback_sectionize("Only one paragraph.", 5)
    assert out.count("<<<SECTION") == 1


def test_sectionize_falls_back_when_anchors_do_not_match():
    out = sectionize(_STORY, ["nope", "still nope"], 2)
    assert out.count("<<<SECTION") == 2


def test_agent_run_returns_one_anchor_per_line():
    agent = SectionizerAgent()
    with patch.object(agent, "_call_claude",
                      return_value="The fleet dropped out\n\nBy morning the line\n"):
        anchors = agent.run(plan="p", story=_STORY, section_count=2)
    assert anchors == ["The fleet dropped out", "By morning the line"]


def test_agent_uses_the_feedback_model():
    from agents.base_agent import FEEDBACK_MODEL
    assert SectionizerAgent().model == FEEDBACK_MODEL
