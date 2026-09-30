"""Replay the analysis calls from a run log at several effort levels.

Every run log holds each agent's output, and those outputs are the inputs of the
calls that follow them: the latest WriterAgent output is the story, the latest
plan output is the plan, the checker outputs are plan_revision's feedbacks. So
the four analysis calls (Variance, Sensory, plan_revision, plan_revision_prose)
can be re-run on byte-identical inputs at `low` and `medium`, and the only
difference between the two outputs is the effort level. Two full council runs
would differ in their drafts too.

    python replay_effort.py logs/run_X.log            # dry run: list what would run
    python replay_effort.py logs/run_X.log --run      # billed: replay and write a report

Only the first occurrence of each call kind is replayed unless --per-kind says
otherwise. Sensory is replayed only on the first checker fan-out after the initial
write: later fan-outs may pass the checkers only the sections the writer touched,
and the log does not record which.
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

from orchestrator import WritingCouncil

_DIVIDER = "=" * 80
_OUTPUT_MARK = re.compile(r"^--- OUTPUT \(completed [^)]*\) ---$")

PLAN_STEPS = ("plan", "plan_bible_revision", "plan_length_fix")
KINDS = ("plan_revision_1", "plan_revision_2", "sensory", "variance", "prose_plan_revision")


def parse_log(text: str) -> list:
    """Return [(step, agent, output)] in the order outputs were written.

    Parallel steps write all their headers first and their outputs afterwards, in
    the same order, so each output belongs to the oldest header still waiting.
    """
    lines = text.splitlines()
    pending, entries = [], []
    i = 0
    while i < len(lines):
        line = lines[i]
        if line == _DIVIDER and i + 2 < len(lines) and lines[i + 1].startswith("STEP:"):
            step = lines[i + 1].split(":", 1)[1].strip()
            agent = lines[i + 2].split(":", 1)[1].strip()
            pending.append((step, agent))
            i += 3
            while i < len(lines) and lines[i] != _DIVIDER:
                i += 1
            i += 1
            continue
        if _OUTPUT_MARK.match(line):
            body = []
            i += 1
            while (i < len(lines) and lines[i] != _DIVIDER
                   and not _OUTPUT_MARK.match(lines[i])):
                body.append(lines[i])
                i += 1
            if pending:
                step, agent = pending.pop(0)
                entries.append((step, agent, "\n".join(body).strip()))
            continue
        i += 1
    return entries


def _leaf(step: str) -> str:
    return step.rsplit(".", 1)[-1]


def build_jobs(entries: list, per_kind: int = 1, top_n: int = 5) -> list:
    """Walk the log, tracking story / plan / canon, and emit one job per replayable
    call: {kind, step, logged, call: (method_name, kwargs)}."""
    from agents.world_builder_agent import WorldBuilderAgent

    story, plan, canon = None, None, ""
    writes_seen = 0
    since_write = {}  # leaf step -> output, for checker outputs since the last write
    middle = {}
    counts = {k: 0 for k in KINDS}
    jobs = []

    def want(kind):
        return counts[kind] < per_kind

    for step, agent, output in entries:
        leaf = _leaf(step)
        if agent == "WriterAgent":
            story = output
            writes_seen += 1
            since_write = {}
            continue
        if agent == "PlanningAgent" and leaf in PLAN_STEPS:
            _, plan = WritingCouncil._parse_world_class(output)
            continue
        if agent == "WorldBuilderAgent":
            canon, _ = WorldBuilderAgent._split(output)
            continue
        if step.startswith("middle.") and step.count(".") == 1:
            middle[leaf] = output
            continue
        since_write[leaf] = output
        if story is None or plan is None:
            continue  # seeded revise run: the sectionized draft is not logged

        if leaf == "plan_revision_1" and want("plan_revision_1"):
            feedbacks = [middle.get(k, "") for k in
                         ("peer_writer", "editor", "marketing", "audience")]
            jobs.append({"kind": "plan_revision_1", "step": step, "logged": output,
                         "call": ("planner", "plan_revision",
                                  dict(story=story, plan=plan, feedbacks=feedbacks,
                                       canon_aware=bool(canon)))})
            counts["plan_revision_1"] += 1
        elif leaf == "plan_revision_2" and want("plan_revision_2"):
            feedbacks = [since_write[k] for k in
                         ("consistency", "ai_check", "engine", "strangeness", "sensory")
                         if k in since_write]
            jobs.append({"kind": "plan_revision_2", "step": step, "logged": output,
                         "call": ("planner", "plan_revision",
                                  dict(story=story, plan=plan, feedbacks=feedbacks,
                                       canon_aware=bool(canon)))})
            counts["plan_revision_2"] += 1
        elif leaf == "sensory" and writes_seen == 1 and want("sensory"):
            jobs.append({"kind": "sensory", "step": step, "logged": output,
                         "call": ("sensory", "run", dict(story=story, canon_sheet=canon))})
            counts["sensory"] += 1
        elif leaf == "variance" and want("variance"):
            jobs.append({"kind": "variance", "step": step, "logged": output,
                         "call": ("variance", "run",
                                  dict(story=story, top_n=top_n, canon_sheet=canon))})
            counts["variance"] += 1
        elif (step.startswith("prose.") and leaf == "plan_revision"
              and want("prose_plan_revision")):
            jobs.append({"kind": "prose_plan_revision", "step": step, "logged": output,
                         "call": ("planner", "plan_revision_prose",
                                  dict(story=story, plan=plan,
                                       prose_feedback=since_write.get("prose_check", ""),
                                       consistency_feedback=since_write.get("consistency", ""),
                                       canon_aware=bool(canon),
                                       variance_feedback=since_write.get("variance", "")))})
            counts["prose_plan_revision"] += 1
    return jobs


def _make_agents():
    from agents.planning_agent import PlanningAgent
    from agents.sensory_agent import SensoryQuotaAgent
    from agents.variance_agent import VarianceReviewerAgent
    return {"planner": PlanningAgent(), "sensory": SensoryQuotaAgent(),
            "variance": VarianceReviewerAgent()}


def replay(job: dict, agents: dict, effort: str) -> dict:
    """Run one job at a forced effort; return output plus token usage."""
    name, method, kwargs = job["call"]
    agent = agents[name]
    usage = {}
    orig_call, orig_first = agent._call_claude, agent._first_text

    def forced(*a, **kw):
        return orig_call(*a, **{**kw, "effort": effort})

    def recording(response):
        u = getattr(response, "usage", None)
        usage["input"] = getattr(u, "input_tokens", None)
        usage["output"] = getattr(u, "output_tokens", None)
        return orig_first(response)

    agent._call_claude, agent._first_text = forced, recording
    try:
        started = datetime.now()
        output = getattr(agent, method)(**kwargs)["output"]
        seconds = (datetime.now() - started).total_seconds()
    finally:
        del agent._call_claude, agent._first_text
    return {"output": output, "usage": usage, "seconds": seconds}


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("log", type=Path)
    ap.add_argument("--run", action="store_true", help="make the billed API calls")
    ap.add_argument("--efforts", nargs="+", default=["low", "medium"])
    ap.add_argument("--per-kind", type=int, default=1)
    ap.add_argument("--kinds", nargs="+", choices=KINDS, default=list(KINDS))
    ap.add_argument("--top-n", type=int, default=5)
    ap.add_argument("--out", type=Path, default=Path("logs"))
    args = ap.parse_args(argv)

    jobs = build_jobs(parse_log(args.log.read_text(encoding="utf-8")),
                      per_kind=args.per_kind, top_n=args.top_n)
    jobs = [j for j in jobs if j["kind"] in args.kinds]
    print(f"{len(jobs)} replayable call(s) in {args.log.name}, "
          f"x {len(args.efforts)} effort level(s) = {len(jobs) * len(args.efforts)} API calls")
    for job in jobs:
        print(f"  {job['kind']:<20} {job['step']}")
    missing = [k for k in args.kinds if k not in {j["kind"] for j in jobs}]
    if missing:
        print(f"  not in this log: {', '.join(missing)}")
    if not args.run or not jobs:
        if not args.run:
            print("Dry run. Add --run to make the calls (billed).")
        return

    agents = _make_agents()
    args.out.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report = args.out / f"effort_replay_{args.log.stem}_{stamp}.md"
    summary = []
    with report.open("w", encoding="utf-8") as f:
        f.write(f"# Effort replay: {args.log.name}\n\n"
                f"Same inputs, efforts {', '.join(args.efforts)}. "
                f"The logged output was produced by whatever model/settings that run used.\n\n")
        for job in jobs:
            f.write(f"\n\n---\n\n## {job['kind']} ({job['step']})\n")
            for effort in args.efforts:
                print(f"[replay] {job['kind']} at {effort}...", flush=True)
                try:
                    r = replay(job, agents, effort)
                except Exception as exc:  # keep the other comparisons
                    print(f"[replay]   failed: {exc}")
                    f.write(f"\n### effort: {effort}\n\nFAILED: {exc}\n")
                    summary.append((job["kind"], effort, "-", "-", "failed"))
                    continue
                u = r["usage"]
                f.write(f"\n### effort: {effort}  "
                        f"(output tokens {u.get('output')}, input {u.get('input')}, "
                        f"{r['seconds']:.0f}s)\n\n{r['output']}\n")
                summary.append((job["kind"], effort, u.get("output"), u.get("input"),
                                f"{r['seconds']:.0f}s"))
            f.write(f"\n### logged output (original run)\n\n{job['logged']}\n")
        f.write("\n\n---\n\n## Token summary\n\n| call | effort | output tokens | "
                "input tokens | time |\n|---|---|---|---|---|\n")
        for row in summary:
            f.write("| " + " | ".join(str(c) for c in row) + " |\n")
    print(f"Report: {report}")


if __name__ == "__main__":
    sys.exit(main())
