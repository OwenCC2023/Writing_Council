import replay_effort as r

D = "=" * 80


def _header(step, agent):
    return f"{D}\nSTEP:   {step}\nAGENT:  {agent}\nSTART:  10:00:00\n{D}\n"


def _out(text):
    return f"--- OUTPUT (completed 10:01:00) ---\n{text}\n\n"


LOG = (
    _header("outer.inner.plan", "PlanningAgent")
    + _out("<<<WORLD_CLASS: SECONDARY>>>\nTHE PLAN")
    + _header("outer.inner.world_builder", "WorldBuilderAgent")
    + _out("=== CANON SHEET ===\nRULE A")
    + _header("outer.inner.write_1", "WriterAgent")
    + _out("<<<SECTION 1>>>\nDRAFT ONE")
    # Parallel: all headers first, outputs afterwards in the same order.
    + _header("outer.inner.consistency", "ConsistencyAgent")
    + _header("outer.inner.ai_check", "AIFailureCheckerAgent")
    + _header("outer.inner.engine", "EngineReviewerAgent")
    + _header("outer.inner.strangeness", "StrangenessReviewerAgent")
    + _header("outer.inner.sensory", "SensoryQuotaAgent")
    + _out("CONS") + _out("AI") + _out("ENG") + _out("STR") + _out("SEN")
    + _header("outer.inner.plan_revision_2", "PlanningAgent")
    + _out("REV PLAN")
    + _header("outer.inner.write_2", "WriterAgent")
    + _out("<<<SECTION 1>>>\nDRAFT TWO")
    + _header("prose.1.consistency", "ConsistencyAgent")
    + _header("prose.1.prose_check", "AIFailureCheckerAgent")
    + _header("prose.1.variance", "VarianceReviewerAgent")
    + _out("P-CONS") + _out("P-AI") + _out("VAR")
    + _header("prose.1.plan_revision", "PlanningAgent")
    + _out("PROSE PLAN")
)


def test_parallel_outputs_map_to_their_headers_in_order():
    entries = r.parse_log(LOG)
    by_step = {step: out for step, _, out in entries}
    assert by_step["outer.inner.ai_check"] == "AI"
    assert by_step["outer.inner.sensory"] == "SEN"
    assert by_step["prose.1.variance"] == "VAR"


def test_jobs_rebuild_the_inputs_each_call_received():
    jobs = {j["kind"]: j for j in r.build_jobs(r.parse_log(LOG))}
    assert set(jobs) == {"sensory", "plan_revision_2", "variance", "prose_plan_revision"}

    _, method, kw = jobs["plan_revision_2"]["call"]
    assert method == "plan_revision"
    assert kw["feedbacks"] == ["CONS", "AI", "ENG", "STR", "SEN"]
    assert kw["story"] == "<<<SECTION 1>>>\nDRAFT ONE"
    assert "WORLD_CLASS" not in kw["plan"] and "THE PLAN" in kw["plan"]
    assert kw["canon_aware"] is True

    _, _, kw = jobs["variance"]["call"]
    assert kw["story"] == "<<<SECTION 1>>>\nDRAFT TWO"
    assert kw["canon_sheet"] == "RULE A"

    _, _, kw = jobs["prose_plan_revision"]["call"]
    assert (kw["prose_feedback"], kw["consistency_feedback"], kw["variance_feedback"]) == \
        ("P-AI", "P-CONS", "VAR")
    assert jobs["prose_plan_revision"]["logged"] == "PROSE PLAN"


def test_sensory_after_a_revise_is_skipped():
    """Later fan-outs may see only the touched sections; the log doesn't say which."""
    log = LOG + (_header("outer.inner.sensory", "SensoryQuotaAgent") + _out("SEN2"))
    jobs = r.build_jobs(r.parse_log(log), per_kind=5)
    assert [j["logged"] for j in jobs if j["kind"] == "sensory"] == ["SEN"]


def test_dry_run_makes_no_calls(tmp_path, capsys, monkeypatch):
    log = tmp_path / "run.log"
    log.write_text(LOG, encoding="utf-8")
    monkeypatch.setattr(r, "_make_agents", lambda: (_ for _ in ()).throw(AssertionError))
    r.main([str(log)])
    assert "Dry run" in capsys.readouterr().out
