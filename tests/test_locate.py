"""Locate tasks — the judged half of completeness.

Two properties carry the instrument, and both are tested here. The worksheet must not leak the answer,
because the search is the measurement. And grading must be mechanical, because a grader reading free text
is a second judgement with its own variance, and the instrument would end up measuring the grader.
"""

import pytest

from locate import Response, Task, grade, load, parse, render, score


def _task(**kw):
    base = dict(id="t1", target="x", rev="r", question="Where does a duplicate get detected?",
                expects=("src/documents/checks.py",), subsystem="consumption.md",
                answer="`checks.py` compares the checksum.")
    return Task(**{**base, **kw})


# --- the worksheet must not leak the answer ---------------------------------------------------------

def test_the_worksheet_contains_no_answer():
    """The opposite of the checklist rule, and the reason this instrument exists separately from it.

    A checklist hands the judge the ground truth so it compares rather than researches. Here the search
    *is* the measurement: a judge told the module beforehand would find it confirmed in the prose and
    report success from an artifact that could never have led anyone there.
    """
    text = render([_task()], "architecture", "x")
    assert "checks.py" not in text
    assert "compares the checksum" not in text
    assert "Where does a duplicate get detected?" in text


def test_the_worksheet_invites_a_not_found_answer():
    text = render([_task()], "architecture", "x")
    assert "NOT FOUND" in text


# --- grading ----------------------------------------------------------------------------------------

def test_naming_the_module_is_located():
    r = Response("t1", where="`src/documents/checks.py`", document="consumption.md")
    assert grade(_task(), r).verdict == "located"


def test_naming_the_module_by_stem_is_located():
    """Documents refer to a module by its bare name constantly, and a reader who arrives at `checks` has
    arrived."""
    assert grade(_task(), Response("t1", where="the checks module")).verdict == "located"


def test_naming_only_the_document_is_partial():
    """A reader who reaches the right document and cannot find the mechanism has been helped, and not
    enough. Half credit says both halves of that."""
    r = Response("t1", where="somewhere in ingestion", document="consumption.md")
    g = grade(_task(), r)
    assert g.verdict == "partial" and g.credit == 0.5


def test_an_answer_that_reaches_neither_is_lost():
    assert grade(_task(), Response("t1", where="the database layer")).verdict == "lost"


def test_not_found_is_lost_and_is_a_real_answer():
    """`NOT FOUND` is the honest result for a document that cannot lead anywhere, and the worksheet asks
    for it rather than for a guess."""
    tasks = [_task()]
    r = parse("## t1\n\n```\nwhere: NOT FOUND\ndocument:\nwhy: I looked at index and consumption.\n```\n",
              tasks)
    assert r["t1"].unanswered
    assert grade(tasks[0], r["t1"]).verdict == "lost"


def test_a_short_stem_does_not_match_by_accident():
    """`described.py` learned this the hard way: a substring test let a module named `a.py` match the
    letter "a" inside "named"."""
    t = _task(expects=("src/app/a.py",), subsystem="")
    assert grade(t, Response("t1", where="somewhere in the frontend, named oddly")).verdict == "lost"


def test_the_matched_token_is_recorded():
    """A verdict a reader cannot audit is a verdict they have to trust."""
    g = grade(_task(), Response("t1", where="see `src/documents/checks.py`"))
    assert g.matched == "src/documents/checks.py"


# --- scoring ----------------------------------------------------------------------------------------

def test_findability_gives_half_credit_for_partial():
    tasks = [_task(id="a"), _task(id="b"), _task(id="c")]
    responses = {"a": Response("a", where="src/documents/checks.py"),
                 "b": Response("b", where="?", document="consumption.md"),
                 "c": Response("c", where="no idea", unanswered=True)}
    s = score(tasks, responses)
    assert s.by_verdict() == {"located": 1, "partial": 1, "lost": 1}
    assert s.findability == pytest.approx(0.5)


def test_severity_weights_the_score():
    tasks = [_task(id="a", severity="serious"), _task(id="b", severity="minor")]
    responses = {"a": Response("a", where="nowhere"), "b": Response("b", where="src/documents/checks.py")}
    s = score(tasks, responses)
    assert s.findability == pytest.approx(0.5)
    assert s.weighted == pytest.approx(1 / 4)      # minor found (1), serious lost (0), over 3+1


def test_an_unanswered_worksheet_does_not_score_perfect():
    assert score([_task()], {}).findability is None


def test_a_skipped_task_is_reported_not_dropped():
    s = score([_task(id="a"), _task(id="b")], {"a": Response("a", where="src/documents/checks.py")})
    assert s.skipped == ["b"] and s.answered == 1


# --- round-tripping ---------------------------------------------------------------------------------

def test_a_task_file_round_trips(tmp_path):
    f = tmp_path / "tasks.toml"
    f.write_text(
        '[[task]]\nid = "t1"\ntarget = "x"\nrev = "r"\n'
        'question = "Where does X happen?"\nexpects = ["src/a/b.py", "src/a/c.py"]\n'
        'subsystem = "s.md"\nanswer = "in b.py"\nseverity = "serious"\n')
    (t,) = load(f)
    assert t.expects == ("src/a/b.py", "src/a/c.py") and t.severity == "serious"


def test_a_multi_line_answer_survives_parsing():
    tasks = [_task()]
    text = ("## t1\n\n```\nwhere: `checks.py`\ndocument: consumption.md, the\nIngestion section\n"
            "why: it says the checksum is compared\nbefore the plugin chain runs\n```\n")
    r = parse(text, tasks)["t1"]
    assert "Ingestion section" in r.document and "plugin chain" in r.why
