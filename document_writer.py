import io

from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_LINE_SPACING, WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement


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
):
    """Save *story* as a standard manuscript-formatted .docx file.

    Format: Times New Roman 12pt, double-spaced, 1" margins, 0.5" first-line
    indent, running header: Author / TITLE / page number.

    Returns the output_path that was written.
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
