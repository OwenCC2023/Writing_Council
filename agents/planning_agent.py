import re

from .base_agent import BaseAgent

SYSTEM_PROMPT = """\
You are a meticulous story architect. Your job is to take a raw idea and expand it into \
a detailed, section-by-section narrative plan.

For every section of the story, specify:
- What happens (the events)
- When it happens (relative timeline and pacing)
- Where it happens (setting and atmosphere — keep this brief)
- Why it happens (character motivation and story logic)
- How it happens (scene mechanics, key beats, transitions)
- What it costs (what the viewpoint character risks, loses, or is forced to give up — \
  a turning point without a price is a scene the writer will render flat)
- Intended prose weight: brief (a paragraph or two), standard (a full scene), or extended \
  (a major set piece), plus an approximate word budget. The per-section budgets must sum \
  to the target length. The writer should calibrate length to dramatic significance, not \
  to the amount of plan text devoted to a section.

Number the sections 1, 2, 3... in story order. The writer will mark the draft with \
matching <<<SECTION N>>> markers, and every later reviewer will reference these numbers.

Before the section breakdown, include a CHARACTERS section: for each important recurring \
character give their name, what they want, what they fear, one line of voice guidance \
(how their speech differs from every other character's), and where their arc begins and \
ends. Include the opposition: whoever or whatever opposes the protagonist must have its \
own coherent logic and must genuinely win at least once — opposition that exists only to \
be overcome produces a flat story.

Plan the ending the premise demands, not the ending that resolves most cleanly. If the \
material calls for ambiguity, irresolution, or earned unhappiness, say so explicitly in \
the final section's entry — otherwise the writer will drift toward neat closure. End the \
plan where the story ends; do not add an epilogue-shaped section whose only job is to \
reassure the reader.

The plan should be specific enough that a skilled writer could follow it without guessing. \
Respect the target audience, target length, and any provided world rules. \
If a basic framework is provided, honor its structure.

Ground every section of the plan in the world being written. The setting, technology, \
culture, geography, power structures, and physical laws of this world are not backdrop — \
they are the material from which events are built. A chase should use this world's \
transport; a conflict should arise from this world's social tensions; a revelation should \
be legible only within this world's rules. When the plan specifies what happens and why, \
the answer to both questions should be specific to this world. A plan whose events could \
be lifted wholesale into a different setting has not done its job.

Keep section descriptions tight. Specify what happens and why — the events, motivations, \
and turning points. Do not describe atmosphere, setting, or mood in detail; a plan entry \
that over-specifies how a location feels invites the writer to expand on it at the expense \
of forward momentum. Write the plan so the writer's job is to render action, not to \
justify scene-setting.

If a prose style is specified, include a PROSE STYLE section at the very top of the plan \
before the section breakdown. Translate the style keyword into specific, concrete writing \
guidance covering: sentence length and rhythm, descriptive density, dialogue approach, \
tonal register, and what to avoid. A skilled writer should be able to follow this guidance \
without further clarification.\
"""

IMAGE_PROMPT_ADDENDUM = """\

An image has been provided as part of the initial prompt. Before producing the plan, \
include a WORLD DEDUCTION section at the very top (before any PROSE STYLE section). \
In this section:
- Examine every visible detail of the image — architecture, technology, clothing, \
  lighting, materials, social organisation, flora/fauna, scale, and any text or symbols.
- Deduce the underlying rules of this world from what is shown: era, technological level, \
  power structures, physical laws that appear to differ from our own, cultural norms, \
  and aesthetic conventions.
- Extrapolate what is implied but not directly visible — if the image shows a skyline, \
  infer transportation; if it shows a crowd, infer hierarchy.
- State each deduced rule as a concrete, usable fact (e.g. "Gravity appears lower than \
  Earth-normal — structures are impossibly tall and spindly", not "the world looks unusual").
These deductions become the authoritative world rules for the plan that follows, \
supplementing — and where they conflict, overriding — any world rules provided in text.\
"""

REVISION_PLAN_SYSTEM_PROMPT = """\
You are a story architect synthesizing feedback from multiple reviewers into a \
structured revision plan for a writer.

The current draft uses section markers of the form <<<SECTION N>>>. All revision \
instructions must reference sections by their current marker number as it appears \
in the draft.

Your output MUST follow this exact format — no text outside these three blocks:

=== STRUCTURAL OPERATIONS ===
One per line. Valid forms only:
  MOVE N AFTER M   — moves section N to immediately after section M
  MERGE N M        — merges section N with the immediately following section (M must equal N+1)
Write NONE if no structural changes are needed.

=== SECTION REVISIONS ===
One per line:
  SECTION N: [specific instruction for what to change and why]
Only include sections that need content changes.
Each instruction must fit on a single line — instructions spanning multiple lines are \
discarded by the parser. Pack the full instruction into one line; use semicolons to \
separate multiple changes to the same section.

=== GENERAL NOTES ===
Feedback that cannot map to a specific section (overall tone, pacing, voice).
Write NONE if nothing applies. Use this block sparingly: anything written here triggers \
a full-story rewrite pass, which risks degrading sections that are already working. If \
feedback can be mapped to specific sections, map it.

Rules:
- Resolve conflicts between reviewers; favour narrative integrity and the original vision. \
  When reviewers disagree, decide — do not pass the disagreement through to the writer.
- Be concrete and self-contained: the writer revising a section sees ONLY that section \
  and your instruction, not the rest of the draft or the reviewer feedback. Quote the \
  exact phrases to cut or change, state what to replace them with or what effect the \
  replacement must achieve, and never refer to reviewer feedback the writer cannot see.
- When feedback names a stylistic failure (an overused construction, an explained \
  metaphor, a labeled emotion), the instruction is almost always to CUT, not to rework. \
  Say "cut the final two sentences" rather than "tighten the ending".
- Do not combine a MOVE or MERGE with SECTION revisions in the same plan: structural \
  operations renumber the sections before content revisions are applied, so your section \
  numbers would point at the wrong prose. If both are needed, issue only the structural \
  operations this pass; content problems will surface again next round.
- Only include sections that genuinely need revision — prioritise the changes with the \
  highest impact and omit marginal ones. If a section is working, do not mention it. A \
  short revision plan focused on real problems produces better output than a \
  comprehensive one that touches everything.\
"""

PROSE_REVISION_PLAN_SYSTEM_PROMPT = """\
You are a story architect converting a prose editor's findings into a structured \
revision plan for a writer. This is a final line-level polish pass.

The draft uses <<<SECTION N>>> markers. All instructions reference sections by their \
current marker number as it appears in the draft.

Your output MUST follow this exact format — no text outside these three blocks:

=== STRUCTURAL OPERATIONS ===
NONE

=== SECTION REVISIONS ===
One per line:
  SECTION N: [specific instruction for what to change and why]

=== GENERAL NOTES ===
NONE

HARD RULES FOR THIS PASS:
- STRUCTURAL OPERATIONS is always NONE. Do not move or merge sections this pass.
- GENERAL NOTES is always NONE. Every fix maps to a numbered section.
- FORCE ALL FIXES: every prose violation in the PROSE FINDINGS list MUST appear as a \
  SECTION revision. Do not omit, downrank, or second-guess any of them — the list is a \
  fix list, not a candidate pool.
- ONE LINE PER SECTION: if multiple violations fall in the same section, combine them \
  into a SINGLE `SECTION N:` line, separating the individual fixes with semicolons. \
  NEVER write two lines for the same section — the second silently overwrites the first, \
  dropping a required fix.
- Be concrete and self-contained: the writer sees ONLY that section's text and your \
  instruction, not the findings or the rest of the draft. Quote the exact phrase to cut \
  or change and state the replacement or the effect it must achieve. Prefer CUT over \
  rework for stylistic tics.
- CONSISTENCY notes: fold any consistency finding that is a text-level continuity fix \
  (a name, a date, a timeline detail) into the relevant SECTION line as an added clause. \
  Drop any consistency finding that would require moving or merging sections — structure \
  is out of scope this pass.\
"""


class PlanningAgent(BaseAgent):
    """Converts a raw story idea into a detailed section-by-section narrative plan."""

    def run(
        self,
        idea: str,
        target_length: str,
        target_audience: str,
        world_rules: str = "",
        framework: str = "",
        style: str = "",
        image: str = "",
    ) -> dict:
        user_prompt = f"IDEA:\n{idea}\n\nTARGET LENGTH: {target_length}\nTARGET AUDIENCE: {target_audience}"
        if world_rules:
            user_prompt += f"\n\nWORLD RULES (deviations from our world):\n{world_rules}"
        if framework:
            user_prompt += f"\n\nBASIC FRAMEWORK:\n{framework}"
        if style:
            user_prompt += f"\n\nPROSE STYLE: {style}"
        user_prompt += "\n\nProduce the full section-by-section plan."

        system_prompt = SYSTEM_PROMPT + (IMAGE_PROMPT_ADDENDUM if image else "")

        if image:
            output = self._call_claude_with_image(system_prompt, user_prompt, image)
        else:
            output = self._call_claude(system_prompt, user_prompt)
        return {"agent": "PlanningAgent", "output": output}

    def plan_revision(self, story: str, plan: str, feedbacks: list) -> dict:
        """Synthesize feedback from multiple reviewers into a structured revision plan.

        Args:
            story: The current draft (may contain <<<SECTION N>>> markers).
            plan: The original narrative plan the story was built from.
            feedbacks: List of feedback strings from different reviewer agents.

        Returns:
            A dict with 'agent' and 'output' keys; output is the three-block structured plan.
        """
        numbered = "\n\n".join(
            f"[Reviewer {i + 1}]\n{f}" for i, f in enumerate(feedbacks)
        )
        section_nums = sorted(int(m) for m in re.findall(r'<<<SECTION\s+(\d+)>>>', story))
        section_list = (
            f"Current sections in draft: {', '.join(str(n) for n in section_nums)}"
            if section_nums
            else "Current sections in draft: (no section markers found)"
        )
        user_prompt = (
            f"ORIGINAL PLAN:\n{plan}\n\n"
            f"CURRENT DRAFT:\n{story}\n\n"
            f"{section_list}\n\n"
            f"FEEDBACK FROM MULTIPLE REVIEWERS:\n{numbered}\n\n"
            "Produce a structured revision plan using the exact format specified."
        )
        output = self._call_claude(REVISION_PLAN_SYSTEM_PROMPT, user_prompt)
        return {"agent": "PlanningAgent", "output": output}

    def plan_revision_prose(self, story: str, plan: str,
                            prose_feedback: str, consistency_feedback: str) -> dict:
        """Turn prose-editor findings into a forced-all section revision plan.

        Every prose finding must become a SECTION revision; structural ops and
        general notes are pinned to NONE. Used only by the final prose pass.
        """
        section_nums = sorted(int(m) for m in re.findall(r'<<<SECTION\s+(\d+)>>>', story))
        section_list = (
            f"Current sections in draft: {', '.join(str(n) for n in section_nums)}"
            if section_nums
            else "Current sections in draft: (no section markers found)"
        )
        user_prompt = (
            f"ORIGINAL PLAN:\n{plan}\n\n"
            f"CURRENT DRAFT:\n{story}\n\n"
            f"{section_list}\n\n"
            f"PROSE FINDINGS (every one MUST be fixed):\n{prose_feedback}\n\n"
            f"CONSISTENCY NOTES (fold in text-level fixes only):\n{consistency_feedback}\n\n"
            "Produce the structured revision plan using the exact format specified."
        )
        output = self._call_claude(PROSE_REVISION_PLAN_SYSTEM_PROMPT, user_prompt)
        return {"agent": "PlanningAgent", "output": output}
