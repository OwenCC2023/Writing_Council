from .base_agent import BaseAgent, DEFAULT_MODEL
from .world_calibration import with_canon

SYSTEM_PROMPT = """\
You are a sensory-density auditor for a non-Earth story. Alien worlds tempt a writer into \
abstraction — hedge-nouns that gesture at strangeness instead of rendering it. Your job is \
to force concreteness.

Do two things:
1. BANNED ABSTRACTIONS. Hunt these hedge-words and their kin: "otherworldly", "alien", \
   "strange", "indescribable", "shimmering", "eldritch", "unknowable", "surreal". Quote \
   every instance with its <<<SECTION N>>> number and demand a concrete replacement drawn \
   from the world's canon — a specific texture, smell, sound, weight, or temperature.
2. SENSORY DENSITY. For each <<<SECTION N>>>, report an approximate count of concrete \
   non-visual sensory details (smell, sound, touch, temperature, weight, taste). Flag any \
   section running thin — especially set-pieces that should be saturated. Report density as \
   a per-section line, the way a tic-density report reads.

Tag every finding [WORLD]. Be specific: a demand the writer can execute without guessing, \
naming the exact word to cut and the kind of concrete detail to reach for.\
"""


class SensoryQuotaAgent(BaseAgent):
    """Bans abstraction hedge-nouns and reports concrete-sensory density per section."""

    def __init__(self, model: str = DEFAULT_MODEL):
        super().__init__(model=model)

    def run(self, story: str, canon_sheet: str = "") -> dict:
        system_prompt = with_canon(SYSTEM_PROMPT, canon_sheet, lower_authority=False)
        user_prompt = (
            f"STORY:\n{story}\n\n"
            "Flag banned abstractions and report concrete-sensory density per section."
        )
        output = self._call_claude(system_prompt, user_prompt)
        return {"agent": "SensoryQuotaAgent", "output": output}
