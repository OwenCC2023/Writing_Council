import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from agents import (
    PlanningAgent,
    WriterAgent,
    AIFailureCheckerAgent,
    ConsistencyAgent,
    PeerWriterAgent,
    EditorAgent,
    MarketingAgent,
    AudienceAgent,
    WorldBuilderAgent,
    StrangenessReviewerAgent,
    SensoryQuotaAgent,
    EngineReviewerAgent,
)
from agents.base_agent import INITIAL_DRAFT_MODEL, max_tokens_for
from agents.intake_agent import IntakeAgent, parse_brief
from agents.sectionizer_agent import SectionizerAgent, sectionize
from agents.writer_agent import INITIAL_WRITE_MAX_TOKENS
from constraints import check_constraint
from story_intake import bump_title_version, word_count

LOGS_DIR = Path(__file__).parent / "logs"

_DIVIDER = "=" * 80
_THIN = "-" * 80

MAX_SOURCE_WORDS = 110_000   # ~150k tokens; leaves window headroom for prompts
REVISE_WARN_WORDS = 20_000   # cost cliff: revise re-sends the draft every pass
REWRITE_MODES = ("reimagine", "revise")


class WritingCouncil:
    """
    Orchestrates the full Writing Council pipeline across three nested loops.

    Outer:  Inner → Middle
    Middle: 5/6/7/8 → [1.plan_revision] → Inner
    Inner:  1 → 2 → (4∥3) → 1(plan_revision) → 2

    Agent key:
      1 = PlanningAgent    2 = WriterAgent         3 = AIFailureCheckerAgent
      4 = ConsistencyAgent 5 = PeerWriterAgent      6 = EditorAgent
      7 = MarketingAgent   8 = AudienceAgent

    Parallel notation (X/Y): agents run concurrently on the same input.

    Inner loop detail:
      - First 1: on the initial Outer call, generates the narrative plan via planner.run().
        On all subsequent calls (from Middle), synthesizes middle reviewer feedback via
        planner.plan_revision() — this is the "first plan_revision" referenced for Middle.
      - Second 1: always planner.plan_revision(), synthesizing the parallel checker
        feedback (4 and 3) into an actionable revision plan for Agent 2.

    Middle loop detail:
      All four reviewers (5, 6, 7, 8) run in parallel. Their combined feedback is passed
      into Inner, which uses plan_revision at both Agent 1 positions ("both 1s plan_revision").
    """

    def __init__(self):
        self.planner = PlanningAgent()
        self.writer = WriterAgent()
        self.ai_checker = AIFailureCheckerAgent()
        self.consistency = ConsistencyAgent()
        self.peer_writer = PeerWriterAgent()
        self.editor = EditorAgent()
        self.marketing = MarketingAgent()
        self.audience = AudienceAgent()
        self.world_builder = WorldBuilderAgent()
        self.strangeness = StrangenessReviewerAgent()
        self.sensory = SensoryQuotaAgent()
        self.engine = EngineReviewerAgent()
        self.intake = IntakeAgent()
        self.sectionizer = SectionizerAgent()
        self._log = []
        self._log_file = None

    def _merge_brief(self, fields: dict, *, idea: str, world_rules: str,
                     framework: str, target_length: str, title: str,
                     filename_stem: str = "") -> dict:
        """A non-empty user value wins; otherwise the brief fills it in.

        Craft params only. target_audience, style, and constraint have no brief
        fallback — the user owns them.

        A title inherited from the original (the brief's own TITLE, or the
        uploaded filename) advances its version marker, since a rewrite is a
        new version of the story it came from. A typed title is used verbatim,
        like every other user-supplied value.
        """
        inherited_title = fields.get("TITLE", "") or filename_stem
        return {
            "idea": idea or fields.get("SYNOPSIS", ""),
            "world_rules": world_rules or fields.get("WORLD RULES", ""),
            "framework": framework or fields.get("STORYLINE/STRUCTURE", ""),
            "target_length": target_length or fields.get("LENGTH", ""),
            "title": title or bump_title_version(inherited_title),
        }

    def run(
        self,
        idea: str,
        target_length: str,
        target_audience: str,
        world_rules: str = "",
        framework: str = "",
        style: str = "",
        image: str | list = "",
        prose_passes: int = 1,
        prose_top_n: int = 5,
        title: str = "",
        constraint: str = "",
        source_story: str = "",
        rewrite_mode: str = "",
        rewrite_notes: str = "",
        source_filename: str = "",
    ) -> dict:
        """Run the full outer loop: Inner → Middle → prose-cleanup pass(es).

        Args:
            idea: The story concept or premise.
            target_length: Desired word count (e.g. "8,000 words").
            target_audience: Intended readership.
            title: The story's title, forwarded to the initial PlanningAgent and
                recorded in the returned planning_details.
            world_rules: Optional text describing deviations from the real world.
            framework: Optional structural template (e.g. "Short Story").
            style: Optional prose style keyword.
            image: Optional path to a local image file or an http/https URL, or a
                list of such strings for multiple images. When provided, the
                PlanningAgent will examine the image(s) and deduce the world's
                rules from their visual content before constructing the plan.
            prose_passes: Number of final line-level prose-cleanup passes to run
                after the middle loop (default 1).
            prose_top_n: Number of most-egregious prose violations the prose-mode
                checker reports per pass (default 5).
            constraint: Optional hard formal constraint (e.g. "exactly 200 words",
                "forbidden words: love, death", "told as an obituary"). The planner
                translates it into rules and the writer honors it on every pass;
                countable constraints are also verified deterministically and
                surfaced as ``constraint_check`` on the result.
            source_story: Optional full text of an uploaded story to rewrite. When
                provided, IntakeAgent digests it into a brief that fills in any
                unset craft params, and the rewrite is routed per rewrite_mode.
            rewrite_mode: ``"reimagine"`` (default when source_story is set) plans
                and writes a new story from the intake brief, or ``"revise"``,
                which seeds the inner loop with the uploaded draft itself and
                runs it through the review/revise loops in place of an initial
                write. Ignored when source_story is empty.
            rewrite_notes: Optional free-text guidance for the rewrite (e.g. "make
                the ending darker"), passed to IntakeAgent and, on a revise run,
                to the planner alongside the source story.
            source_filename: Optional filename of the uploaded source_story, used
                only as a title fallback (its stem) when neither the user nor the
                intake brief supplies one.
        """
        self._log = []
        LOGS_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._log_file = LOGS_DIR / f"run_{timestamp}.log"
        self._log_file.write_text("", encoding="utf-8")
        print(f"Logging to {self._log_file}")

        brief_text = ""
        if source_story:
            mode = rewrite_mode or "reimagine"
            if mode not in REWRITE_MODES:
                raise ValueError(
                    f"Unknown rewrite_mode {mode!r}; expected one of {REWRITE_MODES}."
                )
            words = word_count(source_story)
            if words > MAX_SOURCE_WORDS:
                raise ValueError(
                    f"Source story is {words:,} words; the limit is "
                    f"{MAX_SOURCE_WORDS:,}. Chunked intake is not supported."
                )
            if mode == "revise" and words > REVISE_WARN_WORDS:
                print(f"[outer] WARNING: {words:,}-word revise run. The full draft is "
                      f"re-sent to the writer and every checker on each pass; expect "
                      f"cost to scale with length.")

            print("[outer] Running IntakeAgent on the uploaded story...")
            self._log_start("outer.intake", "IntakeAgent",
                            f"words: {words}\nrewrite_notes: {rewrite_notes or '(none)'}")
            intake_result = self.intake.run(story=source_story,
                                            rewrite_notes=rewrite_notes,
                                            source_words=words)
            self._log_end(intake_result, step="outer.intake")
            brief_text = intake_result["output"]

            merged = self._merge_brief(
                parse_brief(brief_text), idea=idea, world_rules=world_rules,
                framework=framework, target_length=target_length, title=title,
                filename_stem=Path(source_filename).stem if source_filename else "")
            idea = merged["idea"]
            world_rules = merged["world_rules"]
            framework = merged["framework"]
            target_length = merged["target_length"]
            title = merged["title"]
        else:
            mode = ""
            words = 0

        # Inner — generates plan and initial story (or, in revise mode, plans
        # and marks the existing draft, seeding the inner loop instead).
        if mode == "revise":
            print("[outer] Starting inner loop (revise: seeded with the uploaded draft)...")
            plan, story, non_earth, canon_sheet, world_bible, planning_details = \
                self._run_revise_setup(
                    brief=brief_text, source_story=source_story,
                    rewrite_notes=rewrite_notes, target_length=target_length,
                    target_audience=target_audience, world_rules=world_rules,
                    framework=framework, style=style, title=title,
                    constraint=constraint, idea=idea, image=image)
            plan, story, non_earth, canon_sheet, world_bible, _ = self._run_inner(
                seeded=True, plan=plan, story=story, non_earth=non_earth,
                canon_sheet=canon_sheet, world_bible=world_bible,
                target_length=target_length, target_audience=target_audience,
                constraint=constraint, label="outer.inner")
        else:
            print("[outer] Starting inner loop (initial write)...")
            plan, story, non_earth, canon_sheet, world_bible, planning_details = \
                self._run_inner(
                    idea=idea,
                    target_length=target_length,
                    target_audience=target_audience,
                    world_rules=world_rules,
                    framework=framework,
                    style=style,
                    image=image,
                    title=title,
                    constraint=constraint,
                    brief=brief_text,
                    rewrite_mode=mode,
                    rewrite_notes=rewrite_notes,
                    source_words=words,
                    label="outer.inner",
                )

        # Middle
        print("[outer] Starting middle loop...")
        story = self._run_middle(plan, story, target_audience,
                                 non_earth=non_earth, canon_sheet=canon_sheet,
                                 world_bible=world_bible, constraint=constraint,
                                 target_length=target_length)

        # Final prose-cleanup pass(es)
        for i in range(prose_passes):
            print(f"[outer] Starting prose-cleanup pass {i + 1}/{prose_passes}...")
            story = self._run_prose_pass(
                plan, story, top_n=prose_top_n, label=f"prose.{i + 1}",
                non_earth=non_earth, canon_sheet=canon_sheet, world_bible=world_bible,
                constraint=constraint, target_length=target_length)

        # Section markers survive until here (the prose passes need them); strip last.
        story = self._strip_section_markers(story)
        return {"story": story, "non_earth": non_earth,
                "planning_details": planning_details,
                "constraint_check": check_constraint(constraint, story),
                "intake_brief": brief_text,
                "rewrite_mode": mode,
                "title": title,
                "target_length": target_length,
                "log": list(self._log)}

    def _count_plan_sections(self, plan: str) -> int:
        """How many sections the plan declares. At least 1.

        Prefers explicit ``SECTION <n>`` headers wherever they appear in a line,
        so markdown decoration (``**SECTION 1:**``, ``## SECTION 1``) still
        counts and numbered sub-lists inside a section cannot inflate the total.
        Falls back to line-start numbering for plans that use bare ``1.`` heads.

        The two strategies cooperate rather than letting either win outright. A
        *single* SECTION number is ambiguous: it is either a genuine one-section
        plan or one stray prose mention ("as section 2 sets up") inside a
        bare-numbered plan. Only a header-shaped mention — the line starts with
        it, decoration aside — is allowed to claim the plan on its own; an
        in-prose mention defers to the bare numbering.
        """
        keyed = set(re.findall(r'SECTION\s+(\d+)', plan, re.IGNORECASE))
        if len(keyed) > 1:
            return len(keyed)
        header_keyed = set(re.findall(r'^[\s>#*_-]*SECTION\s+(\d+)', plan,
                                      re.IGNORECASE | re.MULTILINE))
        if header_keyed:
            return max(1, len(header_keyed))
        nums = set(re.findall(r'^\s*(\d+)[.:)]', plan, re.MULTILINE))
        return max(1, len(nums), len(keyed))

    def _run_revise_setup(self, brief: str, source_story: str, rewrite_notes: str,
                          target_length: str, target_audience: str, world_rules: str,
                          framework: str, style: str, title: str, constraint: str,
                          idea: str, image: str | list = "",
                          label: str = "revise") -> tuple:
        """Plan the existing story, classify it, world-build, and mark sections.

        Returns (plan, marked_story, non_earth, canon_sheet, world_bible,
        planning_details). Kept out of _run_inner, whose initial branch owns
        classification for fresh runs and would reset these values.
        """
        image_desc = ", ".join(image) if isinstance(image, list) else image
        input_text = (
            f"title: {title or '(none)'}\n"
            f"rewrite_mode: revise\n"
            f"rewrite_notes: {rewrite_notes or '(none)'}\n"
            f"source_words: {word_count(source_story)}\n"
            f"idea: {idea}\ntarget_length: {target_length}\n"
            f"target_audience: {target_audience}\n"
            f"world_rules: {world_rules or '(none)'}\n"
            f"framework: {framework or '(none)'}\n"
            f"style: {style or '(none)'}\n"
            f"constraint: {constraint or '(none)'}\n"
            f"image: {image_desc or '(none)'}"
        )

        print(f"[{label}] Running PlanningAgent over the existing story...")
        self._log_start(f"{label}.plan", "PlanningAgent", input_text)
        result = self.planner.run(
            idea=idea, target_length=target_length, target_audience=target_audience,
            world_rules=world_rules, framework=framework, style=style,
            image=image,
            model=INITIAL_DRAFT_MODEL, title=title, constraint=constraint,
            brief=brief, rewrite_notes=rewrite_notes,
            source_story=source_story, plan_existing=True,
        )
        self._log_end(result, step=f"{label}.plan")
        non_earth, plan = self._parse_world_class(result["output"])

        canon_sheet, world_bible = "", ""
        if non_earth:
            print(f"[{label}] NON-EARTH world — running WorldBuilder...")
            self._log_start(f"{label}.world_builder", "WorldBuilderAgent",
                            f"idea:\n{idea}\n\nplan:\n{plan}")
            wb = self.world_builder.run(idea=idea, plan=plan, world_rules=world_rules)
            self._log_end(wb, step=f"{label}.world_builder")
            canon_sheet, world_bible = wb["canon_sheet"], wb["world_bible"]
            # revise_with_world_bible is deliberately NOT called: it rewrites the
            # plan to exploit the world, pulling it away from the draft it must
            # describe.

        section_count = self._count_plan_sections(plan)
        print(f"[{label}] Marking {section_count} sections in the original draft...")
        self._log_start(f"{label}.sectionize", "SectionizerAgent",
                        f"section_count: {section_count}")
        anchors = self.sectionizer.run(plan=plan, story=source_story,
                                       section_count=section_count)
        self._log_end({"agent": "SectionizerAgent", "output": "\n".join(anchors)},
                      step=f"{label}.sectionize")
        marked_story = sectionize(source_story, anchors, section_count)

        return plan, marked_story, non_earth, canon_sheet, world_bible, input_text

    # ------------------------------------------------------------------
    # Inner loop: 1 → 2 → (4∥3) → 1(plan_revision) → 2
    #
    # When called from Outer (idea provided):
    #   - First 1: planner.run() to generate the narrative plan
    #   - Agent 2: writer.run() initial write
    # When called from Middle (middle_feedbacks provided):
    #   - First 1: planner.plan_revision() on the middle feedbacks
    #   - Agent 2: writer.revise() using that plan
    # In both cases the second 1 is always planner.plan_revision() on the checker outputs.
    # ------------------------------------------------------------------
    def _run_inner(
        self,
        idea: str = None,
        target_length: str = None,
        target_audience: str = None,
        world_rules: str = "",
        framework: str = "",
        style: str = "",
        image: str | list = "",
        title: str = "",
        constraint: str = "",
        plan: str = None,
        story: str = None,
        middle_feedbacks: list = None,
        label: str = "inner",
        non_earth: bool = False,
        canon_sheet: str = "",
        world_bible: str = "",
        brief: str = "",
        rewrite_mode: str = "",
        rewrite_notes: str = "",
        source_words: int = 0,
        seeded: bool = False,
    ) -> tuple:
        """Returns (plan, story, non_earth, canon_sheet, world_bible, planning_details)."""

        write_max_tokens = max_tokens_for(target_length, INITIAL_WRITE_MAX_TOKENS)

        planning_details = ""
        revised_sections = None

        if seeded:
            # Revise mode: plan and marked draft come from _run_revise_setup.
            # No plan call, no write call — start at the checker fan-out.
            print(f"[{label}] Seeded with an existing draft; skipping the initial write.")
        elif idea is not None:
            non_earth, canon_sheet, world_bible = False, "", ""
            # ---- Initial call (from Outer): 1 generates plan, 2 writes ----
            print(f"[{label}] Running PlanningAgent (initial plan)...")
            image_desc = ", ".join(image) if isinstance(image, list) else image
            # A rewrite records what it was a rewrite of, in the same shape
            # _run_revise_setup uses. Omitted entirely on a fresh run, which must
            # keep its planning_details byte-for-byte what it always was.
            rewrite_block = (
                f"rewrite_mode: {rewrite_mode}\n"
                f"rewrite_notes: {rewrite_notes or '(none)'}\n"
                f"source_words: {source_words}\n"
            ) if rewrite_mode else ""
            input_text = (
                f"title: {title or '(none)'}\n"
                f"{rewrite_block}"
                f"idea: {idea}\ntarget_length: {target_length}\n"
                f"target_audience: {target_audience}\n"
                f"world_rules: {world_rules or '(none)'}\n"
                f"framework: {framework or '(none)'}\n"
                f"style: {style or '(none)'}\n"
                f"constraint: {constraint or '(none)'}\n"
                f"image: {image_desc or '(none)'}"
            )
            planning_details = input_text
            self._log_start(f"{label}.plan", "PlanningAgent", input_text)
            extra = {}
            if brief:
                extra["brief"] = brief
            if rewrite_notes:
                extra["rewrite_notes"] = rewrite_notes
            result = self.planner.run(
                idea=idea,
                target_length=target_length,
                target_audience=target_audience,
                world_rules=world_rules,
                framework=framework,
                style=style,
                image=image,
                model=INITIAL_DRAFT_MODEL,
                title=title,
                constraint=constraint,
                **extra,
            )
            self._log_end(result, step=f"{label}.plan")
            plan = result["output"]
            non_earth, plan = self._parse_world_class(plan)

            if non_earth:
                print(f"[{label}] NON-EARTH world — running WorldBuilder...")
                self._log_start(f"{label}.world_builder", "WorldBuilderAgent",
                                f"idea:\n{idea}\n\nplan:\n{plan}")
                wb = self.world_builder.run(idea=idea, plan=plan, world_rules=world_rules)
                self._log_end(wb, step=f"{label}.world_builder")
                canon_sheet, world_bible = wb["canon_sheet"], wb["world_bible"]

                print(f"[{label}] Revising plan against the world bible...")
                self._log_start(f"{label}.plan_bible_revision", "PlanningAgent",
                                f"plan:\n{plan}\n\nworld_bible:\n{world_bible}")
                rev = self.planner.revise_with_world_bible(
                    plan=plan, world_bible=world_bible, canon_sheet=canon_sheet,
                    target_length=target_length)
                self._log_end(rev, step=f"{label}.plan_bible_revision")
                plan = rev["output"]

            print(f"[{label}] Running WriterAgent (initial write)...")
            self._log_start(f"{label}.write_1", "WriterAgent", f"plan:\n{plan}")
            write_result = self.writer.run(
                plan=plan, model=INITIAL_DRAFT_MODEL,
                canon_sheet=canon_sheet, world_bible=world_bible, constraint=constraint,
                max_tokens=write_max_tokens)
            self._log_end(write_result, step=f"{label}.write_1")
            story = write_result["output"]
            revised_sections = write_result.get("revised_sections")

        else:
            # ---- Called from Middle: 1 synthesizes middle feedback, 2 revises ----
            print(f"[{label}] Running PlanningAgent (plan revision from middle feedback)...")
            self._log_start(
                f"{label}.plan_revision_1", "PlanningAgent",
                "\n\n".join(
                    f"[Reviewer {i + 1}]\n{f}"
                    for i, f in enumerate(middle_feedbacks)
                ),
            )
            result = self.planner.plan_revision(
                story=story,
                plan=plan,
                feedbacks=middle_feedbacks,
            )
            self._log_end(result, step=f"{label}.plan_revision_1")
            pre_write_plan = result["output"]

            print(f"[{label}] Running WriterAgent (revise from middle plan)...")
            self._log_start(
                f"{label}.write_1", "WriterAgent",
                f"revision_plan:\n{pre_write_plan}\n\nplan:\n{plan}\n\nstory:\n{story}",
            )
            write_result = self.writer.revise(
                plan=plan, story=story, feedback=pre_write_plan,
                model=(INITIAL_DRAFT_MODEL if non_earth else None),
                canon_sheet=canon_sheet, world_bible=world_bible, constraint=constraint,
                max_tokens=write_max_tokens)
            self._log_end(write_result, step=f"{label}.write_1")
            story = write_result["output"]
            revised_sections = write_result.get("revised_sections")

        # ---- 4 and 3: parallel consistency and AI failure check ----
        # If the writer only rewrote specific sections, pass only those to the checkers.
        check_text = (
            self._extract_sections_text(story, revised_sections)
            if revised_sections is not None
            else story
        )
        check_label = (
            f"sections {revised_sections}" if revised_sections is not None else "full story"
        )
        print(f"[{label}] Running ConsistencyAgent, AIFailureCheckerAgent, EngineReviewerAgent"
              f"{', StrangenessReviewerAgent and SensoryQuotaAgent' if non_earth else ''} "
              f"in parallel ({check_label})...")
        self._log_start(f"{label}.consistency", "ConsistencyAgent", f"story:\n{check_text}")
        self._log_start(f"{label}.ai_check", "AIFailureCheckerAgent", f"story:\n{check_text}")
        self._log_start(f"{label}.engine", "EngineReviewerAgent", f"story:\n{check_text}")
        if non_earth:
            self._log_start(f"{label}.strangeness", "StrangenessReviewerAgent",
                            f"story:\n{check_text}")
            self._log_start(f"{label}.sensory", "SensoryQuotaAgent", f"story:\n{check_text}")
        workers = 5 if non_earth else 3
        with ThreadPoolExecutor(max_workers=workers) as executor:
            f_cons = executor.submit(self.consistency.run, story=check_text,
                                     canon_sheet=canon_sheet)
            f_ai = executor.submit(self.ai_checker.run, story=check_text,
                                   canon_sheet=canon_sheet)
            f_eng = executor.submit(self.engine.run, plan=plan, story=check_text,
                                    canon_sheet=canon_sheet)
            f_str = executor.submit(self.strangeness.run, story=check_text,
                                    canon_sheet=canon_sheet) if non_earth else None
            f_sen = executor.submit(self.sensory.run, story=check_text,
                                    canon_sheet=canon_sheet) if non_earth else None
            cons_result = f_cons.result()
            ai_result = f_ai.result()
            eng_result = f_eng.result()
            str_result = f_str.result() if f_str else None
            sen_result = f_sen.result() if f_sen else None
        self._log_end(cons_result, step=f"{label}.consistency")
        self._log_end(ai_result, step=f"{label}.ai_check")
        self._log_end(eng_result, step=f"{label}.engine")
        if str_result:
            self._log_end(str_result, step=f"{label}.strangeness")
        if sen_result:
            self._log_end(sen_result, step=f"{label}.sensory")

        # ---- Second 1: plan_revision on checker outputs ----
        print(f"[{label}] Running PlanningAgent (plan revision from checkers)...")
        feedbacks = [cons_result["output"], ai_result["output"], eng_result["output"]]
        if str_result:
            feedbacks.append(str_result["output"])
        if sen_result:
            feedbacks.append(sen_result["output"])
        self._log_start(
            f"{label}.plan_revision_2", "PlanningAgent",
            "\n\n".join(f"[Checker {i + 1} feedback]\n{f}" for i, f in enumerate(feedbacks)),
        )
        result = self.planner.plan_revision(
            story=story,
            plan=plan,
            feedbacks=feedbacks,
            non_earth=non_earth,
        )
        self._log_end(result, step=f"{label}.plan_revision_2")
        revision_plan = result["output"]

        # ---- Final 2: revise with revision plan ----
        print(f"[{label}] Running WriterAgent (final revise)...")
        self._log_start(
            f"{label}.write_2", "WriterAgent",
            f"revision_plan:\n{revision_plan}\n\nplan:\n{plan}\n\nstory:\n{story}",
        )
        result = self.writer.revise(
            plan=plan, story=story, feedback=revision_plan,
            model=(INITIAL_DRAFT_MODEL if non_earth else None),
            canon_sheet=canon_sheet, world_bible=world_bible, constraint=constraint,
            max_tokens=write_max_tokens)
        self._log_end(result, step=f"{label}.write_2")
        story = result["output"]

        return plan, story, non_earth, canon_sheet, world_bible, planning_details

    # ------------------------------------------------------------------
    # Middle loop: 5/6/7/8 → [1.plan_revision] → Inner(both 1s plan_revision)
    # ------------------------------------------------------------------
    def _run_middle(self, plan: str, story: str, target_audience: str,
                    non_earth: bool = False, canon_sheet: str = "",
                    world_bible: str = "", constraint: str = "",
                    target_length: str = "") -> str:
        # 5, 6, 7, 8 — all four reviewers in parallel
        print("[middle] Running PeerWriterAgent, EditorAgent, MarketingAgent, "
              "AudienceAgent in parallel...")
        self._log_start("middle.peer_writer", "PeerWriterAgent",
                        f"plan:\n{plan}\n\nstory:\n{story}")
        self._log_start("middle.editor", "EditorAgent", f"story:\n{story}")
        self._log_start("middle.marketing", "MarketingAgent",
                        f"target_audience: {target_audience}\n\nstory:\n{story}")
        self._log_start("middle.audience", "AudienceAgent",
                        f"target_audience: {target_audience}\n\nstory:\n{story}")
        with ThreadPoolExecutor(max_workers=4) as executor:
            f_peer = executor.submit(self.peer_writer.run, plan=plan, story=story,
                                     canon_sheet=canon_sheet)
            f_editor = executor.submit(self.editor.run, story=story,
                                       canon_sheet=canon_sheet)
            f_mkt = executor.submit(self.marketing.run, story=story,
                                    target_audience=target_audience,
                                    canon_sheet=canon_sheet)
            f_aud = executor.submit(self.audience.run, story=story,
                                    target_audience=target_audience,
                                    canon_sheet=canon_sheet)
            peer_result = f_peer.result()
            editor_result = f_editor.result()
            mkt_result = f_mkt.result()
            aud_result = f_aud.result()
        self._log_end(peer_result, step="middle.peer_writer")
        self._log_end(editor_result, step="middle.editor")
        self._log_end(mkt_result, step="middle.marketing")
        self._log_end(aud_result, step="middle.audience")

        middle_feedbacks = [
            peer_result["output"],
            editor_result["output"],
            mkt_result["output"],
            aud_result["output"],
        ]

        # Inner with all four middle feedbacks; both Agent 1 calls use plan_revision
        print("[middle] Starting inner loop (both plan_revisions active)...")
        _, story, _, _, _, _ = self._run_inner(
            plan=plan,
            story=story,
            middle_feedbacks=middle_feedbacks,
            label="middle.inner",
            non_earth=non_earth,
            canon_sheet=canon_sheet,
            world_bible=world_bible,
            constraint=constraint,
            target_length=target_length,
        )
        return story

    # ------------------------------------------------------------------
    # Final prose-cleanup pass: (4 ∥ 3_prose) → 1(plan_revision_prose) → 2
    # ------------------------------------------------------------------
    def _run_prose_pass(self, plan: str, story: str, top_n: int = 5,
                        label: str = "prose", non_earth: bool = False,
                        canon_sheet: str = "", world_bible: str = "",
                        constraint: str = "", target_length: str = "") -> str:
        """One line-level polish pass. Runs consistency + prose-mode checker in
        parallel, forces all prose findings into a section-revision plan, and
        applies it. Returns the revised story (markers intact)."""
        print(f"[{label}] Running ConsistencyAgent and AIFailureCheckerAgent "
              f"(prose mode, top {top_n}) in parallel...")
        self._log_start(f"{label}.consistency", "ConsistencyAgent")
        self._log_start(f"{label}.prose_check", "AIFailureCheckerAgent")
        with ThreadPoolExecutor(max_workers=2) as executor:
            f_cons = executor.submit(self.consistency.run, story=story,
                                     canon_sheet=canon_sheet)
            f_prose = executor.submit(self.ai_checker.run_prose, story=story, top_n=top_n,
                                      canon_sheet=canon_sheet)
            cons_result = f_cons.result()
            prose_result = f_prose.result()
        self._log_end(cons_result, step=f"{label}.consistency")
        self._log_end(prose_result, step=f"{label}.prose_check")

        print(f"[{label}] Running PlanningAgent (prose revision plan)...")
        self._log_start(f"{label}.plan_revision", "PlanningAgent")
        plan_result = self.planner.plan_revision_prose(
            story=story,
            plan=plan,
            prose_feedback=prose_result["output"],
            consistency_feedback=cons_result["output"],
            non_earth=non_earth,
        )
        self._log_end(plan_result, step=f"{label}.plan_revision")
        revision_plan = plan_result["output"]

        print(f"[{label}] Running WriterAgent (prose revise)...")
        self._log_start(f"{label}.write", "WriterAgent")
        write_result = self.writer.revise(
            plan=plan, story=story, feedback=revision_plan,
            model=(INITIAL_DRAFT_MODEL if non_earth else None),
            canon_sheet=canon_sheet, world_bible=world_bible, constraint=constraint,
            max_tokens=max_tokens_for(target_length, INITIAL_WRITE_MAX_TOKENS))
        self._log_end(write_result, step=f"{label}.write")
        return write_result["output"]

    @staticmethod
    def _parse_world_class(plan: str) -> tuple:
        """Return (non_earth, plan_without_tag). Missing tag → (False, plan)."""
        m = re.search(r'<<<WORLD_CLASS:\s*(EARTH|NON-EARTH)>>>\n?', plan, re.IGNORECASE)
        if not m:
            return False, plan
        non_earth = m.group(1).upper() == "NON-EARTH"
        return non_earth, plan[:m.start()] + plan[m.end():]

    @staticmethod
    def _strip_section_markers(story: str) -> str:
        """Remove <<<SECTION N>>> markers. Called once at the end of run(),
        after all prose passes — the passes need the markers intact."""
        return re.sub(r'<<<SECTION\s+\d+>>>\n?', '', story)

    # ------------------------------------------------------------------
    # Section helpers
    # ------------------------------------------------------------------

    def _extract_sections_text(self, story: str, section_nums: list) -> str:
        """Return only the specified sections from the story, with their markers."""
        pattern = re.compile(r'<<<SECTION\s+(\d+)>>>', re.IGNORECASE)
        parts = pattern.split(story)
        if len(parts) < 3:
            return story  # no markers; return full story as fallback
        sections = {}
        i = 1
        while i < len(parts) - 1:
            sections[int(parts[i])] = parts[i + 1].strip()
            i += 2
        result = "\n\n".join(
            f"<<<SECTION {n}>>>\n{sections[n]}"
            for n in sorted(section_nums)
            if n in sections
        )
        return result if result else story

    # ------------------------------------------------------------------
    # Logging helpers
    # ------------------------------------------------------------------

    def _log_start(self, step: str, agent_name: str, input_text: str = "") -> None:
        """Write step header immediately before the agent is called.

        input_text is accepted for caller compatibility but no longer logged —
        each agent's input equals the prior agent's output already in the log.
        """
        if not self._log_file:
            return
        with self._log_file.open("a", encoding="utf-8") as f:
            f.write(f"{_DIVIDER}\n")
            f.write(f"STEP:   {step}\n")
            f.write(f"AGENT:  {agent_name}\n")
            f.write(f"START:  {datetime.now().strftime('%H:%M:%S')}\n")
            f.write(f"{_DIVIDER}\n")

    def _log_end(self, result: dict, step: str) -> None:
        """Append output immediately after the agent returns, then record in memory log."""
        self._log.append({**result, "step": step})
        if not self._log_file:
            return
        with self._log_file.open("a", encoding="utf-8") as f:
            f.write(f"--- OUTPUT (completed {datetime.now().strftime('%H:%M:%S')}) ---\n")
            f.write(result.get("output", "").strip())
            f.write("\n\n")
