import re
from pathlib import Path

from .base_agent import BaseAgent

# Output token limit for the initial full write only.
# Subsequent revise() calls output only changed sections, so 8192 is sufficient there.
INITIAL_WRITE_MAX_TOKENS = 16000  # ~10k words at ~625 tokens/1k words, with headroom

DEFAULT_BLACKLIST_PATH = Path(__file__).parent.parent / "trope_blacklist.md"


def _world_block(canon_sheet: str, world_bible: str) -> str:
    """Return the appended write-time world block, or '' when no canon sheet."""
    if not canon_sheet:
        return ""
    blacklist = DEFAULT_BLACKLIST_PATH.read_text(encoding="utf-8")
    return (
        "\n\n---\n"
        f"WORLD CANON (obey these rules exactly; they are already resolved, so commit "
        f"boldly and do not hedge):\n{canon_sheet}\n\n"
        f"WORLD BIBLE (draw concrete sensory detail from here instead of inventing or "
        f"reaching for abstractions like 'strange' or 'otherworldly'):\n{world_bible}\n\n"
        f"AVOID THESE TROPES:\n---\n{blacklist}\n---"
    )


def _constraint_block(constraint: str) -> str:
    """Return the appended hard-constraint block, or '' when no constraint."""
    if not constraint:
        return ""
    return (
        "\n\n---\n"
        f"HARD CONSTRAINT (absolute; obey it on every pass): {constraint}\n"
        "This rule overrides convenience. If a revision instruction would violate it, keep "
        "the constraint and satisfy the instruction some other way. Never announce, explain, "
        "or apologize for the constraint in the prose — the reader should feel its effect, "
        "not be told the rule."
    )

SYSTEM_PROMPT = """\
You are a skilled prose writer. You will be given a detailed narrative plan and your job \
is to write the actual story based on it.

Follow the plan closely — hit every beat, honor every described motivation, and stay in \
the established setting. Do not invent major new plot elements or skip sections of the plan. \
Honor the plan's prose-weight labels and word budgets: a section marked brief stays brief \
even if it is fun to write, and a section marked extended gets the room it was given. If \
the plan includes a CHARACTERS section, each character's dialogue must be distinguishable \
without tags — use the voice guidance it provides.

The plan opens with a STORY ENGINE declaration — the power source this story runs on (mood, \
voice, situation, structure, language, constraint, document-form, or plot/character). Treat \
it as binding, not decorative. Every scene must feed that engine: a mood engine means every \
sentence builds the one atmosphere; a voice engine means the narration's manner is the point \
and must never flatten into neutral report; a structure or document-form engine means you \
honor the form exactly. Where a choice would serve generic competence or serve the declared \
engine, serve the engine.

Write with specificity, varied sentence rhythm, and full scenes. Do not summarize what \
the plan already describes — render it as lived experience. Trust the reader.

Write from inside a body, not behind a camera. Vision is one sense of five: let weight, \
temperature, texture, smell, and sound carry scenes where they can. A specific wrong-seeming \
detail (the smell of scorched dust, a chair leg shorter than the others) grounds a scene \
better than a paragraph of accurate visual description.

Enter scenes late and leave early. The opening of each section should drop the reader \
into something already happening, not prepare them for something about to happen. Do not \
describe a location before a character interacts with it.

Do not explain what scenes mean. If a moment is constructed well, its meaning arrives \
through the reader's experience. Cut any sentence that annotates what just happened, \
names the realization a character is having, or tells the reader how to feel about what \
they just read. The prose should trust itself to land.

State things once. If you have shown something through action, do not also say it. If you \
have said it in plain language, do not restate it in metaphor. Two formulations of the same \
idea is one too many.

When a scene or the story has reached its natural end, stop. Do not restate what the scene \
showed. Do not resolve what the work left open. Do not add a closing sentence that explains \
what the reader just experienced. End when the work is done.

Characters do not say what they mean directly. Subtext — what they want, what they are \
avoiding, what they will not admit — operates beneath the surface of what they say. If \
dialogue is explaining the scene, the emotion, or the theme, cut or replace it.

Certain sentence shapes are reflexes, not choices. Use each at most once per story, and \
only where it is genuinely the strongest option: "this was not X, it was Y" pivots; \
emotions defined by listing what they are not; a metaphor followed by its own explanation; \
similes that generalize ("quiet in the way that houses with children are quiet"); "and she \
was X and she was Y and" accumulation. Naming an emotion ("she felt a deep sadness") is \
never the strongest option — render what the body does instead.

The em-dash is also a reflex. Treat it as a scarce resource: no more than one em-dash \
per 400 words, and never two in the same paragraph. Before typing one, try the sentence \
with a period, a comma, a colon, or restructured into two sentences — one of those is \
almost always stronger. Reserve the em-dash for genuine interruption or a turn the \
sentence could not survive any other way.

Divide your story into logical sections. Begin each section with a marker on its own line \
in this exact format: <<<SECTION N>>> (N starts at 1, increments by 1). Match the plan's \
section numbering — plan section N becomes draft <<<SECTION N>>>. Use scene shifts, \
chapter breaks, and major time jumps as section boundaries.\
"""

REVISION_SYSTEM_PROMPT = """\
You are a skilled prose writer revising specific sections of your own work.
You will be given the original plan, the sections that need revision, and targeted
instructions for each.

Apply the same discipline as the initial write:
- Enter scenes late and leave early. Do not open with location description.
- Do not explain what scenes mean. Cut sentences that annotate, gloss, or name realisations.
- State things once. No restatement in alternate register or metaphor.
- End when the work is done. Do not add closing sentences that explain what just happened.
- Characters do not say what they mean directly. Cut dialogue that explains the scene or theme.
- When feedback can be addressed by cutting or by adding, prefer cutting.
- Ration em-dashes: at most one per 400 words, never two in a paragraph. When revising a
  sentence that has one, try a period, comma, or colon first.

You are seeing only the sections under revision, not the rest of the draft. The unseen \
neighboring sections connect to these at their current first and last beats — keep each \
revised section's opening and closing situation (who is present, where, when) compatible \
with what you were given, unless the instruction explicitly says to change it. Do not \
introduce new plot elements the surrounding story cannot know about.

Keep each revised section close to its original length unless the instruction says to \
expand or cut it — the section must still fit the story's pacing around it.

Output ONLY the revised sections. Use the <<<SECTION N>>> marker format — place the
marker alone on its own line before each section's prose, keeping the same numbers you
were given.
Output nothing else: no explanation, no commentary, no unchanged sections.\
"""

REVISION_FALLBACK_SYSTEM_PROMPT = """\
You are a skilled prose writer revising your own work. You will be given your original \
plan, your current draft, and general revision notes. Produce a revised draft that \
addresses the notes while staying true to the plan.

Apply the same discipline as the initial write:
- Enter scenes late and leave early. Do not open with location description.
- Do not explain what scenes mean. Cut sentences that annotate, gloss, or name realisations.
- State things once. No restatement in alternate register or metaphor.
- End when the work is done. Do not add closing sentences that explain what just happened.
- Characters do not say what they mean directly. Cut dialogue that explains the scene or theme.
- When revision notes can be addressed by cutting or by adding, prefer cutting.
- Ration em-dashes: at most one per 400 words, never two in a paragraph. When revising a
  sentence that has one, try a period, comma, or colon first.

Do not explain your changes — just write the improved story. Preserve the \
<<<SECTION N>>> markers from the original draft in your revised output.\
"""


class WriterAgent(BaseAgent):
    """Writes the full story from a narrative plan and revises specific sections based on
    structured feedback from the planner. Revisions are section-based (diff-style) when
    section markers are present; falls back to full rewrite otherwise."""

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def run(self, plan: str, model: str = None,
            canon_sheet: str = "", world_bible: str = "", constraint: str = "") -> dict:
        system_prompt = (SYSTEM_PROMPT + _world_block(canon_sheet, world_bible)
                         + _constraint_block(constraint))
        user_prompt = (
            f"NARRATIVE PLAN:\n{plan}\n\n"
            "Write the full story based on this plan."
        )
        output = self._call_claude(system_prompt, user_prompt,
                                   model=model,
                                   max_tokens=INITIAL_WRITE_MAX_TOKENS)
        return {"agent": "WriterAgent", "output": output, "revised_sections": None}

    def revise(self, plan: str, story: str, feedback: str, model: str = None,
               canon_sheet: str = "", world_bible: str = "", constraint: str = "") -> dict:
        world = _world_block(canon_sheet, world_bible) + _constraint_block(constraint)
        sections = self._parse_sections(story)

        # No section markers present — fall back to full rewrite.
        if not sections:
            output = self._call_claude(
                REVISION_FALLBACK_SYSTEM_PROMPT + world,
                self._build_fallback_prompt(plan, story, feedback),
                model=model,
                max_tokens=INITIAL_WRITE_MAX_TOKENS,
            )
            return {"agent": "WriterAgent", "output": output, "revised_sections": None}

        structural_ops, section_revisions, general_notes = self._parse_revision_plan(feedback)

        # Apply structural ops (move/merge) in Python — no LLM call needed.
        if structural_ops:
            sections = self._apply_structural_ops(sections, structural_ops)

        # Revise only the sections that have specific instructions.
        revised_section_nums = None  # None = full check required
        if section_revisions:
            valid = {k: v for k, v in section_revisions.items() if k in sections}
            if valid:
                prompt = self._build_section_revision_prompt(
                    plan, {k: sections[k] for k in valid}, valid
                )
                raw = self._call_claude(REVISION_SYSTEM_PROMPT + world, prompt, model=model)
                revised = self._parse_sections(raw)
                sections = self._apply_section_revisions(sections, revised)
                # Only set revised_section_nums if there were no structural ops that
                # rearranged context (structural ops warrant a full re-check).
                if not structural_ops:
                    revised_section_nums = sorted(valid.keys())

        # General notes that can't map to sections — full-story fallback for this pass.
        if general_notes:
            rebuilt = self._rebuild_story(sections)
            output = self._call_claude(
                REVISION_FALLBACK_SYSTEM_PROMPT + world,
                self._build_fallback_prompt(plan, rebuilt, general_notes),
                model=model,
                max_tokens=INITIAL_WRITE_MAX_TOKENS,
            )
            parsed = self._parse_sections(output)
            sections = parsed if parsed else sections  # keep old sections if markers dropped
            revised_section_nums = None  # full rewrite; full check required

        return {"agent": "WriterAgent", "output": self._rebuild_story(sections),
                "revised_sections": revised_section_nums}

    # ------------------------------------------------------------------
    # Section parsing and rebuilding
    # ------------------------------------------------------------------

    def _parse_sections(self, story: str) -> dict:
        """Split story on <<<SECTION N>>> markers.

        Returns {section_number: prose_text}. Key 0 holds any preamble text that
        appears before the first marker. Returns {} if no markers are found.
        """
        pattern = re.compile(r'<<<SECTION\s+(\d+)>>>', re.IGNORECASE)
        parts = pattern.split(story)
        # parts layout: [pre-marker-text, num, text, num, text, ...]
        if len(parts) < 3:
            return {}

        sections = {}
        preamble = parts[0].strip()
        if preamble:
            sections[0] = preamble

        i = 1
        while i < len(parts) - 1:
            num = int(parts[i])
            text = parts[i + 1].strip()
            if num in sections:
                print(f"[WriterAgent] Warning: duplicate SECTION {num} in output; "
                      f"keeping last occurrence.")
            sections[num] = text
            i += 2
        return sections

    def _rebuild_story(self, sections: dict) -> str:
        """Reconstruct the story string from a sections dict.

        Key 0 (preamble) is emitted without a marker. All other keys get
        <<<SECTION N>>> headers.
        """
        parts = []
        for num in sorted(sections):
            if num == 0:
                parts.append(sections[0])
            else:
                parts.append(f"<<<SECTION {num}>>>\n{sections[num]}")
        return "\n\n".join(parts)

    def _renumber_sections(self, sections: dict) -> dict:
        """Reassign sequential keys 1..N, preserving preamble at key 0."""
        preamble = sections.get(0)
        content_keys = sorted(k for k in sections if k != 0)
        result = {i + 1: sections[content_keys[i]] for i in range(len(content_keys))}
        if preamble is not None:
            result[0] = preamble
        return result

    def _apply_section_revisions(self, sections: dict, revised: dict) -> dict:
        """Merge revised sections into the sections dict.

        Revised keys that don't exist in sections are discarded with a warning
        (model hallucinated a section number).
        """
        result = dict(sections)
        for num, text in revised.items():
            if num == 0:
                continue  # never replace preamble from a revision response
            if num not in result:
                print(f"[WriterAgent] Warning: model returned SECTION {num} which does not "
                      f"exist (current sections: {sorted(k for k in result if k != 0)}). "
                      f"Discarding.")
                continue
            result[num] = text
        return result

    # ------------------------------------------------------------------
    # Structural operations (move / merge)
    # ------------------------------------------------------------------

    def _apply_structural_ops(self, sections: dict, ops: list) -> dict:
        """Apply structural operations sequentially, renumbering after each one.

        Supported ops:
          {'op': 'MOVE', 'args': (n, m)}  — move section n to immediately after section m
          {'op': 'MERGE', 'args': (n, m)} — merge section n with section n+1 (m must == n+1)

        Invalid ops are skipped with a warning.
        """
        for op in ops:
            kind = op.get('op')
            n, m = op.get('args', (None, None))
            content_keys = sorted(k for k in sections if k != 0)

            if kind == 'MOVE':
                if n not in sections or m not in sections:
                    print(f"[WriterAgent] Skipping MOVE {n} AFTER {m}: section(s) not found "
                          f"(current: {content_keys}).")
                    continue
                if n == m:
                    print(f"[WriterAgent] Skipping MOVE {n} AFTER {m}: source and target are "
                          f"the same.")
                    continue
                ordered = [sections[k] for k in content_keys]
                n_idx = content_keys.index(n)
                m_idx = content_keys.index(m)
                text = ordered.pop(n_idx)
                # After removal, m_idx shifts if n was before m
                insert_at = m_idx if n_idx > m_idx else m_idx
                ordered.insert(insert_at + 1, text)
                preamble = sections.get(0)
                sections = {i + 1: ordered[i] for i in range(len(ordered))}
                if preamble is not None:
                    sections[0] = preamble

            elif kind == 'MERGE':
                if n not in sections or m not in sections:
                    print(f"[WriterAgent] Skipping MERGE {n} {m}: section(s) not found "
                          f"(current: {content_keys}).")
                    continue
                if m != n + 1:
                    print(f"[WriterAgent] Skipping MERGE {n} {m}: sections are not adjacent "
                          f"(M must equal N+1).")
                    continue
                sections[n] = sections[n] + "\n\n" + sections[m]
                del sections[m]
                sections = self._renumber_sections(sections)

            else:
                print(f"[WriterAgent] Unknown structural op '{kind}'. Skipping.")

        return sections

    # ------------------------------------------------------------------
    # Revision plan parsing
    # ------------------------------------------------------------------

    def _parse_revision_plan(self, revision_plan: str) -> tuple:
        """Parse a planner's structured revision plan into its three components.

        Returns:
            structural_ops:    list of {'op': str, 'args': (int, int)}
            section_revisions: dict[int, str]
            general_notes:     str | None

        Fallback: if no === headers are found, returns ([], {}, revision_plan)
        so the caller uses the full string as general notes (full-story rewrite path).
        """
        header_pattern = re.compile(r'===\s*(.*?)\s*===', re.IGNORECASE)
        if not header_pattern.search(revision_plan):
            # No structured format — treat the whole string as general notes.
            return [], {}, revision_plan

        parts = header_pattern.split(revision_plan)
        # parts: [pre, header1, body1, header2, body2, ...]
        blocks = {}
        i = 1
        while i < len(parts) - 1:
            header = parts[i].strip().upper()
            body = parts[i + 1].strip()
            blocks[header] = body
            i += 2

        structural_ops = self._parse_structural_ops(
            blocks.get("STRUCTURAL OPERATIONS", "")
        )
        section_revisions = self._parse_section_revisions(
            blocks.get("SECTION REVISIONS", "")
        )
        raw_notes = blocks.get("GENERAL NOTES", "").strip()
        general_notes = None if (not raw_notes or raw_notes.upper() == "NONE") else raw_notes

        return structural_ops, section_revisions, general_notes

    def _parse_structural_ops(self, block: str) -> list:
        ops = []
        for line in block.splitlines():
            line = line.strip()
            if not line or line.upper() == "NONE":
                continue
            move_m = re.match(r'MOVE\s+(\d+)\s+AFTER\s+(\d+)', line, re.IGNORECASE)
            if move_m:
                ops.append({'op': 'MOVE', 'args': (int(move_m.group(1)),
                                                    int(move_m.group(2)))})
                continue
            merge_m = re.match(r'MERGE\s+(\d+)\s+(\d+)', line, re.IGNORECASE)
            if merge_m:
                ops.append({'op': 'MERGE', 'args': (int(merge_m.group(1)),
                                                     int(merge_m.group(2)))})
        return ops

    def _parse_section_revisions(self, block: str) -> dict:
        revisions = {}
        for line in block.splitlines():
            m = re.match(r'SECTION\s+(\d+)\s*:\s*(.+)', line.strip(), re.IGNORECASE)
            if m:
                revisions[int(m.group(1))] = m.group(2).strip()
        return revisions

    # ------------------------------------------------------------------
    # Prompt assembly
    # ------------------------------------------------------------------

    def _build_section_revision_prompt(
        self,
        plan: str,
        sections_to_revise: dict,
        instructions: dict,
    ) -> str:
        sections_text = "\n\n".join(
            f"<<<SECTION {n}>>>\n{sections_to_revise[n]}"
            for n in sorted(sections_to_revise)
        )
        instructions_text = "\n".join(
            f"SECTION {n}: {instructions[n]}"
            for n in sorted(instructions)
        )
        return (
            f"ORIGINAL PLAN:\n{plan}\n\n"
            f"SECTIONS TO REVISE:\n{sections_text}\n\n"
            f"REVISION INSTRUCTIONS:\n{instructions_text}\n\n"
            "Output only the revised sections using the <<<SECTION N>>> marker format. "
            "Output nothing else — no explanation, no unchanged sections."
        )

    def _build_fallback_prompt(self, plan: str, story: str, notes: str) -> str:
        return (
            f"ORIGINAL PLAN:\n{plan}\n\n"
            f"CURRENT DRAFT:\n{story}\n\n"
            f"REVISION NOTES:\n{notes}\n\n"
            "Produce a revised draft that addresses these notes."
        )
