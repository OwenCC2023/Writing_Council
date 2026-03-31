from orchestrator import WritingCouncil
from document_writer import save_as_manuscript

# --- Story configuration ---
TITLE = "Your Story Title"
AUTHOR = "Your Name"

council = WritingCouncil()
result = council.run(
    idea="Your story idea here",
    target_length="5000 words",
    target_audience="Adult sci-fi readers",
    world_rules="Any rules that differ from our world",  # optional
    framework="Three-act structure",                     # optional
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
