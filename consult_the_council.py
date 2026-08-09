from pathlib import Path

from orchestrator import WritingCouncil
from document_writer import save_as_manuscript, resolve_output_path
from story_intake import load_story_text


def _load(path: str, fallback: str) -> str:
    """Return file contents if path is given, otherwise return fallback string."""
    if path:
        return Path(path).read_text(encoding="utf-8")
    return fallback


# --- Story configuration ---
TITLE = "The Sforzato"
AUTHOR = "Owen Cardwell-Copenhefer"
STYLE = ""  # e.g. "clipped", "flowery", "hemingway", "dark" — or "" for no style
CONSTRAINT = ""  # hard formal rule, e.g. "exactly 200 words", "forbidden words: love, death",
                 # "told as an obituary", "second person throughout" — or "" for none

SOURCE_STORY_PATH = ""   # path to an existing .txt/.md/.docx story, or "" for a fresh run
REWRITE_MODE = ""        # "reimagine" (new story on the original's bones) or
                         # "revise" (edit the original prose). "" defaults to reimagine.
REWRITE_NOTES = ""       # e.g. "cut it to 3,000 words", "second person", "darker ending"
# With SOURCE_STORY_PATH set, leaving TARGET_LENGTH blank keeps the original's length.
TARGET_LENGTH = "8,000 words"
TARGET_AUDIENCE = "Adult sci-fi readers"

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

def main() -> None:
    """Run a real council pass and save the manuscript. Billed and long —
    only runs when this file is executed directly, never on import."""
    source_story = load_story_text(SOURCE_STORY_PATH) if SOURCE_STORY_PATH else ""

    council = WritingCouncil()
    result = council.run(
        idea=_load(IDEA_PATH, IDEA),
        target_length=TARGET_LENGTH,
        target_audience=TARGET_AUDIENCE,
        world_rules=_load(WORLD_RULES_PATH, WORLD_RULES),
        framework="Short Story",                     # optional
        style=STYLE,                                 # optional
        constraint=CONSTRAINT,                       # optional
        title=TITLE,
        source_story=source_story,                   # optional — rewrite an existing story
        source_filename=SOURCE_STORY_PATH,
        rewrite_mode=REWRITE_MODE,
        rewrite_notes=REWRITE_NOTES,
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

    # The brief the intake agent extracted from the original story
    if result.get("intake_brief"):
        print("\n--- STORY BRIEF (extracted from the original) ---")
        print(result["intake_brief"])

    # Deterministic constraint verification (only when a countable constraint was set)
    cc = result.get("constraint_check")
    if cc:
        status = "PASSED" if cc["passed"] else "FAILED"
        print(f"Constraint check {status}: {cc['checks']}")

    # Full log of every agent call
    for entry in result["log"]:
        print(f"{entry['step']}: {entry['output'][:100]}...")


if __name__ == "__main__":
    main()
