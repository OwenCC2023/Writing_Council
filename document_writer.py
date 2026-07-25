import io
from pathlib import Path

from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_LINE_SPACING, WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


_STORY_OUTPUTS = Path(__file__).parent / "story_outputs"


def resolve_output_path(title: str) -> Path:
    """Return a non-colliding .docx path under story_outputs/<title>/.

    Creates the folder if needed. If <title>.docx already exists,
    returns <title>_v2.docx, _v3.docx, … until a free name is found.
    """
    folder = _STORY_OUTPUTS / title
    folder.mkdir(parents=True, exist_ok=True)
    candidate = folder / f"{title}.docx"
    if not candidate.exists():
        return candidate
    v = 2
    while True:
        candidate = folder / f"{title}_v{v}.docx"
        if not candidate.exists():
            return candidate
        v += 1


def _add_page_number(paragraph) -> None:
    """Append a PAGE field to an existing paragraph run."""
    run = paragraph.add_run()
    fld_begin = OxmlElement("w:fldChar")
    fld_begin.set(qn("w:fldCharType"), "begin")
    run._r.append(fld_begin)

    instr = OxmlElement("w:instrText")
    instr.set(qn("xml:space"), "preserve")
    instr.text = " PAGE "
    run._r.append(instr)

    fld_end = OxmlElement("w:fldChar")
    fld_end.set(qn("w:fldCharType"), "end")
    run._r.append(fld_end)


def save_as_manuscript(
    story: str,
    title: str,
    author: str,
    output_path: str = None,
    output: io.BytesIO = None,
    details: str = None,
):
    """Save *story* as a standard manuscript-formatted .docx file.

    Format: Times New Roman 12pt, double-spaced, 1" margins, 0.5" first-line
    indent, running header: Author / TITLE / page number.

    If *details* is provided (the parameters sent to the initial PlanningAgent),
    a "Story Parameters" section is appended on a new page after the story.

    Returns output_path (str) if writing to a file, or the BytesIO buffer seeked to 0.
    """
    doc = Document()

    # --- Margins ---
    section = doc.sections[0]
    section.top_margin = Inches(1)
    section.bottom_margin = Inches(1)
    section.left_margin = Inches(1)
    section.right_margin = Inches(1)

    # --- Default Normal style ---
    normal = doc.styles["Normal"]
    normal.font.name = "Times New Roman"
    normal.font.size = Pt(12)

    # --- Running header: Author / TITLE / <page> ---
    header = section.header
    header.is_linked_to_previous = False
    # Clear any default paragraph in the header
    for p in header.paragraphs:
        p.clear()
    hdr_para = header.paragraphs[0]
    hdr_para.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    hdr_para.style = doc.styles["Normal"]
    hdr_run = hdr_para.add_run(f"{author} / {title.upper()} / ")
    hdr_run.font.name = "Times New Roman"
    hdr_run.font.size = Pt(12)
    _add_page_number(hdr_para)

    # --- Body paragraphs ---
    chunks = [c.strip() for c in story.split("\n\n") if c.strip()]

    for chunk in chunks:
        para = doc.add_paragraph()
        para.style = doc.styles["Normal"]

        pf = para.paragraph_format
        pf.space_before = Pt(0)
        pf.space_after = Pt(0)

        if chunk in ("***", "---", "* * *"):
            # Section break — centered, no indent, single-spaced
            pf.alignment = WD_ALIGN_PARAGRAPH.CENTER
            pf.line_spacing_rule = WD_LINE_SPACING.SINGLE
            pf.first_line_indent = Inches(0)
            run = para.add_run(chunk)
            run.font.name = "Times New Roman"
            run.font.size = Pt(12)
        else:
            pf.alignment = WD_ALIGN_PARAGRAPH.LEFT
            pf.line_spacing_rule = WD_LINE_SPACING.DOUBLE
            pf.first_line_indent = Inches(0.5)
            run = para.add_run(chunk)
            run.font.name = "Times New Roman"
            run.font.size = Pt(12)

    # --- Appended parameters page: details sent to the initial PlanningAgent ---
    if details and details.strip():
        doc.add_page_break()

        heading = doc.add_paragraph()
        heading.style = doc.styles["Normal"]
        hpf = heading.paragraph_format
        hpf.space_before = Pt(0)
        hpf.space_after = Pt(0)
        hpf.line_spacing_rule = WD_LINE_SPACING.SINGLE
        hpf.first_line_indent = Inches(0)
        hrun = heading.add_run("Story Parameters")
        hrun.bold = True
        hrun.font.name = "Times New Roman"
        hrun.font.size = Pt(12)

        for line in details.split("\n"):
            para = doc.add_paragraph()
            para.style = doc.styles["Normal"]
            dpf = para.paragraph_format
            dpf.space_before = Pt(0)
            dpf.space_after = Pt(0)
            dpf.line_spacing_rule = WD_LINE_SPACING.SINGLE
            dpf.first_line_indent = Inches(0)
            run = para.add_run(line)
            run.font.name = "Times New Roman"
            run.font.size = Pt(12)

    if (output_path is None) == (output is None):
        raise ValueError("Provide exactly one of output_path or output")
    if output_path is not None:
        doc.save(output_path)
        return output_path
    doc.save(output)
    output.seek(0)
    return output


if __name__ == "__main__":
    # Quick smoke-test with sample text
    sample = (
        "The Last Signal\n\n"
        "The radio crackled once, then fell silent. Lieutenant Mara Chen pressed "
        "her headset tight against her ear, willing the static back into something "
        "recognizable — a voice, a pattern, anything human.\n\n"
        "Outside the observation window, the nebula churned in slow violet spirals. "
        "She had been watching it for six hours, logging every fluctuation, every "
        "pulse of light that didn't quite match the models.\n\n"
        "***\n\n"
        "The signal came again at 0300, clearer this time. Three tones, repeating."
    )
    path = save_as_manuscript(sample, title="The Last Signal", author="J. Smith", output_path="test_output.docx")
    print(f"Written to {path}")
