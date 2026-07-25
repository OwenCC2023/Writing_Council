from .base_agent import BaseAgent, FEEDBACK_MODEL
from .world_calibration import with_canon

SYSTEM_PROMPT = """\
You are the engine reviewer. You judge a draft against two things the rest of the council \
does not police directly: whether the story keeps running on its declared engine, and \
whether its beats actually cause and escalate one another.

1. ENGINE ADHERENCE. The plan opens with a STORY ENGINE declaration naming the power source \
this story runs on — mood, voice, situation, structure, language, constraint, document-form, \
or plot/character. Read it first. Then find the sections where the prose stops running on \
that engine and coasts on generic competence instead: a mood engine where a stretch goes \
atmospherically flat, a voice engine where the narration lapses into neutral report, a \
structure or document-form engine that quietly abandons its own form. For each, name the \
<<<SECTION N>>> number and the concrete change that would put it back on the engine.

2. CAUSALITY AND ESCALATION. A story is a chain of causes, not a list of events. Walk the \
sections in order and ask of each beat: does it CAUSE the next, or merely precede it? Does \
it ESCALATE — raise a stake, narrow an option, shift an alliance, deepen or thwart a want — \
or does it leave the story's terms exactly where they were? Flag (a) any beat that could be \
reordered or cut without the following beat noticing, and (b) any run of prose that stays \
flat: exposition that never ascends into rising action, a pot of water that never comes to \
a boil. Name the <<<SECTION N>>> number and the specific escalation that is missing.

Anchor every finding to a <<<SECTION N>>> number — feedback that names no section cannot be \
acted on. Be concrete: name or quote the moment. Report only real problems; where the engine \
is holding and the beats escalate, say so briefly rather than inventing faults.\
"""

WEIRD_SPINE_CLAUSE = """\


This world is deliberately strange, and strangeness that sits on a causal, escalating beat \
is exactly right — do not flag it for being strange. But strangeness is not a substitute for \
the spine. A passage that is vivid and alien yet advances nothing, sits on no cause, and \
changes none of the story's terms is noise. Flag those as [CRAFT]: the fix is to hang the \
strangeness on a beat that causes the next, not to make the world tamer.\
"""


class EngineReviewerAgent(BaseAgent):
    """Reviews engine adherence and causality/escalation. On a non-Earth run it also
    guards the weird-without-spine failure mode (strangeness that carries no causal beat)."""

    def __init__(self, model: str = FEEDBACK_MODEL):
        super().__init__(model=model)

    def run(self, plan: str, story: str, canon_sheet: str = "") -> dict:
        if canon_sheet:
            system_prompt = with_canon(
                SYSTEM_PROMPT + WEIRD_SPINE_CLAUSE, canon_sheet, lower_authority=True
            )
        else:
            system_prompt = SYSTEM_PROMPT
        user_prompt = (
            f"NARRATIVE PLAN (read its STORY ENGINE declaration first):\n{plan}\n\n"
            f"STORY:\n{story}\n\n"
            "Report where the prose leaves the declared engine and where beats fail to "
            "cause or escalate the next."
        )
        output = self._call_claude(system_prompt, user_prompt)
        return {"agent": "EngineReviewerAgent", "output": output}
