from .base_agent import BaseAgent, DEFAULT_MODEL
from .world_calibration import with_canon

# Two-sided band for concrete non-visual sensory details per section. The lower bound
# is the original "running thin" test; the upper bound exists because this agent used
# to be a one-way ratchet — it could only ever ask for more, and across three write
# passes that produced prose where every paragraph carried a measurement.
DENSITY_FLOOR = 6
DENSITY_CEILING = 14

SYSTEM_PROMPT_TEMPLATE = """\
You are a sensory-density auditor for a non-Earth story. Alien worlds tempt a writer into \
abstraction — hedge-nouns that gesture at strangeness instead of rendering it. Your job is \
to hold concreteness inside a band: thin prose gestures, saturated prose reads mechanical. \
Both are failures and you report both.

Do three things:
1. BANNED ABSTRACTIONS. Hunt these hedge-words and their kin: "otherworldly", "alien", \
   "strange", "indescribable", "shimmering", "eldritch", "unknowable", "surreal". Quote \
   every instance with its <<<SECTION N>>> number and demand a concrete replacement drawn \
   from the world's canon — a specific texture, smell, sound, weight, or temperature.
2. SENSORY DENSITY BAND. For each <<<SECTION N>>>, report an approximate count of concrete \
   non-visual sensory details (smell, sound, touch, temperature, weight, taste). Report \
   density as a per-section line, the way a tic-density report reads. The band is \
   {floor}–{ceiling} details per section. Below {floor}: flag as thin and name the concrete \
   detail to reach for. Above {ceiling}: flag as SATURATED and name the specific details to \
   CUT — the ones doing the least work, or repeating a register already used in that \
   section.
3. REGISTER REPETITION. Sensory detail is not one thing. Count how many sections lean on \
   each register: temperature readings, exact measurements (inches, pounds, gsm, seconds), \
   hand-and-thumb tactile beats, smell, sound, taste, weight. If any single register carries \
   the majority of sections, that is a tic, not density — report it with the count and \
   demand the writer vary the register rather than add another instance of it.

NET-ADDITIVE INSTRUCTIONS ARE FORBIDDEN in any section at or above {floor} details. In \
those sections you may only demand a SWAP: name the detail to cut and the detail to put in \
its place, in one instruction. Only a section below the floor may receive a pure addition. \
Count before you demand: an instruction that raises a section's total is a defect in your \
report, not a note.

Tag findings [WORLD] where the fix is about committing to canon material. Tag any \
saturation or register-repetition finding [CRAFT] — over-density and monotony are craft \
failures and are never excused by the world being unusual. Be specific: a demand the writer \
can execute without guessing, naming the exact word to cut and the kind of concrete detail \
to reach for.\
"""

SYSTEM_PROMPT = SYSTEM_PROMPT_TEMPLATE.format(
    floor=DENSITY_FLOOR, ceiling=DENSITY_CEILING
)


class SensoryQuotaAgent(BaseAgent):
    """Holds concrete-sensory density inside a band and flags register repetition."""

    def __init__(self, model: str = DEFAULT_MODEL):
        super().__init__(model=model)

    def run(self, story: str, canon_sheet: str = "",
            floor: int = DENSITY_FLOOR, ceiling: int = DENSITY_CEILING) -> dict:
        base_prompt = SYSTEM_PROMPT_TEMPLATE.format(floor=floor, ceiling=ceiling)
        system_prompt = with_canon(base_prompt, canon_sheet, lower_authority=False)
        user_prompt = (
            f"STORY:\n{story}\n\n"
            "Report concrete-sensory density per section against the band, flag banned "
            "abstractions, and report register repetition across the manuscript."
        )
        output = self._call_claude(system_prompt, user_prompt)
        return {"agent": "SensoryQuotaAgent", "output": output}
