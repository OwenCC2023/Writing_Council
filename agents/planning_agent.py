from .base_agent import BaseAgent

SYSTEM_PROMPT = """\
You are a meticulous story architect. Your job is to take a raw idea and expand it into \
a detailed, section-by-section narrative plan.

For every section of the story, specify:
- What happens (the events)
- When it happens (relative timeline and pacing)
- Where it happens (setting and atmosphere)
- Why it happens (character motivation and story logic)
- How it happens (scene mechanics, key beats, transitions)

The plan should be specific enough that a skilled writer could follow it without guessing. \
Respect the target audience, target length, and any provided world rules. \
If a basic framework is provided, honor its structure.\
"""

REVISION_PLAN_SYSTEM_PROMPT = """\
You are a story architect synthesizing feedback from multiple reviewers into a clear, \
actionable revision plan for a writer.

Your job:
1. Read each piece of feedback carefully.
2. Identify which feedback items conflict with each other or with the original plan. \
   Resolve conflicts by choosing the approach that best serves narrative integrity and \
   the original vision.
3. Merge non-conflicting feedback into a unified, prioritized list of revision actions.
4. For each action, state exactly what to change, where it occurs, and why the change \
   improves the story.

Output a numbered list of specific revision actions. Be concrete enough that a writer \
knows precisely what to do without further interpretation. Do not include vague suggestions.\
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
    ) -> dict:
        user_prompt = f"IDEA:\n{idea}\n\nTARGET LENGTH: {target_length}\nTARGET AUDIENCE: {target_audience}"
        if world_rules:
            user_prompt += f"\n\nWORLD RULES (deviations from our world):\n{world_rules}"
        if framework:
            user_prompt += f"\n\nBASIC FRAMEWORK:\n{framework}"
        user_prompt += "\n\nProduce the full section-by-section plan."

        output = self._call_claude(SYSTEM_PROMPT, user_prompt)
        return {"agent": "PlanningAgent", "output": output}

    def plan_revision(self, story: str, plan: str, feedbacks: list) -> dict:
        """Synthesize feedback from multiple reviewers into an actionable revision plan.

        Args:
            story: The current draft.
            plan: The original narrative plan the story was built from.
            feedbacks: List of feedback strings from different reviewer agents.

        Returns:
            A dict with 'agent' and 'output' keys; output is a numbered revision plan.
        """
        numbered = "\n\n".join(
            f"[Reviewer {i + 1}]\n{f}" for i, f in enumerate(feedbacks)
        )
        user_prompt = (
            f"ORIGINAL PLAN:\n{plan}\n\n"
            f"CURRENT DRAFT:\n{story}\n\n"
            f"FEEDBACK FROM MULTIPLE REVIEWERS:\n{numbered}\n\n"
            "Produce a clear, actionable revision plan for the writer."
        )
        output = self._call_claude(REVISION_PLAN_SYSTEM_PROMPT, user_prompt)
        return {"agent": "PlanningAgent", "output": output}
