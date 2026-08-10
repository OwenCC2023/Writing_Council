"""Interactive terminal harness for the Writing Council.

Run this instead of editing consult_the_council.py directly.  It asks
each story parameter as a question, then launches the full pipeline.
"""

import sys

from orchestrator import REWRITE_MODES, WritingCouncil
from document_writer import save_as_manuscript, resolve_output_path
from story_intake import load_story_text

_BANNER = """\
╔══════════════════════════════════════╗
║         THE WRITING COUNCIL          ║
╚══════════════════════════════════════╝"""


def _ask(prompt: str, default: str = "", required: bool = False) -> str:
    """Prompt for a single line.  Returns default if the user presses Enter."""
    hint = f" [{default}]" if default else (" (required)" if required else " (optional)")
    while True:
        try:
            value = input(f"  {prompt}{hint}: ").strip()
        except EOFError:
            value = ""
        if value:
            return value
        if default:
            return default
        if not required:
            return ""
        print("  This field is required — please enter a value.")


def _ask_multiline(prompt: str, required: bool = False) -> str:
    """Prompt for multiple lines.  A blank line terminates input."""
    opt = "" if required else " (optional)"
    print(f"\n  {prompt}{opt}")
    print("  (press Enter on a blank line when done)")
    lines: list[str] = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line == "":
            # If nothing entered yet and field is optional, keep prompting until
            # the user either types something or presses Enter a second time.
            if not lines and required:
                print("  This field is required — enter your text above, then a blank line.")
                continue
            break
        lines.append(line)
    return "\n".join(lines).strip()


def _section(title: str) -> None:
    print(f"\n── {title} {'─' * max(0, 44 - len(title))}")


def main() -> None:
    print("\n" + _BANNER)
    print()

    # ── Output metadata ──────────────────────────────────────────────────────
    _section("Output")
    title = _ask("Story title (used for the output filename)", required=True)
    author = _ask("Author name", required=True)

    # ── Core story parameters ─────────────────────────────────────────────────
    _section("Story parameters")
    source_path = _ask("Path to an existing story to rewrite (blank for a new story)")
    source_story, rewrite_mode, rewrite_notes = "", "", ""
    if source_path:
        try:
            source_story = load_story_text(source_path)
        except (ValueError, FileNotFoundError) as exc:
            print(f"\n  Could not read that story: {exc}")
            sys.exit(1)
        rewrite_mode = _ask("Rewrite mode — reimagine or revise", default="reimagine")
        if rewrite_mode not in REWRITE_MODES:
            # Validated here rather than at run() time, so the user is not made
            # to answer every remaining question before hearing about a typo.
            print(f"\n  Unknown rewrite mode {rewrite_mode!r} — "
                  f"expected one of {', '.join(REWRITE_MODES)}.")
            sys.exit(1)
        rewrite_notes = _ask("Anything you want changed in the rewrite")

    # The brief extracted from the original supplies the idea, and blank length
    # or audience means "match the original" — so no defaults are forced here.
    # An idea is still offered on a rewrite: it steers a reimagine, and blank
    # (the common answer) leaves the brief in sole charge.
    idea = _ask_multiline(
        "Story idea — extra steer for the rewrite" if source_story else "Story idea",
        required=not source_story)
    if source_story:
        target_length = _ask("Target length (blank keeps the original's length)")
        target_audience = _ask("Target audience (blank keeps the original's)")
    else:
        target_length = _ask("Target length", default="8,000 words")
        target_audience = _ask("Target audience", required=True)

    # ── Optional world-building ───────────────────────────────────────────────
    _section("World-building (all optional)")
    world_rules = _ask_multiline("World rules — deviations from the real world")
    framework = _ask("Structural framework", default="Short Story")
    style = _ask("Prose style (e.g. Punchy, Hemingway, Lyrical)")
    image = _ask(
        "Reference image — file path or http/https URL\n"
        "    The planner will deduce world rules from the image"
    )

    # ── Confirm & run ─────────────────────────────────────────────────────────
    print("\n" + "─" * 48)
    print(f"  Title:     {title}")
    print(f"  Author:    {author}")
    print(f"  Length:    {target_length or '(match the original)'}")
    print(f"  Audience:  {target_audience or '(match the original)'}")
    if source_story:
        print(f"  Rewrite:   {source_path} ({rewrite_mode or 'reimagine'})")
        print(f"  Changes:   {rewrite_notes or '(none)'}")
    print(f"  Framework: {framework or '(none)'}")
    print(f"  Style:     {style or '(none)'}")
    print(f"  Image:     {image or '(none)'}")
    if idea:
        print(f"  Idea:      {idea[:60]}{'…' if len(idea) > 60 else ''}")
    print("─" * 48)

    try:
        confirm = input("\n  Launch the Writing Council? [Y/n]: ").strip().lower()
    except EOFError:
        confirm = "y"

    if confirm and confirm not in ("y", "yes", ""):
        print("\n  Aborted.")
        sys.exit(0)

    print("\n  Starting the Writing Council…\n")

    try:
        council = WritingCouncil()
        result = council.run(
            idea=idea,
            target_length=target_length,
            target_audience=target_audience,
            world_rules=world_rules,
            framework=framework,
            style=style,
            image=image,
            source_story=source_story,
            source_filename=source_path,
            rewrite_mode=rewrite_mode,
            rewrite_notes=rewrite_notes,
        )
    except KeyboardInterrupt:
        print("\n\n  Interrupted — no output saved.")
        sys.exit(1)

    path = save_as_manuscript(
        story=result["story"],
        title=title,
        author=author,
        output_path=resolve_output_path(title),
    )
    print(f"\n  Manuscript saved: {path}")

    if result.get("intake_brief"):
        print("\n--- STORY BRIEF (extracted from the original) ---")
        print(result["intake_brief"])


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n  Interrupted.")
        sys.exit(1)
