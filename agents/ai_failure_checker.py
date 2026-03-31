from pathlib import Path
from .base_agent import BaseAgent

DEFAULT_FAILURE_MODES_PATH = Path(__file__).parent.parent / "ai_writing_failure_modes.md"

SYSTEM_PROMPT_TEMPLATE = """\
You are a technical reviewer specializing in AI writing failure modes. \
You have been trained on the following taxonomy of known AI writing failures:

---
{failure_modes}
---

Your job is to read the provided story and identify every failure mode present. \
For each one found:
- Name the failure mode
- Quote or describe the specific passage(s) where it occurs
- Briefly explain why it qualifies

Be thorough. A failure mode that appears subtly still counts. \
If you find no instances of a particular failure mode, do not mention it. \
Prioritize accuracy over comprehensiveness — only flag what is genuinely present.\
"""


class AIFailureCheckerAgent(BaseAgent):
    """Reviews a story against the AI writing failure modes reference document."""

    def run(self, story: str, failure_modes_path: str | Path = None) -> dict:
        path = Path(failure_modes_path) if failure_modes_path else DEFAULT_FAILURE_MODES_PATH
        failure_modes = path.read_text(encoding="utf-8")

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(failure_modes=failure_modes)
        user_prompt = f"STORY:\n{story}\n\nIdentify all AI writing failure modes present in this story."

        output = self._call_claude(system_prompt, user_prompt)
        return {"agent": "AIFailureCheckerAgent", "output": output}
