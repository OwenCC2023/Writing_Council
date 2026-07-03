from pathlib import Path
from .base_agent import BaseAgent, FEEDBACK_MODEL

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
- Quote the specific passage(s) where it occurs — a finding without a quote will be ignored
- Cite the section number(s) where each quote appears, using the draft's <<<SECTION N>>> markers
- Briefly explain why it qualifies

Distinguish instance from pattern. Many of these constructions are legitimate craft used \
once; they become failures at density. For tic-type modes (negation-then-correction, \
rhetorical restatement, polysyndeton, "particular"), count the occurrences across the \
story and report the count — one instance of a tic is usually not worth a revision pass; \
five instances are.

End your review with a PRIORITY list: the three failure modes doing the most damage to \
this story, in order. The revision process can only address a few problems per pass — \
your ranking decides which ones get fixed.

Be thorough in reading, selective in reporting. A failure mode that appears subtly still \
counts, but if you find no instances of a particular failure mode, do not mention it. \
Prioritize accuracy over comprehensiveness — only flag what is genuinely present.\
"""


class AIFailureCheckerAgent(BaseAgent):
    """Reviews a story against the AI writing failure modes reference document."""

    def __init__(self, model: str = FEEDBACK_MODEL):
        super().__init__(model=model)

    def run(self, story: str, failure_modes_path: str | Path = None) -> dict:
        path = Path(failure_modes_path) if failure_modes_path else DEFAULT_FAILURE_MODES_PATH
        failure_modes = path.read_text(encoding="utf-8")

        system_prompt = SYSTEM_PROMPT_TEMPLATE.format(failure_modes=failure_modes)
        user_prompt = f"STORY:\n{story}\n\nIdentify all AI writing failure modes present in this story."

        output = self._call_claude(system_prompt, user_prompt)
        return {"agent": "AIFailureCheckerAgent", "output": output}
