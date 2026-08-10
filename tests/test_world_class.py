import pytest

import world_class as wc


def test_normalize_accepts_the_forms_a_caller_would_type():
    assert wc.normalize("") == wc.AUTO
    assert wc.normalize("auto") == wc.AUTO
    assert wc.normalize("  Earth ") == wc.EARTH
    assert wc.normalize("secondary") == wc.SECONDARY
    assert wc.normalize("NON-EARTH") == wc.NON_EARTH
    assert wc.normalize("non_earth") == wc.NON_EARTH


def test_normalize_rejects_an_unknown_tier():
    with pytest.raises(ValueError) as exc:
        wc.normalize("Mars")
    assert "Mars" in str(exc.value)


def test_parse_tag_falls_back_to_earth():
    """A tag the planner garbled buys nothing, rather than accidentally buying the
    whole harness."""
    assert wc.parse_tag("SECONDARY") == wc.SECONDARY
    assert wc.parse_tag("MOON") == wc.EARTH
    assert wc.parse_tag("") == wc.EARTH
    assert wc.parse_tag("auto") == wc.EARTH


def test_earth_buys_nothing():
    for predicate in (wc.wants_canon, wc.wants_bible, wc.wants_opus_writer,
                      wc.wants_strangeness_reviewers, wc.wants_smaller_sections,
                      wc.is_non_earth):
        assert predicate(wc.EARTH) is False


def test_secondary_buys_the_canon_sheet_and_nothing_else():
    """The whole point of the tier: a wands-in-Britain world gets its rules written
    down without paying for a sensory bible it does not need."""
    assert wc.wants_canon(wc.SECONDARY) is True
    assert wc.wants_bible(wc.SECONDARY) is False
    assert wc.wants_opus_writer(wc.SECONDARY) is False
    assert wc.wants_strangeness_reviewers(wc.SECONDARY) is False
    assert wc.wants_smaller_sections(wc.SECONDARY) is False
    assert wc.is_non_earth(wc.SECONDARY) is False


def test_non_earth_buys_everything():
    for predicate in (wc.wants_canon, wc.wants_bible, wc.wants_opus_writer,
                      wc.wants_strangeness_reviewers, wc.wants_smaller_sections,
                      wc.is_non_earth):
        assert predicate(wc.NON_EARTH) is True
