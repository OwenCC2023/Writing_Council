from pathlib import Path

from orchestrator import WritingCouncil
from document_writer import save_as_manuscript, resolve_output_path


def _load(path: str, fallback: str) -> str:
    """Return file contents if path is given, otherwise return fallback string."""
    if path:
        return Path(path).read_text(encoding="utf-8")
    return fallback


# --- Story configuration ---
TITLE = "The Sforzato"
AUTHOR = "Owen Cardwell-Copenhefer"
STYLE = "Punchy"  # e.g. "clipped", "flowery", "hemingway", "dark" — or "" for no constraint

IDEA_PATH = ""  # path to a .txt file, or "" to use the inline string below
IDEA = """
    A space-opera set in a distant part of the galaxy with centuries of human habitation. A great empire is in the process of falling,
    remaking itself into a Republic through a civil war. So far it has been a long and bloody affair, but the tide has finally turned in
    the Republican's favor. Or did it?

    The now-outnumbered Imperial side just got a new Fleet Admiral, Admiral Ligatto. Instead of pausing to consolidate
    their forces Admiral Ligatto launches a bold counteroffensive known as The Sforzato. Republican forces are pushed back, losing several
    pivotal battles. Then comes the battle of Frankfurt im Weltraum where Republican forces regain the initiative by being in the
    right place at the right time for entirely the wrong reasons.
"""

WORLD_RULES_PATH = ""  # path to a .txt file, or "" to use the inline string below
WORLD_RULES = """
    Hyperlanes exist between star systems, allowing for faster-than-light travel, but only between certain systems.
    This gives the region a geography - choke points, dead-ends, and crossroads. FTL communication is only possible through a network of relay stations, which are vulnerable to attack and sabotage.

    Otherwise, I want pure hard sci-fi here. Make it conform to known physics, just in the future.
"""

council = WritingCouncil()
result = council.run(
    idea=_load(IDEA_PATH, IDEA),
    target_length="8,000 words",
    target_audience="Adult sci-fi readers",
    world_rules=_load(WORLD_RULES_PATH, WORLD_RULES),
    framework="Short Story",                     # optional
    style=STYLE,                                 # optional
    # image="path/to/world_reference.png",       # optional — local file or http/https URL;
    #                                            # the planner will deduce world rules from it
)

# Save the finished story as a manuscript Word document
path = save_as_manuscript(
    story=result["story"],
    title=TITLE,
    author=AUTHOR,
    output_path=resolve_output_path(TITLE),
)
print(f"Saved manuscript: {path}")

# Full log of every agent call
for entry in result["log"]:
    print(f"{entry['step']}: {entry['output'][:100]}...")
