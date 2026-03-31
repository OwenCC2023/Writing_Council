import json
from .base_agent import BaseAgent
from .character_agent import CharacterAgent

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

CHARACTER_IDENTIFICATION_SYSTEM_PROMPT = """\
You are a casting director analyzing a narrative plan. Your job is to identify all \
important, recurring characters — those who appear in multiple scenes and meaningfully \
impact the story's outcome or themes.

Do NOT include:
- Minor characters who appear in only one scene
- Unnamed background figures
- Characters mentioned but never present

For each important character, produce:
- name: their full name or title
- profile: a detailed description covering personality, background, voice, core drive, \
  and fatal flaw (3-5 sentences)
- growth_arc: how they change across the story, or empty string if they do not change

Return ONLY a valid JSON array. No explanation, no markdown. Example format:
[
  {
    "name": "Commander Yara Chen",
    "profile": "...",
    "growth_arc": "..."
  }
]\
"""


class WriterAgent(BaseAgent):
    """Writes the full story from a narrative plan, and revises drafts based on feedback.

    Automatically identifies important recurring characters from the plan and spins up
    a CharacterAgent for each. Character profiles are included as context when writing
    and revising. Access identified characters via `self.characters`.
    """

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.characters: list[CharacterAgent] = []

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

class WriterAgent(BaseAgent):
    """Writes the full story from a narrative plan, and revises drafts based on feedback."""

    def run(self, plan: str) -> dict:
        self._spin_up_characters(plan)
        user_prompt = self._build_write_prompt(plan)
        output = self._call_claude(SYSTEM_PROMPT, user_prompt)
        return {"agent": "WriterAgent", "output": output}

    def revise(self, plan: str, story: str, feedback: str) -> dict:
        char_advocacy = self._collect_advocacy(story)
        full_feedback = feedback
        if char_advocacy:
            full_feedback = f"{feedback}\n\nCHARACTER CONSISTENCY NOTES:\n{char_advocacy}"
        user_prompt = (
            f"{self._character_context_block()}"
            f"ORIGINAL PLAN:\n{plan}\n\n"
            f"CURRENT DRAFT:\n{story}\n\n"
            f"FEEDBACK TO ADDRESS:\n{full_feedback}\n\n"
        user_prompt = (
            f"ORIGINAL PLAN:\n{plan}\n\n"
            f"CURRENT DRAFT:\n{story}\n\n"
            f"FEEDBACK TO ADDRESS:\n{feedback}\n\n"
            "Produce a revised draft that addresses this feedback."
        )
        output = self._call_claude(REVISION_SYSTEM_PROMPT, user_prompt)
        return {"agent": "WriterAgent", "output": output}

    # ------------------------------------------------------------------
    # Character management
    # ------------------------------------------------------------------

    def _identify_characters(self, plan: str) -> list[dict]:
        """Ask Claude to identify important recurring characters from the plan."""
        raw = self._call_claude(CHARACTER_IDENTIFICATION_SYSTEM_PROMPT, f"NARRATIVE PLAN:\n{plan}")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Extract JSON array if Claude wrapped it in prose
            start = raw.find("[")
            end = raw.rfind("]") + 1
            if start != -1 and end > start:
                return json.loads(raw[start:end])
            return []

    def _spin_up_characters(self, plan: str) -> None:
        """Create CharacterAgent instances for each important character in the plan."""
        char_data = self._identify_characters(plan)
        self.characters = [
            CharacterAgent(
                name=c.get("name", "Unknown"),
                profile=c.get("profile", ""),
                growth_arc=c.get("growth_arc", ""),
            )
            for c in char_data
            if c.get("name") and c.get("profile")
        ]

    def _compile_character_context(self) -> str:
        """Format all character profiles as a block of text."""
        if not self.characters:
            return ""
        sections = []
        for c in self.characters:
            section = f"--- CHARACTER: {c.name} ---\n{c.profile}"
            if c.growth_arc:
                section += f"\nGrowth Arc: {c.growth_arc}"
            sections.append(section)
        return "\n\n".join(sections)

    def _character_context_block(self) -> str:
        """Return formatted character context ready to prepend to a prompt, or empty string."""
        ctx = self._compile_character_context()
        return f"CHARACTER PROFILES:\n{ctx}\n\n" if ctx else ""

    def _collect_advocacy(self, story: str) -> str:
        """Run advocate() on each CharacterAgent and compile the results."""
        if not self.characters:
            return ""
        parts = []
        for c in self.characters:
            result = c.advocate(story)
            parts.append(f"[{c.name}]\n{result['output']}")
        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # Prompt assembly
    # ------------------------------------------------------------------

    def _build_write_prompt(self, plan: str) -> str:
        return (
            f"{self._character_context_block()}"
            f"NARRATIVE PLAN:\n{plan}\n\n"
            "Write the full story based on this plan."
        )
