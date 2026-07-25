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
STYLE = ""  # e.g. "clipped", "flowery", "hemingway", "dark" — or "" for no constraint

IDEA_PATH = ""  # path to a .txt file, or "" to use the inline string below
IDEA = """
    A space-opera set in a distant part of the galaxy with centuries of human habitation. A great empire is in the process of falling - 
    remaking itself into a Republic through a civil war. The war is a long and bloody affair, but the tide has finally turned in the Republican's favor. Or did it?

    The now-outnumbered Imperial side's new Fleet Admiral, Admiral Ligatto, launches a bold counteroffensive known as The Sforzato. Surprised, Republican forces are pushed back, losing several
    pivotal battles and taking heavy casualties. Then comes the battle of Frankfurt im Weltraum where Republican forces regain the initiative, simply by being in the right place at the right 
    time for the wrong reason. The Sforzato's momentum is broken, and the Imperial side is once again forced onto the defensive - weaker now than when it started.
"""

WORLD_RULES_PATH = ""  # path to a .txt file, or "" to use the inline string below
WORLD_RULES = """
    Hyperlanes exist between star systems, but only between certain systems. This is the FTL mechanism. Ships exit the hyperlane at relative rest, and must accelerate upon departure. However, mining the exits
    is not realistic due to the bubble of spacetime that enters local space whenever ships exit the hyperlane, causing all nearby objects to move away as if pushed by a wave.
    This gives the region a geography - choke points, dead-ends, and crossroads. FTL communication is only possible through a network of relay stations that sit outside each hyperlane and rely on ships to
    physically traverse the hyperlanes to move messages between systems. These relay stations and the ships between them are vulnerable to attack and sabotage.

    Otherwise, make it purely hard sci-fi here. Make it conform to known physics with realistic travel times and speeds, just in the future.
"""

council = WritingCouncil()
result = council.run(
    idea=_load(IDEA_PATH, IDEA),
    target_length="8,000 words",
    target_audience="Adult sci-fi readers",
    world_rules=_load(WORLD_RULES_PATH, WORLD_RULES),
    framework="Short Story",                     # optional
    style=STYLE,                                 # optional
    title=TITLE,
    # image="path/to/world_reference.png",       # optional — local file or http/https URL;
    #                                            # the planner will deduce world rules from it
)

# Save the finished story as a manuscript Word document
path = save_as_manuscript(
    story=result["story"],
    title=TITLE,
    author=AUTHOR,
    output_path=resolve_output_path(TITLE),
    details=result.get("planning_details"),
)
print(f"Saved manuscript: {path}")

# Full log of every agent call
for entry in result["log"]:
    print(f"{entry['step']}: {entry['output'][:100]}...")
