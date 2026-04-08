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
)

LOGS_DIR = Path(__file__).parent / "logs"

_DIVIDER = "=" * 80
_THIN = "-" * 80


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
        self._log = []
        self._log_file = None

    def run(
        self,
        idea: str,
        target_length: str,
        target_audience: str,
        world_rules: str = "",
        framework: str = "",
        style: str = "",
        image: str = "",
    ) -> dict:
        """Run the full outer loop: Inner → Middle.

        Args:
            idea: The story concept or premise.
            target_length: Desired word count (e.g. "8,000 words").
            target_audience: Intended readership.
            world_rules: Optional text describing deviations from the real world.
            framework: Optional structural template (e.g. "Short Story").
            style: Optional prose style keyword.
            image: Optional path to a local image file or an http/https URL. When
                provided, the PlanningAgent will examine the image and deduce the
                world's rules from its visual content before constructing the plan.
        """
        self._log = []
        LOGS_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._log_file = LOGS_DIR / f"run_{timestamp}.log"
        self._log_file.write_text("", encoding="utf-8")
        print(f"Logging to {self._log_file}")

        # Inner — generates plan and initial story
        print("[outer] Starting inner loop (initial write)...")
        plan, story = self._run_inner(
            idea=idea,
            target_length=target_length,
            target_audience=target_audience,
            world_rules=world_rules,
            framework=framework,
            style=style,
            image=image,
            label="outer.inner",
        )

        # Middle
        print("[outer] Starting middle loop...")
        story = self._run_middle(plan, story, target_audience)

        return {"story": story, "log": list(self._log)}

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
        image: str = "",
        plan: str = None,
        story: str = None,
        middle_feedbacks: list = None,
        label: str = "inner",
    ) -> tuple:
        """Returns (plan, story)."""

        if idea is not None:
            # ---- Initial call (from Outer): 1 generates plan, 2 writes ----
            print(f"[{label}] Running PlanningAgent (initial plan)...")
            input_text = (
                f"idea: {idea}\ntarget_length: {target_length}\n"
                f"target_audience: {target_audience}\n"
                f"world_rules: {world_rules or '(none)'}\n"
                f"framework: {framework or '(none)'}\n"
                f"style: {style or '(none)'}\n"
                f"image: {image or '(none)'}"
            )
            self._log_start(f"{label}.plan", "PlanningAgent", input_text)
            result = self.planner.run(
                idea=idea,
                target_length=target_length,
                target_audience=target_audience,
                world_rules=world_rules,
                framework=framework,
                style=style,
                image=image,
            )
            self._log_end(result, step=f"{label}.plan")
            plan = result["output"]

            print(f"[{label}] Running WriterAgent (initial write)...")
            self._log_start(f"{label}.write_1", "WriterAgent", f"plan:\n{plan}")
            result = self.writer.run(plan=plan)
            self._log_end(result, step=f"{label}.write_1")
            story = result["output"]

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
            result = self.writer.revise(plan=plan, story=story, feedback=pre_write_plan)
            self._log_end(result, step=f"{label}.write_1")
            story = result["output"]

        # ---- 4 and 3: parallel consistency and AI failure check ----
        print(f"[{label}] Running ConsistencyAgent and AIFailureCheckerAgent in parallel...")
        self._log_start(f"{label}.consistency", "ConsistencyAgent", f"story:\n{story}")
        self._log_start(f"{label}.ai_check", "AIFailureCheckerAgent", f"story:\n{story}")
        with ThreadPoolExecutor(max_workers=2) as executor:
            f_cons = executor.submit(self.consistency.run, story=story)
            f_ai = executor.submit(self.ai_checker.run, story=story)
            cons_result = f_cons.result()
            ai_result = f_ai.result()
        self._log_end(cons_result, step=f"{label}.consistency")
        self._log_end(ai_result, step=f"{label}.ai_check")

        # ---- Second 1: plan_revision on checker outputs ----
        print(f"[{label}] Running PlanningAgent (plan revision from checkers)...")
        self._log_start(
            f"{label}.plan_revision_2", "PlanningAgent",
            f"[Consistency feedback]\n{cons_result['output']}\n\n"
            f"[AI failure feedback]\n{ai_result['output']}",
        )
        result = self.planner.plan_revision(
            story=story,
            plan=plan,
            feedbacks=[cons_result["output"], ai_result["output"]],
        )
        self._log_end(result, step=f"{label}.plan_revision_2")
        revision_plan = result["output"]

        # ---- Final 2: revise with revision plan ----
        print(f"[{label}] Running WriterAgent (final revise)...")
        self._log_start(
            f"{label}.write_2", "WriterAgent",
            f"revision_plan:\n{revision_plan}\n\nplan:\n{plan}\n\nstory:\n{story}",
        )
        result = self.writer.revise(plan=plan, story=story, feedback=revision_plan)
        self._log_end(result, step=f"{label}.write_2")
        story = result["output"]

        return plan, story

    # ------------------------------------------------------------------
    # Middle loop: 5/6/7/8 → [1.plan_revision] → Inner(both 1s plan_revision)
    # ------------------------------------------------------------------
    def _run_middle(self, plan: str, story: str, target_audience: str) -> str:
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
            f_peer = executor.submit(self.peer_writer.run, plan=plan, story=story)
            f_editor = executor.submit(self.editor.run, story=story)
            f_mkt = executor.submit(self.marketing.run, story=story,
                                    target_audience=target_audience)
            f_aud = executor.submit(self.audience.run, story=story,
                                    target_audience=target_audience)
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
        _, story = self._run_inner(
            plan=plan,
            story=story,
            middle_feedbacks=middle_feedbacks,
            label="middle.inner",
        )
        return story

    # ------------------------------------------------------------------
    # Logging helpers
    # ------------------------------------------------------------------

    def _log_start(self, step: str, agent_name: str, input_text: str) -> None:
        """Write step header + input immediately before the agent is called."""
        if not self._log_file:
            return
        with self._log_file.open("a", encoding="utf-8") as f:
            f.write(f"{_DIVIDER}\n")
            f.write(f"STEP:   {step}\n")
            f.write(f"AGENT:  {agent_name}\n")
            f.write(f"START:  {datetime.now().strftime('%H:%M:%S')}\n")
            f.write(f"{_DIVIDER}\n")
            f.write("--- INPUT ---\n")
            f.write(input_text.strip())
            f.write("\n\n")

    def _log_end(self, result: dict, step: str) -> None:
        """Append output immediately after the agent returns, then record in memory log."""
        self._log.append({**result, "step": step})
        if not self._log_file:
            return
        with self._log_file.open("a", encoding="utf-8") as f:
            f.write(f"--- OUTPUT (completed {datetime.now().strftime('%H:%M:%S')}) ---\n")
            f.write(result.get("output", "").strip())
            f.write("\n\n")
