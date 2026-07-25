from constraints import check_constraint


def test_none_when_empty():
    assert check_constraint("", "some story") is None
    assert check_constraint("   ", "x") is None


def test_none_when_nothing_checkable():
    # Document-form / voice constraints are left to the reviewer, not counted.
    assert check_constraint("told as an obituary", "a body of text") is None


def test_word_count_exact_pass():
    r = check_constraint("exactly 3 words", "one two three")
    assert r["passed"] is True
    c = r["checks"][0]
    assert c["kind"] == "word_count_exact"
    assert c["target"] == 3 and c["actual"] == 3


def test_word_count_exact_fail_and_reversed_phrasing():
    r = check_constraint("200 words exactly", "one two three")
    assert r["passed"] is False
    assert r["checks"][0]["target"] == 200 and r["checks"][0]["actual"] == 3


def test_forbidden_words_found():
    r = check_constraint("forbidden words: love, death", "a story about love and war")
    assert r["passed"] is False
    assert r["checks"][0]["found"] == ["love"]


def test_forbidden_words_clean():
    r = check_constraint("banned words: love; death", "a tale of war")
    assert r["passed"] is True
    assert r["checks"][0]["found"] == []


def test_multiple_checks_combined():
    r = check_constraint("exactly 2 words, forbidden words: love", "just love")
    kinds = {c["kind"] for c in r["checks"]}
    assert kinds == {"word_count_exact", "forbidden_words"}
    assert r["passed"] is False  # 2 words passes, but "love" is forbidden
