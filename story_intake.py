"""Load an existing story from disk into plain text.

No LLM, no policy: this module reads files. Length limits live in
WritingCouncil.run (pasted text never reaches this module), and manuscript
front matter is left in place for the intake prompt to ignore.
"""

import re
from pathlib import Path

SUPPORTED_SUFFIXES = {".txt", ".md", ".docx"}

# A trailing version marker: v-prefixed, at least one digit, optionally followed
# by dot- or underscore-separated components. Anchored to the end so a "v2" in
# the middle of a title is left alone.
_VERSION_SUFFIX = re.compile(
    r"(?P<v>[vV])(?P<major>\d+)(?P<tail>(?:[._]\d+)*)$"
)


def word_count(text: str) -> int:
    """Whitespace-separated token count."""
    return len(text.split())


def _load_docx(path: Path) -> str:
    try:
        from docx import Document
    except ImportError as exc:  # pragma: no cover - python-docx is in requirements.txt
        raise ImportError(
            "Reading .docx requires python-docx. Run: pip install python-docx"
        ) from exc
    doc = Document(str(path))
    return "\n\n".join(p.text for p in doc.paragraphs)


def bump_title_version(title: str) -> str:
    """Return the title a rewrite of `title` should carry.

    A rewrite is a new version of the story it came from, so the title's
    version marker advances:

        The Sforzato       -> The Sforzato v2      (no marker yet: this is v2)
        The Sforzato v2    -> The Sforzato v3
        The Sforzato v2.3  -> The Sforzato v3.0    (dotted: lower parts zeroed)
        sforzato_v2_3      -> sforzato_v3          (underscored: lower parts dropped)

    Only the highest-placed component advances; everything below it is zeroed
    or dropped, depending on how the version writes its own separators. A bare
    trailing number is left alone — "Blade Runner 2049" is a title, not a
    version — so a marker must be v-prefixed to count.
    """
    if not title.strip():
        return title

    match = _VERSION_SUFFIX.search(title)
    if not match:
        # No marker yet. Attach one using the title's own word separator, so a
        # filename stem stays a filename stem.
        separator = "_" if ("_" in title and " " not in title) else " "
        return f"{title}{separator}v2"

    head = title[: match.start()]
    marker = match.group("v")
    major = int(match.group("major")) + 1
    tail = match.group("tail") or ""

    if "." in tail:
        # Dotted: keep the shape, zero every lower component.
        zeroed = "".join(f".{0}" for _ in tail.split(".")[1:])
        return f"{head}{marker}{major}{zeroed}"
    # Underscored (or absent): the lower components go away entirely.
    return f"{head}{marker}{major}"


def load_story_text(path: str | Path) -> str:
    """Return the plain text of a .txt, .md, or .docx story file."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise ValueError(
            f"Unsupported story file type '{suffix or path.name}'. "
            f"Supported: {', '.join(sorted(SUPPORTED_SUFFIXES))}"
        )
    if suffix == ".docx":
        text = _load_docx(path)
    else:
        text = path.read_text(encoding="utf-8")
    if not text.strip():
        raise ValueError(f"Story file '{path.name}' is empty.")
    return text.strip()
