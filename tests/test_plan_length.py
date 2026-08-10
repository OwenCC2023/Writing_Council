from plan_length import check_plan_length, declared_words, parse_target_words

# The shape that produced an 8,214-word draft against a 14,589-word target: a header
# line claiming the target, then sections whose budgets sum to 41% of it.
GRANGER_PLAN = """\
# THE GRANGER TRUST v2 - SECTION PLAN

Total: 14,589 words across 20 sections.

## SECTION 1
**Prose weight:** standard | **Budget: 750 words**
## SECTION 2
**Prose weight:** standard | **Budget: 650 words**
## SECTION 3
**Prose weight:** standard | **Budget: 800 words**
## SECTION 4
**Prose weight:** standard | **Budget: 700 words**
## SECTION 5
**Prose weight:** standard | **Budget: 650 words**
## SECTION 6
**Prose weight:** standard | **Budget: 800 words**
## SECTION 7
**Prose weight:** standard | **Budget: 750 words**
## SECTION 8
**Prose weight:** extended | **Budget: 950 words**
"""

# The Opus bible-revision rewrote the same plan in a different notation: no explicit
# "Budget:" lines at all, just per-half approximations.
GRANGER_PLAN_BIBLE_REVISED = """\
# THE GRANGER TRUST v3 - SECTION PLAN

Total: **14,589 words** across **20 sections.**

## SECTION 1
**ENTRY (Hermione, ~500w).** The two papers.
**MARGIN (Ron, ~250w).** The third stair.
## SECTION 2
**ENTRY (Harry, ~550w).** The memo.
**MARGIN (Harry, ~250w).** The landing.
"""


def test_parse_target_words_handles_the_forms_a_run_supplies():
    assert parse_target_words("14,589 words") == 14589
    assert parse_target_words("8000 words") == 8000
    assert parse_target_words("about 3,000 words") == 3000
    assert parse_target_words("") is None
    assert parse_target_words("novella length") is None


def test_declared_words_sums_explicit_section_budgets():
    assert declared_words(GRANGER_PLAN) == 6050


def test_declared_words_never_counts_the_total_line_as_a_budget():
    """The header line is the claim the plan contradicts; counting it would mask the bug."""
    assert declared_words(GRANGER_PLAN) < 14589


def test_declared_words_falls_back_to_half_budgets():
    """The bible revision emitted no explicit budgets, only ~Nw per half."""
    assert declared_words(GRANGER_PLAN_BIBLE_REVISED) == 1550


def test_declared_words_does_not_double_count_both_notations():
    """A plan carrying both notations describes one set of sections, not two."""
    both = GRANGER_PLAN + "\n**ENTRY (Hermione, ~500w).** restated\n"
    assert declared_words(both) == 6050


def test_check_fails_on_the_plan_that_caused_the_bug():
    result = check_plan_length(GRANGER_PLAN, "14,589 words")
    assert result["passed"] is False
    assert result["declared"] == 6050
    assert result["target"] == 14589
    assert round(result["ratio"], 2) == 0.41
    assert result["sections"] == 8


def test_check_passes_a_plan_whose_budgets_add_up():
    plan = "Total: 2,000 words\n**Budget: 1,000 words**\n**Budget: 1,000 words**\n"
    result = check_plan_length(plan, "2,000 words")
    assert result["passed"] is True
    assert result["declared"] == 2000


def test_check_tolerates_a_near_miss():
    """Budgets are approximations; only a real miss should cost a re-plan."""
    plan = "**Budget: 900 words**\n**Budget: 950 words**\n"
    assert check_plan_length(plan, "2,000 words")["passed"] is True
    assert check_plan_length(plan, "2,000 words", tolerance=0.02)["passed"] is False


def test_check_is_none_when_it_cannot_judge():
    """No parseable target, or a plan with no budgets at all, means no opinion --
    an unrecognised target must behave exactly as it does today."""
    assert check_plan_length(GRANGER_PLAN, "novella length") is None
    assert check_plan_length("a plan with no budgets", "2,000 words") is None


def test_section_count_ignores_in_prose_mentions():
    """"as section 2 sets up" is not a section; only header-shaped mentions count."""
    plan = GRANGER_PLAN + "\nThe payoff lands where section 2 set it up.\n"
    assert check_plan_length(plan, "14,589 words")["sections"] == 8
