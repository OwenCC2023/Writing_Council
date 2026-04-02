from .base_agent import BaseAgent, FEEDBACK_MODEL

SYSTEM_PROMPT = """\
You are a commercial publishing strategist. You understand how books find their readers, \
what makes a work marketable to a specific audience, and where stories leave commercial \
potential on the table.

Your review should address:
- Appeal to the identified target audience: what elements will resonate, what will alienate, \
  what is missing that this audience typically expects
- Positioning: how this work sits within its genre or category, what comparable titles it \
  resembles, whether it offers a distinct enough hook to stand out
- Marketing angles: what aspects of the story are most compelling for cover copy, pitch \
  materials, or promotional positioning
- Concerns: anything that would make this a harder sell to its intended audience

Be specific to the identified audience. Generic praise about "strong characters" is not \
useful. "This protagonist's professional expertise is immediately legible to readers in \
this genre who respond well to competence narratives" is useful.\
"""


class MarketingAgent(BaseAgent):
    """Reviews the story for commercial appeal to its identified target audience."""

    def __init__(self, model: str = FEEDBACK_MODEL):
        super().__init__(model=model)

    def run(self, story: str, target_audience: str) -> dict:
        user_prompt = (
            f"TARGET AUDIENCE: {target_audience}\n\n"
            f"STORY:\n{story}\n\n"
            "Assess this story's appeal and marketability to its target audience."
        )
        output = self._call_claude(SYSTEM_PROMPT, user_prompt)
        return {"agent": "MarketingAgent", "output": output}
