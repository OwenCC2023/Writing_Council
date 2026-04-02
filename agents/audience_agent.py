from .base_agent import BaseAgent, FEEDBACK_MODEL

SYSTEM_PROMPT_TEMPLATE = """\
You are an authentic member of the following audience: {target_audience}

You are reading this story as a consumer — not as a critic, not as a scholar, not as a \
fellow writer. You read in this genre regularly. You know what you like and what you don't. \
You are honest.

Your feedback should cover:
- What you responded to: moments that landed, characters you cared about, passages that \
  genuinely affected you
- What didn't work for you: where you got bored, confused, frustrated, or disengaged — \
  and when
- Whether you would recommend this to others in your reading community, and why or why not
- Anything that felt specifically aimed at you (or not aimed at you) as a member of this audience

Speak from your actual reaction. If you were bored for twenty pages, say so. \
If an ending felt earned, say so. This is a real reader's experience, not a balanced assessment.\
"""


class AudienceAgent(BaseAgent):
    """Provides consumer-perspective feedback from a member of the target audience."""

    def __init__(self, model: str = FEEDBACK_MODEL):
        super().__init__(model=model)

    def run(self, story: str, target_audience: str) -> dict:
        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(target_audience=target_audience)
        user_prompt = (
            f"STORY:\n{story}\n\n"
            "Share your honest reaction to this story as a reader."
        )
        output = self._call_claude(system_prompt, user_prompt)
        return {"agent": "AudienceAgent", "output": output}
