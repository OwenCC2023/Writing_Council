"""Deterministic check that a plan's per-section word budgets add up to the target.

The planner is told its budgets must sum to the target length. It does not always
obey: one run emitted a plan headed "Total: 14,589 words across 20 sections" and then
enumerated eight sections budgeted at 6,050 words. The writer hit that plan to within
2.6% and the story came out 44% short, because nothing between the two counted.

Same policy as ``constraints.py``: anything countable is counted in Python, not trusted
to a model.
"""

import re

# Budgets are approximations by design, so only a real miss should cost a re-plan.
DEFAULT_TOLERANCE = 0.15

# "**Prose weight:** standard | **Budget: 750 words**"
_EXPLICIT_BUDGET = re.compile(r'Budget:?\s*\**\s*([\d,]+)\s*words', re.IGNORECASE)
# "**standard | 750 words**" — the same field with the label dropped.
_WEIGHTED_BUDGET = re.compile(
    r'\b(?:brief|standard|extended)\s*\|\s*\**\s*([\d,]+)\s*words', re.IGNORECASE)
# "**ENTRY (Hermione, ~700w).**" — per-half approximations, the bible-revision notation.
_HALF_BUDGET = re.compile(r'~\s*([\d,]+)\s*w\b', re.IGNORECASE)

# Header-shaped only (markdown decoration aside), so an in-prose "as section 2 sets up"
# does not inflate the count the re-plan message reports.
_SECTION_HEADER = re.compile(r'^[\s>#*_-]*SECTION\s+(\d+)', re.IGNORECASE | re.MULTILINE)


def parse_target_words(target_length: str) -> int | None:
    """First number in a target like "14,589 words". None when there isn't one."""
    match = re.search(r'[\d,]+', target_length or "")
    if not match:
        return None
    digits = match.group().replace(",", "")
    return int(digits) if digits else None


def _sum_on_budget_lines(pattern: re.Pattern, plan: str) -> int:
    """Sum a pattern's matches, ignoring any line that states a total.

    The header line the plan contradicts ("Total: 14,589 words") matches the same
    shapes a section budget does; counting it would hide exactly the bug this exists
    to catch.
    """
    total = 0
    for line in plan.split("\n"):
        if re.search(r'\btotals?\b', line, re.IGNORECASE):
            continue
        total += sum(int(m.replace(",", "")) for m in pattern.findall(line))
    return total


def declared_words(plan: str) -> int:
    """Total words the plan's per-section budgets promise. 0 when it declares none.

    Explicit per-section budgets win; the ~Nw half-budgets are a fallback, not an
    addend. A plan that carries both notations is describing one set of sections
    twice, and summing them would double-count it.
    """
    explicit = (_sum_on_budget_lines(_EXPLICIT_BUDGET, plan)
                or _sum_on_budget_lines(_WEIGHTED_BUDGET, plan))
    return explicit or _sum_on_budget_lines(_HALF_BUDGET, plan)


def check_plan_length(plan: str, target_length: str,
                      tolerance: float = DEFAULT_TOLERANCE) -> dict | None:
    """Compare a plan's declared budgets against its target.

    Returns None when there is nothing to judge — no parseable target, or a plan that
    declares no budgets at all — so an unrecognised target behaves exactly as it did
    before this check existed. Otherwise a dict with ``declared``, ``target``,
    ``ratio``, ``sections``, and ``passed``.
    """
    target = parse_target_words(target_length)
    if not target:
        return None
    declared = declared_words(plan)
    if not declared:
        return None
    ratio = declared / target
    return {
        "declared": declared,
        "target": target,
        "ratio": ratio,
        "sections": len(set(_SECTION_HEADER.findall(plan))),
        "passed": abs(1 - ratio) <= tolerance,
    }
