from .base_agent import BaseAgent

BRIEF_FIELDS = [
    "TITLE",
    "WORLD_CLASS_GUESS",
    "GENRE",
    "SETTING",
    "WORLD RULES",
    "CHARACTERS",
    "PLOT",
    "STORYLINE/STRUCTURE",
    "INTENT",
    "LENGTH",
    "SYNOPSIS",
]

SYSTEM_PROMPT = """\
You are a story analyst. You are given the full text of an existing story. Your job is to \
digest it into a brief that another agent will use to rebuild or revise it. You are not \
rewriting anything and you are not judging quality.

Ignore manuscript front matter entirely: an author byline, a contact block, a word-count \
line, a title page, a running header. Begin your reading from the first line of narrative. \
Take the title from the front matter only if the story names itself there.

Fill in every field of the brief:
- title: the story's own title, or an empty string if it has none
- world_class_guess: EARTH, SECONDARY, or NON-EARTH. Classify by sensory ground: would a \
  reader's body know this room? EARTH means contemporary or familiar-historical Earth. \
  SECONDARY means ordinary sensory ground with a bounded, listable set of departures on \
  top of it (magic in a real city, alternate history, near future). NON-EARTH means a \
  world whose sensory texture itself falls outside ordinary experience and must be built \
  before it can be written (another planet, far future, deep past). This is advisory — a \
  later agent makes the binding call.
- world_class_reason: one line of why
- genre: the genre as a publisher would shelve it
- setting: where and when, concretely
- world_rules: every way this world departs from ours — physics, technology, biology, \
  society. If it departs in no way, write NONE.
- characters: one entry for every recurring character — name, what they want, what they \
  fear or have lost, and what they do for the story
- plot: the beats in order, one entry each, stated causally: what happens and what it \
  forces next
- structure: how the story is told — point of view, tense, chronology, frame, any \
  document form
- intent: what the story is trying to do to its reader. Name the effect, not the moral.
- length: the word count you are given, verbatim
- synopsis: one paragraph that states the premise the way a pitch would\
"""

_TEXT = {"type": "string"}
_LIST = {"type": "array", "items": {"type": "string"}}

BRIEF_SCHEMA = {
    "type": "object",
    "properties": {
        "title": _TEXT,
        "world_class_guess": {"type": "string", "enum": ["EARTH", "SECONDARY", "NON-EARTH"]},
        "world_class_reason": _TEXT,
        "genre": _TEXT,
        "setting": _TEXT,
        "world_rules": _TEXT,
        "characters": _LIST,
        "plot": _LIST,
        "structure": _TEXT,
        "intent": _TEXT,
        "length": _TEXT,
        "synopsis": _TEXT,
    },
    "required": ["title", "world_class_guess", "world_class_reason", "genre", "setting",
                 "world_rules", "characters", "plot", "structure", "intent", "length",
                 "synopsis"],
    "additionalProperties": False,
}

# Brief field name -> schema key, for the fields that map one to one.
_KEY_FOR_FIELD = {
    "TITLE": "title",
    "GENRE": "genre",
    "SETTING": "setting",
    "WORLD RULES": "world_rules",
    "CHARACTERS": "characters",
    "PLOT": "plot",
    "STORYLINE/STRUCTURE": "structure",
    "INTENT": "intent",
    "LENGTH": "length",
    "SYNOPSIS": "synopsis",
}


def brief_fields(raw: dict) -> dict:
    """Turn a schema-valid response into {BRIEF_FIELDS name: text}.

    List fields (characters, plot beats) become one line per entry; the world-class
    guess and its reason are joined the way the brief has always shown them.
    """
    fields = {}
    for name, key in _KEY_FOR_FIELD.items():
        value = raw[key]
        text = "\n".join(v.strip() for v in value if v.strip()) if isinstance(value, list) \
            else value.strip()
        fields[name] = text
    reason = raw["world_class_reason"].strip()
    fields["WORLD_CLASS_GUESS"] = (f"{raw['world_class_guess']} — {reason}" if reason
                                   else raw["world_class_guess"])
    return {name: fields[name] for name in BRIEF_FIELDS}


def render_brief(fields: dict) -> str:
    """The `=== STORY BRIEF ===` block the planner reads and the UI and CLI display."""
    return "=== STORY BRIEF ===\n" + "\n".join(
        f"{name}: {fields.get(name, '')}" for name in BRIEF_FIELDS)


class IntakeAgent(BaseAgent):
    """Digests an uploaded story into a fixed-shape story brief."""

    def run(self, story: str, rewrite_notes: str = "", source_words: int = 0) -> dict:
        """Returns 'fields' ({BRIEF_FIELDS name: text}) and 'output' (the rendered
        brief, which the planner reads and the UI and CLI show)."""
        user_prompt = f"SOURCE WORD COUNT: {source_words} words\n\n"
        if rewrite_notes:
            user_prompt += (
                "WHAT THE USER WANTS FROM THE REWRITE (let this direct what you "
                f"preserve and what you flag):\n{rewrite_notes}\n\n"
            )
        user_prompt += f"STORY TEXT:\n{story}\n\nProduce the story brief."
        fields = brief_fields(self._call_claude_json(SYSTEM_PROMPT, user_prompt, BRIEF_SCHEMA))
        return {"agent": "IntakeAgent", "fields": fields, "output": render_brief(fields)}
