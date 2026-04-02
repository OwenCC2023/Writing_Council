from orchestrator import WritingCouncil
from document_writer import save_as_manuscript

# --- Story configuration ---
TITLE = "The Sforzato"
AUTHOR = "Owen Cardwell-Copenhefer"
STYLE = ""  # e.g. "clipped", "flowery", "hemingway", "dark" — or "" for no constraint

council = WritingCouncil()
result = council.run(
    idea="""
    A space-opera set in a distant part of the galaxy with centuries of human habitation. A great empire is in the process of falling,
    remaking itself into a Republic through a civil war. So far it has been a long and bloody affair, but the tide has finally turned in
    the Republican's favor. Or did it?

    The now-outnumbered Imperial side just got a new Fleet Admiral, Admiral Quent. Instead of pausing to consolidate
    his forces Admiral Quent launches a bold counteroffensive known as The Sforzato. Republican forces were pushed back, losing several
    pivotal battles. Then came the battle of Frankfurt im Weltraum where Republican forces regained the initiative by being in the
    right place at the right time for entirely the wrong reasons.
    """,
    target_length="8,000 words",
    target_audience="Adult sci-fi readers",
    world_rules="Actually none. I want pure hard sci-fi here. Make it conform to known physics, just in the future.",  # optional
    framework="Short Story",                     # optional
    style=STYLE,                                 # optional
)

# Save the finished story as a manuscript Word document
path = save_as_manuscript(
    story=result["story"],
    title=TITLE,
    author=AUTHOR,
    output_path="output.docx",
)
print(f"Saved manuscript: {path}")

# Full log of every agent call
for entry in result["log"]:
    print(f"{entry['step']}: {entry['output'][:100]}...")
