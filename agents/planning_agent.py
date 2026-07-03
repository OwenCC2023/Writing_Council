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
- Intended prose weight: brief (a paragraph or two), standard (a full scene), or extended \
  (a major set piece). The writer should calibrate length to dramatic significance, not to \
  the amount of plan text devoted to a section.

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

=== GENERAL NOTES ===
Feedback that cannot map to a specific section (overall tone, pacing, voice).
Write NONE if nothing applies.

Rules:
- Resolve conflicts between reviewers; favour narrative integrity and the original vision.
- Be concrete: state what to change, where, and why it improves the story.
- MOVE and MERGE are applied automatically in Python — only specify them when the \
  structural change alone is the improvement needed, not a content rewrite.
- Only include sections that genuinely need revision. If a section is working, do not \
  mention it. A short revision plan focused on real problems produces better output than \
  a comprehensive one that touches everything.\
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
