"""Deterministic verification of countable story constraints.

The `constraint` parameter is free text (like `style`): the planner translates it
into writing rules and the writer obeys it on every pass. For the subset of
constraints that are mechanically checkable — an exact word count, a list of
forbidden words — this module verifies the finished story directly, because an
LLM reviewer counts words unreliably. Non-countable constraints (document-form,
second-person) are left to the EngineReviewerAgent.
"""
import re


def check_constraint(constraint: str, story: str) -> dict | None:
    """Verify countable aspects of *constraint* against *story*.

    Returns None when the constraint is empty or contains nothing mechanically
    checkable. Otherwise returns:
        {"constraint": str, "passed": bool, "checks": [ {...}, ... ]}
    where each check has a "kind", the measured values, and a "passed" bool.
    """
    if not constraint or not constraint.strip():
        return None

    text = constraint.lower()
    checks = []

    # Exact word count: "exactly 200 words" or "200 words exactly".
    m = (re.search(r'exactly\s+([\d,]+)\s+words', text)
         or re.search(r'([\d,]+)\s+words\s+exactly', text))
    if m:
        target = int(m.group(1).replace(',', ''))
        actual = len(story.split())
        checks.append({
            "kind": "word_count_exact",
            "target": target,
            "actual": actual,
            "passed": actual == target,
        })

    # Forbidden words: "forbidden words: a, b, c" / "banned words - x; y".
    fm = re.search(r'(?:forbidden|banned)\s+words?\s*[:\-]\s*(.+)', text)
    if fm:
        forbidden = [w.strip() for w in re.split(r'[,;/]|\band\b', fm.group(1)) if w.strip()]
        story_words = set(re.findall(r"[a-z']+", story.lower()))
        found = sorted(w for w in forbidden if w in story_words)
        checks.append({
            "kind": "forbidden_words",
            "forbidden": forbidden,
            "found": found,
            "passed": not found,
        })

    if not checks:
        return None
    return {
        "constraint": constraint,
        "passed": all(c["passed"] for c in checks),
        "checks": checks,
    }
