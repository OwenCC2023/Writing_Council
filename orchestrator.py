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


class WritingCouncil:
    """
    Orchestrates the full Writing Council pipeline across three nested loops.

    Outer:  1 → Inner → Middle → Middle
    Middle: 5 → Inner → 6 → Inner → 7 → Inner → 8 → Inner
    Inner:  2 → 3 → 2 → 4 → 2 → 3 → 2
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

    def run(
        self,
        idea: str,
        target_length: str,
        target_audience: str,
        world_rules: str = "",
        framework: str = "",
    ) -> dict:
        """Run the full outer loop: 1 → Inner → Middle → Middle."""
        self._log = []

        # 1 — PlanningAgent
        result = self.planner.run(
            idea=idea,
            target_length=target_length,
            target_audience=target_audience,
            world_rules=world_rules,
            framework=framework,
        )
        self._record(result, step="outer.plan")
        plan = result["output"]

        # Inner — fresh write
        story = self._run_inner(plan, label="outer.inner")

        # Middle × 2
        story = self._run_middle(plan, story, target_audience, pass_num=1)
        story = self._run_middle(plan, story, target_audience, pass_num=2)

        return {"story": story, "log": list(self._log)}

    # ------------------------------------------------------------------
    # Inner loop: 2 → 3 → 2 → 4 → 2 → 3 → 2
    # ------------------------------------------------------------------
    def _run_inner(self, plan: str, story: str = None, feedback: str = None, label: str = "inner") -> str:
        # 2 — write or revise
        if story is None:
            result = self.writer.run(plan=plan)
        else:
            result = self.writer.revise(plan=plan, story=story, feedback=feedback)
        self._record(result, step=f"{label}.write_1")
        story = result["output"]

        # 3 — AI failure check
        result = self.ai_checker.run(story=story)
        self._record(result, step=f"{label}.ai_check_1")
        feedback = result["output"]

        # 2 — revise
        result = self.writer.revise(plan=plan, story=story, feedback=feedback)
        self._record(result, step=f"{label}.write_2")
        story = result["output"]

        # 4 — consistency check
        result = self.consistency.run(story=story)
        self._record(result, step=f"{label}.consistency")
        feedback = result["output"]

        # 2 — revise
        result = self.writer.revise(plan=plan, story=story, feedback=feedback)
        self._record(result, step=f"{label}.write_3")
        story = result["output"]

        # 3 — AI failure check
        result = self.ai_checker.run(story=story)
        self._record(result, step=f"{label}.ai_check_2")
        feedback = result["output"]

        # 2 — revise
        result = self.writer.revise(plan=plan, story=story, feedback=feedback)
        self._record(result, step=f"{label}.write_4")
        story = result["output"]

        return story

    # ------------------------------------------------------------------
    # Middle loop: 5 → Inner → 6 → Inner → 7 → Inner → 8 → Inner
    # ------------------------------------------------------------------
    def _run_middle(self, plan: str, story: str, target_audience: str, pass_num: int = 1) -> str:
        p = f"middle{pass_num}"

        # 5 — PeerWriter
        result = self.peer_writer.run(plan=plan, story=story)
        self._record(result, step=f"{p}.peer_writer")
        feedback = result["output"]
        story = self._run_inner(plan, story, feedback, label=f"{p}.inner_after_peer")

        # 6 — Editor
        result = self.editor.run(story=story)
        self._record(result, step=f"{p}.editor")
        feedback = result["output"]
        story = self._run_inner(plan, story, feedback, label=f"{p}.inner_after_editor")

        # 7 — Marketing
        result = self.marketing.run(story=story, target_audience=target_audience)
        self._record(result, step=f"{p}.marketing")
        feedback = result["output"]
        story = self._run_inner(plan, story, feedback, label=f"{p}.inner_after_marketing")

        # 8 — Audience
        result = self.audience.run(story=story, target_audience=target_audience)
        self._record(result, step=f"{p}.audience")
        feedback = result["output"]
        story = self._run_inner(plan, story, feedback, label=f"{p}.inner_after_audience")

        return story

    # ------------------------------------------------------------------

    def _record(self, result: dict, step: str) -> None:
        self._log.append({**result, "step": step})
