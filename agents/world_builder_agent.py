import re
from pathlib import Path
from .base_agent import BaseAgent, INITIAL_DRAFT_MODEL

DEFAULT_BLACKLIST_PATH = Path(__file__).parent.parent / "trope_blacklist.md"
WORLD_BUILDER_MAX_TOKENS = 16000  # bible is intentionally dense; keep both blocks intact

SYSTEM_PROMPT_TEMPLATE = """\
You are a world-builder. You are given a story idea and a narrative plan set in a world \
that is NOT contemporary Earth. Your job is to precompute that world so a writer never has \
to invent it mid-sentence. Produce two artifacts, in this exact order and with these exact \
delimiters, and NOTHING else:

=== CANON SHEET ===
A short, authoritative list of the world's load-bearing rules: physics that differ from \
Earth, biology, technology level, social structure, what characters can and cannot do. \
Each rule one concrete, usable line (e.g. "Noon light is deep red; shadows point three \
ways from the three suns"). This block is threaded into every later stage; keep it tight.

=== WORLD BIBLE ===
A dense bank of CONCRETE SENSORY detail this world affords: textures, smells, sounds, \
temperatures, weights, the feel of daily objects, what bodies do here. Not rules — raw \
specific material the writer draws from so prose stays grounded instead of abstract. Anchor \
every entry to a human-legible sensation, then distort it; do not describe things as merely \
"strange" or "otherworldly".

Avoid the clichés in this blacklist:
---
{blacklist}
---

Emit the CANON SHEET block first so it is never at risk of truncation. Use the two \
delimiter lines verbatim.\
"""

CANON_ONLY_SYSTEM_PROMPT_TEMPLATE = """\
You are a world-builder. You are given a story idea and a narrative plan set in a SECONDARY \
world: the sensory ground is ordinary human experience — rooms are rooms, bread tastes like \
bread — but a bounded set of departures sits on top of it. Your job is to state that \
departure set so precisely that no later agent has to guess at it. Produce ONE artifact, \
with this exact delimiter, and NOTHING else:

=== CANON SHEET ===
A short, authoritative list of the world's load-bearing rules: what is possible here that \
is not possible for the reader, what it costs, who can do it, and where the limits sit. \
Each rule one concrete, usable line (e.g. "A healed board holds for a season, then fails; \
nobody heals the same board twice"). Include the social and economic consequences of the \
departures — those are where a secondary world's stories actually live — and any rule the \
plan relies on without stating.

Do NOT produce a world bible and do NOT write a sensory detail bank. The writer knows what \
this world's air and furniture feel like; supplying that material would only push the prose \
toward describing what needs no describing. Rules only.

Avoid the clichés in this blacklist:
---
{blacklist}
---

Use the delimiter line verbatim.\
"""


class WorldBuilderAgent(BaseAgent):
    """Precomputes an out-of-distribution world into a canon sheet + world-bible."""

    def __init__(self, model: str = INITIAL_DRAFT_MODEL):
        super().__init__(model=model)

    def run(self, idea: str, plan: str, world_rules: str = "",
            blacklist_path=None, canon_only: bool = False) -> dict:
        """Precompute the world. ``canon_only`` returns rules without a sensory bible —
        the SECONDARY tier, where the reader already knows what the rooms feel like."""
        path = Path(blacklist_path) if blacklist_path else DEFAULT_BLACKLIST_PATH
        blacklist = path.read_text(encoding="utf-8")
        template = (CANON_ONLY_SYSTEM_PROMPT_TEMPLATE if canon_only
                    else SYSTEM_PROMPT_TEMPLATE)
        system_prompt = template.format(blacklist=blacklist)
        user_prompt = (
            f"IDEA:\n{idea}\n\n"
            f"NARRATIVE PLAN (already contains any image-derived WORLD DEDUCTION):\n{plan}\n\n"
            f"WORLD RULES (text):\n{world_rules or '(none)'}\n\n"
            + ("Produce the CANON SHEET." if canon_only
               else "Produce the CANON SHEET and WORLD BIBLE.")
        )
        output = self._call_claude(system_prompt, user_prompt,
                                   model=self.model, max_tokens=WORLD_BUILDER_MAX_TOKENS)
        canon_sheet, world_bible = self._split(output)
        return {"agent": "WorldBuilderAgent", "output": output,
                "canon_sheet": canon_sheet, "world_bible": world_bible}

    @staticmethod
    def _split(text: str) -> tuple:
        """Split on the two headers. Returns (canon_sheet, world_bible)."""
        canon = re.search(
            r'===\s*CANON SHEET\s*===\s*(.*?)(?=\s*===\s*WORLD BIBLE\s*===|\Z)',
            text, re.IGNORECASE | re.DOTALL)
        bible = re.search(
            r'===\s*WORLD BIBLE\s*===\s*(.*)$', text, re.IGNORECASE | re.DOTALL)
        return (canon.group(1).strip() if canon else text.strip(),
                bible.group(1).strip() if bible else "")
