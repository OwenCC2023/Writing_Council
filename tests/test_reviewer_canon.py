from unittest.mock import patch
from agents.consistency_agent import ConsistencyAgent, SYSTEM_PROMPT as CONS_SP
from agents.editor_agent import EditorAgent, SYSTEM_PROMPT as ED_SP
from agents.peer_writer_agent import PeerWriterAgent, SYSTEM_PROMPT as PEER_SP


def test_consistency_earth_unchanged():
    a = ConsistencyAgent()
    with patch.object(a, "_call_claude", return_value="x") as m:
        a.run(story="s")
    assert m.call_args.args[0] == CONS_SP


def test_consistency_canon_lowers_authority():
    a = ConsistencyAgent()
    with patch.object(a, "_call_claude", return_value="x") as m:
        a.run(story="s", canon_sheet="halved gravity")
    sp = m.call_args.args[0]
    assert "halved gravity" in sp and "authority" in sp.lower()


def test_peer_writer_canon_keeps_authority():
    a = PeerWriterAgent()
    with patch.object(a, "_call_claude", return_value="x") as m:
        a.run(plan="p", story="s", canon_sheet="three suns")
    sp = m.call_args.args[0]
    assert "three suns" in sp
    assert "lower your authority" not in sp.lower()   # agent 5 exempt
