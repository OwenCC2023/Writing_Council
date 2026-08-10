from agents.world_calibration import with_canon


def test_empty_canon_returns_base_prompt_unchanged():
    base = "You are a reviewer.\\nDo your job."
    assert with_canon(base, "") == base
    assert with_canon(base, "", lower_authority=False) == base


def test_canon_present_appends_rules_and_bucketing():
    out = with_canon("BASE", "Gravity is halved.")
    assert out.startswith("BASE")
    assert "Gravity is halved." in out
    assert "[CRAFT]" in out and "[WORLD]" in out
    assert "authority" in out.lower()


def test_peer_variant_omits_authority_lowering():
    out = with_canon("BASE", "Rule.", lower_authority=False)
    assert "[WORLD]" in out            # still buckets + judges against world
    assert "lower your authority" not in out.lower()


def test_repetition_findings_are_carved_out_of_the_world_bucket():
    """A canon-aware reviewer once excused a monotone voice as "[WORLD] — structural to
    the story". Strangeness is bucketable; repetition never is."""
    out = with_canon("BASE", "Gravity is halved.")
    assert "never repetition" in out
    assert "ALWAYS [CRAFT]" in out
    assert "not defenses" in out


def test_carve_out_present_in_both_authority_variants():
    for lowered in (True, False):
        out = with_canon("BASE", "Rule.", lower_authority=lowered)
        assert "ALWAYS [CRAFT]" in out
