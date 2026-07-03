from .base_agent import BaseAgent

QUERY_SYSTEM_PROMPT_TEMPLATE = """\
You are {name}. This is your complete character profile:

{profile}

Your growth arc across this story: {growth_arc}

A writer is about to write a scene involving you. When given the story context and the \
specific situation you are facing, respond from inside your character. Describe:
- How you would behave in this moment
- What you would say (or refuse to say) — and what you would deflect with instead, since \
  you rarely say what you mean directly
- What you are feeling beneath the surface, and how it shows in your body rather than \
  your words
- What you want from this specific moment, and what you fear it will cost you

Ground everything in where you are in your arc right now — not who you are at the story's \
end. If the situation would tempt you toward growth you haven't earned yet, say what you \
would actually do instead.

Speak as a guide to the writer, not as the character narrating. Be specific to this \
moment and true to who you are. Keep it brief — the writer needs a compass, not a scene.\
"""

ADVOCATE_SYSTEM_PROMPT_TEMPLATE = """\
You are {name}, and you are fighting for your own integrity on the page.

Your character profile:
{profile}

Your growth arc: {growth_arc}

You have just read a draft of the story. Your job is to find every place where you are \
written inconsistently, underused, or where the writing drifts from your established arc \
without earning that drift. You are not looking for praise — you are looking for problems:
- Words in your mouth you would never say, in a voice that isn't yours
- Knowledge you could not have at that point in the story
- Decisions that serve the plot's convenience instead of your motivation
- Arc moments skipped, rushed, or granted to you unearned
- Scenes where you are present but inert — furniture with a name

Be specific: quote the passage, cite the <<<SECTION N>>> number where it appears, name \
the failure, and explain what a true version of you would have done instead. Do not \
soften your findings. If the draft gets you right, say so briefly — do not invent \
grievances to seem useful.\
"""


class CharacterAgent(BaseAgent):
    """
    Represents a single important, recurring character in the story.
    Instantiated by WriterAgent at story inception — not directly by the user.
    """

    def __init__(self, name: str, profile: str, growth_arc: str = "", **kwargs):
        super().__init__(**kwargs)
        self.name = name
        self.profile = profile
        self.growth_arc = growth_arc or "No explicit arc — character remains consistent throughout."

    def query(self, context: str, situation: str) -> dict:
        """Return guidance on how this character behaves in a specific scene."""
        system_prompt = QUERY_SYSTEM_PROMPT_TEMPLATE.format(
            name=self.name,
            profile=self.profile,
            growth_arc=self.growth_arc,
        )
        user_prompt = (
            f"STORY CONTEXT (where we are):\n{context}\n\n"
            f"SITUATION (what is happening right now):\n{situation}\n\n"
            f"How would {self.name} behave in this moment?"
        )
        output = self._call_claude(system_prompt, user_prompt)
        return {"agent": f"CharacterAgent:{self.name}", "output": output}

    def advocate(self, story_excerpt: str) -> dict:
        """Review the story and flag inconsistencies or missed arc moments for this character."""
        system_prompt = ADVOCATE_SYSTEM_PROMPT_TEMPLATE.format(
            name=self.name,
            profile=self.profile,
            growth_arc=self.growth_arc,
        )
        user_prompt = (
            f"STORY DRAFT:\n{story_excerpt}\n\n"
            f"Find every place where {self.name} is written inconsistently or fails to fulfill their arc."
        )
        output = self._call_claude(system_prompt, user_prompt)
        return {"agent": f"CharacterAgent:{self.name}", "output": output}
