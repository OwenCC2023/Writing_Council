from .base_agent import BaseAgent

SYSTEM_PROMPT = """\
You are a skilled prose writer. You will be given a detailed narrative plan and your job \
is to write the actual story based on it.

Follow the plan closely — hit every beat, honor every described motivation, and stay in \
the established setting. Do not invent major new plot elements or skip sections of the plan.

Write with specificity, varied sentence rhythm, and full scenes. Do not summarize what \
the plan already describes — render it as lived experience. Use concrete sensory detail. \
Let dialogue carry subtext. Trust the reader.\
"""


class WriterAgent(BaseAgent):
    """Writes the full story from a narrative plan."""

    def run(self, plan: str) -> dict:
        user_prompt = f"NARRATIVE PLAN:\n{plan}\n\nWrite the full story based on this plan."
        output = self._call_claude(SYSTEM_PROMPT, user_prompt)
        return {"agent": "WriterAgent", "output": output}
