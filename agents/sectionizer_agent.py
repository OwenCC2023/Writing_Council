"""Insert <<<SECTION N>>> markers into an existing draft.

The model returns only anchors — the opening words of each section — and Python
does the insertion. The prose is never re-emitted, so it cannot mutate and no
tokens are spent echoing the story back.
"""

import re

from .base_agent import BaseAgent, FEEDBACK_MODEL

_GLYPH_BREAK = re.compile(r"^\s*(\*\s*\*\s*\*|-{3,}|#{1,6})\s*$", re.MULTILINE)

SYSTEM_PROMPT = """\
You are given a narrative plan and the full text of a draft that follows it. Return the \
anchor for each planned section: the first six to ten words of the draft passage where \
that section begins, copied EXACTLY from the draft — same words, same punctuation, same \
capitalisation.

Rules:
- One anchor per line. Nothing else: no numbering, no quotes, no commentary.
- Emit exactly as many anchors as the plan has sections, in story order.
- Every anchor must appear in the draft word for word, and must be unique in it. If an \
opening phrase repeats elsewhere in the draft, extend the anchor until it is unique.
- The first anchor marks where the narrative itself begins. Skip any manuscript front \
matter — byline, contact block, word count, title page.\
"""


def insert_markers(story: str, anchors: list) -> str:
    """Return the story with <<<SECTION N>>> markers, or None if anchors don't fit.

    Rejects an anchor that is absent, appears more than once, or arrives out of
    order. Text before the first anchor is dropped.
    """
    if not anchors:
        return None
    positions = []
    for anchor in anchors:
        first = story.find(anchor)
        if first < 0 or story.find(anchor, first + 1) != -1:
            return None
        positions.append(first)
    if positions != sorted(positions) or len(set(positions)) != len(positions):
        return None

    chunks = []
    for i, start in enumerate(positions):
        end = positions[i + 1] if i + 1 < len(positions) else len(story)
        chunks.append(f"<<<SECTION {i + 1}>>>\n{story[start:end].strip()}")
    return "\n\n".join(chunks)


def _split_chunks(story: str) -> list:
    """Split on scene-break glyphs, then on blank lines if that wasn't enough."""
    chunks = [c.strip() for c in _GLYPH_BREAK.split(story) if c and c.strip()]
    chunks = [c for c in chunks if not _GLYPH_BREAK.match(c)]
    if len(chunks) > 1:
        return chunks
    return [c.strip() for c in re.split(r"\n\s*\n", story) if c.strip()]


def fallback_sectionize(story: str, count: int) -> str:
    """Group the draft into at most `count` sections without an LLM."""
    chunks = _split_chunks(story)
    count = max(1, min(count, len(chunks)))
    per = len(chunks) / count
    groups = []
    for i in range(count):
        start = int(round(i * per))
        end = int(round((i + 1) * per)) if i + 1 < count else len(chunks)
        groups.append("\n\n".join(chunks[start:end]).strip())
    return "\n\n".join(
        f"<<<SECTION {i + 1}>>>\n{g}" for i, g in enumerate(groups) if g
    )


def sectionize(story: str, anchors: list, count: int) -> str:
    """Anchor-based marking when it fits; deterministic fallback otherwise."""
    marked = insert_markers(story, anchors)
    if marked is not None:
        return marked
    print("[sectionizer] Anchors did not fit the draft — using structural fallback.")
    return fallback_sectionize(story, count)


class SectionizerAgent(BaseAgent):
    """Returns one anchor phrase per planned section."""

    def __init__(self, model: str = FEEDBACK_MODEL):
        super().__init__(model=model)

    def run(self, plan: str, story: str, section_count: int) -> list:
        user_prompt = (
            f"NARRATIVE PLAN:\n{plan}\n\n"
            f"DRAFT:\n{story}\n\n"
            f"Return exactly {section_count} anchors, one per line."
        )
        output = self._call_claude(SYSTEM_PROMPT, user_prompt)
        return [line.strip() for line in output.splitlines() if line.strip()]
