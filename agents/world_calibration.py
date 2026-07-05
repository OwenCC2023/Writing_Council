"""Shared helpers for making reviewers world-aware when a canon sheet exists.

The whole point is conditional injection: with no canon sheet the caller's prompt is
returned byte-for-byte unchanged, so EARTH runs keep today's exact prompt strings.
"""

_CANON_HEADER = """\


---
WORLD CANON (authoritative rules for THIS world — judge against this world's normal, \
not Earth's):
{canon}
---

This world is deliberately unlike Earth. Prose that reads "strange" may be correct, not a \
defect. Tag every finding you report with one of two buckets:
- [CRAFT]: a genuine craft flaw (rhythm, grammar, clarity, an actual continuity \
  contradiction, an AI tic). These get fixed.
- [WORLD]: the passage only reads odd because it commits to a canon rule. This is usually \
  authorial intent, not a bug.\
"""

_AUTHORITY_CLAUSE = """
Near world-elements, lower your authority: do not demand that intentional strangeness be \
normalized. Keep full authority on rhythm, grammar, and clarity.\
"""


def with_canon(base_prompt: str, canon_sheet: str, lower_authority: bool = True) -> str:
    """Append canon + bucketing to base_prompt, or return it unchanged if no canon."""
    if not canon_sheet:
        return base_prompt
    block = _CANON_HEADER.format(canon=canon_sheet)
    if lower_authority:
        block += _AUTHORITY_CLAUSE
    return base_prompt + block
