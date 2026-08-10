import re

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

Emit EXACTLY this block and nothing else. Every field must appear, in this order, each \
starting at the beginning of a line. A field body may run over several lines; the next \
field name ends it.

=== STORY BRIEF ===
TITLE: the story's own title, or leave blank if it has none
WORLD_CLASS_GUESS: EARTH or NON-EARTH, then an em dash and one line of why. EARTH means \
contemporary or familiar-historical Earth; NON-EARTH means off-Earth, or an Earth far \
enough from present-day common experience (far future, deep past, radically altered) that \
its sensory texture falls outside ordinary experience. This is advisory — a later agent \
makes the binding call.
GENRE: the genre as a publisher would shelve it
SETTING: where and when, concretely
WORLD RULES: every way this world departs from ours — physics, technology, biology, \
society. If it departs in no way, write NONE.
CHARACTERS: one line each for every recurring character — name, what they want, what \
they fear or have lost, and what they do for the story
PLOT: the beats in order, each on its own line, stated causally: what happens and what \
it forces next
STORYLINE/STRUCTURE: how the story is told — point of view, tense, chronology, frame, \
any document form
INTENT: what the story is trying to do to its reader. Name the effect, not the moral.
LENGTH: the word count you are given, verbatim
SYNOPSIS: one paragraph that states the premise the way a pitch would\
"""


def _brief_field_pattern() -> re.Pattern:
    names = "|".join(re.escape(f) for f in BRIEF_FIELDS)
    return re.compile(rf"^({names}):\s*(.*)$")


def parse_brief(brief: str) -> dict:
    """Split a STORY BRIEF block into {field: body}. Missing fields become ''.

    A missing field is not fatal — the run continues with a blank — but it is
    warned about, so a malformed brief cannot silently swallow the upload's
    TITLE or LENGTH.
    """
    pattern = _brief_field_pattern()
    fields = {name: "" for name in BRIEF_FIELDS}
    current = None
    for line in brief.splitlines():
        match = pattern.match(line.strip())
        if match:
            current = match.group(1)
            fields[current] = match.group(2).strip()
        elif current and line.strip() and not line.strip().startswith("==="):
            fields[current] = (fields[current] + "\n" + line.strip()).strip()
    missing = [name for name in BRIEF_FIELDS if not fields[name]]
    if missing:
        print(f"[intake] WARNING: story brief is missing {len(missing)} field(s): "
              f"{', '.join(missing)}. They stay blank for this run.")
    return fields


class IntakeAgent(BaseAgent):
    """Digests an uploaded story into a fixed-shape STORY BRIEF block."""

    def run(self, story: str, rewrite_notes: str = "", source_words: int = 0) -> dict:
        user_prompt = f"SOURCE WORD COUNT: {source_words} words\n\n"
        if rewrite_notes:
            user_prompt += (
                "WHAT THE USER WANTS FROM THE REWRITE (let this direct what you "
                f"preserve and what you flag):\n{rewrite_notes}\n\n"
            )
        user_prompt += f"STORY TEXT:\n{story}\n\nProduce the STORY BRIEF."
        output = self._call_claude(SYSTEM_PROMPT, user_prompt)
        return {"agent": "IntakeAgent", "output": output}
