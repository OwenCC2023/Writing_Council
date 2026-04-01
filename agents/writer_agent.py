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

REVISION_SYSTEM_PROMPT = """\
You are a skilled prose writer revising your own work. You will be given your original plan, \
your current draft, and specific feedback. Your job is to produce a revised draft that \
addresses the feedback while staying true to the plan.

Do not explain your changes — just write the improved story.\
"""


class WriterAgent(BaseAgent):
    """Writes the full story from a narrative plan, and revises drafts based on feedback."""

    def run(self, plan: str) -> dict:
        user_prompt = (
            f"NARRATIVE PLAN:\n{plan}\n\n"
            "Write the full story based on this plan."
        )
        output = self._call_claude(SYSTEM_PROMPT, user_prompt)
        return {"agent": "WriterAgent", "output": output}

    def revise(self, plan: str, story: str, feedback: str) -> dict:
        user_prompt = (
            f"ORIGINAL PLAN:\n{plan}\n\n"
            f"CURRENT DRAFT:\n{story}\n\n"
            f"FEEDBACK TO ADDRESS:\n{feedback}\n\n"
            "Produce a revised draft that addresses this feedback."
        )
        output = self._call_claude(REVISION_SYSTEM_PROMPT, user_prompt)
        return {"agent": "WriterAgent", "output": output}
