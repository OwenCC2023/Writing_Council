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
