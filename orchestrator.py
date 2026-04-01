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
        self._log_file = None

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
        LOGS_DIR.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        self._log_file = LOGS_DIR / f"run_{timestamp}.log"
        self._log_file.write_text("", encoding="utf-8")
        print(f"Logging to {self._log_file}")

        # 1 — PlanningAgent
        print("[outer] Running PlanningAgent...")
        input_text = (
            f"idea: {idea}\n"
            f"target_length: {target_length}\n"
            f"target_audience: {target_audience}\n"
            f"world_rules: {world_rules or '(none)'}\n"
            f"framework: {framework or '(none)'}"
        )
        self._log_start("outer.plan", "PlanningAgent", input_text)
        result = self.planner.run(
            idea=idea,
            target_length=target_length,
            target_audience=target_audience,
            world_rules=world_rules,
            framework=framework,
        )
        self._log_end(result, step="outer.plan")
        plan = result["output"]

        # Inner — fresh write
        print("[outer] Starting inner loop (fresh write)...")
        story = self._run_inner(plan, label="outer.inner")

        # Middle × 2
        print("[outer] Starting middle loop pass 1...")
        story = self._run_middle(plan, story, target_audience, pass_num=1)
        print("[outer] Starting middle loop pass 2...")
        story = self._run_middle(plan, story, target_audience, pass_num=2)

        return {"story": story, "log": list(self._log)}

    # ------------------------------------------------------------------
    # Inner loop: 2 → 3 → 2 → 4 → 2 → 3 → 2
    # ------------------------------------------------------------------
    def _run_inner(self, plan: str, story: str = None, feedback: str = None, label: str = "inner") -> str:
        # 2 — write or revise
        if story is None:
            print(f"[{label}] Running WriterAgent (initial write)...")
            self._log_start(f"{label}.write_1", "WriterAgent", f"plan:\n{plan}")
            result = self.writer.run(plan=plan)
        else:
            print(f"[{label}] Running WriterAgent (revise 1)...")
            self._log_start(f"{label}.write_1", "WriterAgent",
                            f"feedback:\n{feedback}\n\nplan:\n{plan}\n\nstory:\n{story}")
            result = self.writer.revise(plan=plan, story=story, feedback=feedback)
        self._log_end(result, step=f"{label}.write_1")
        story = result["output"]

        # 3 — AI failure check
        print(f"[{label}] Running AIFailureCheckerAgent (check 1)...")
        self._log_start(f"{label}.ai_check_1", "AIFailureCheckerAgent", f"story:\n{story}")
        result = self.ai_checker.run(story=story)
        self._log_end(result, step=f"{label}.ai_check_1")
        feedback = result["output"]

        # 2 — revise
        print(f"[{label}] Running WriterAgent (revise 2)...")
        self._log_start(f"{label}.write_2", "WriterAgent",
                        f"feedback:\n{feedback}\n\nplan:\n{plan}\n\nstory:\n{story}")
        result = self.writer.revise(plan=plan, story=story, feedback=feedback)
        self._log_end(result, step=f"{label}.write_2")
        story = result["output"]

        # 4 — consistency check
        print(f"[{label}] Running ConsistencyAgent...")
        self._log_start(f"{label}.consistency", "ConsistencyAgent", f"story:\n{story}")
        result = self.consistency.run(story=story)
        self._log_end(result, step=f"{label}.consistency")
        feedback = result["output"]

        # 2 — revise
        print(f"[{label}] Running WriterAgent (revise 3)...")
        self._log_start(f"{label}.write_3", "WriterAgent",
                        f"feedback:\n{feedback}\n\nplan:\n{plan}\n\nstory:\n{story}")
        result = self.writer.revise(plan=plan, story=story, feedback=feedback)
        self._log_end(result, step=f"{label}.write_3")
        story = result["output"]

        # 3 — AI failure check
        print(f"[{label}] Running AIFailureCheckerAgent (check 2)...")
        self._log_start(f"{label}.ai_check_2", "AIFailureCheckerAgent", f"story:\n{story}")
        result = self.ai_checker.run(story=story)
        self._log_end(result, step=f"{label}.ai_check_2")
        feedback = result["output"]

        # 2 — revise
        print(f"[{label}] Running WriterAgent (revise 4)...")
        self._log_start(f"{label}.write_4", "WriterAgent",
                        f"feedback:\n{feedback}\n\nplan:\n{plan}\n\nstory:\n{story}")
        result = self.writer.revise(plan=plan, story=story, feedback=feedback)
        self._log_end(result, step=f"{label}.write_4")
        story = result["output"]

        return story

    # ------------------------------------------------------------------
    # Middle loop: 5 → Inner → 6 → Inner → 7 → Inner → 8 → Inner
    # ------------------------------------------------------------------
    def _run_middle(self, plan: str, story: str, target_audience: str, pass_num: int = 1) -> str:
        p = f"middle{pass_num}"

        # 5 — PeerWriter
        print(f"[{p}] Running PeerWriterAgent...")
        self._log_start(f"{p}.peer_writer", "PeerWriterAgent",
                        f"plan:\n{plan}\n\nstory:\n{story}")
        result = self.peer_writer.run(plan=plan, story=story)
        self._log_end(result, step=f"{p}.peer_writer")
        feedback = result["output"]
        print(f"[{p}] Starting inner loop after PeerWriter...")
        story = self._run_inner(plan, story, feedback, label=f"{p}.inner_after_peer")

        # 6 — Editor
        print(f"[{p}] Running EditorAgent...")
        self._log_start(f"{p}.editor", "EditorAgent", f"story:\n{story}")
        result = self.editor.run(story=story)
        self._log_end(result, step=f"{p}.editor")
        feedback = result["output"]
        print(f"[{p}] Starting inner loop after Editor...")
        story = self._run_inner(plan, story, feedback, label=f"{p}.inner_after_editor")

        # 7 — Marketing
        print(f"[{p}] Running MarketingAgent...")
        self._log_start(f"{p}.marketing", "MarketingAgent",
                        f"target_audience: {target_audience}\n\nstory:\n{story}")
        result = self.marketing.run(story=story, target_audience=target_audience)
        self._log_end(result, step=f"{p}.marketing")
        feedback = result["output"]
        print(f"[{p}] Starting inner loop after Marketing...")
        story = self._run_inner(plan, story, feedback, label=f"{p}.inner_after_marketing")

        # 8 — Audience
        print(f"[{p}] Running AudienceAgent...")
        self._log_start(f"{p}.audience", "AudienceAgent",
                        f"target_audience: {target_audience}\n\nstory:\n{story}")
        result = self.audience.run(story=story, target_audience=target_audience)
        self._log_end(result, step=f"{p}.audience")
        feedback = result["output"]
        print(f"[{p}] Starting inner loop after Audience...")
        story = self._run_inner(plan, story, feedback, label=f"{p}.inner_after_audience")

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
