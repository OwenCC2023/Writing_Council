"""Load an existing story from disk into plain text.

No LLM, no policy: this module reads files. Length limits live in
WritingCouncil.run (pasted text never reaches this module), and manuscript
front matter is left in place for the intake prompt to ignore.
"""

from pathlib import Path

SUPPORTED_SUFFIXES = {".txt", ".md", ".docx"}


def word_count(text: str) -> int:
    """Whitespace-separated token count."""
    return len(text.split())


def _load_docx(path: Path) -> str:
    try:
        from docx import Document
    except ImportError as exc:  # pragma: no cover
        raise ImportError(
            "Reading .docx requires python-docx. Run: pip install python-docx"
        ) from exc
    doc = Document(str(path))
    return "\n\n".join(p.text for p in doc.paragraphs)


def load_story_text(path) -> str:
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
