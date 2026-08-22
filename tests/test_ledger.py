"""The evaluation ledger — mostly tests that it refuses things.

Storing rows is the easy half and barely worth testing. The half that earns the file is the refusal: a
ledger that will average a mean from a four-criterion brief with one from a six-criterion brief produces a
number that looks like a trend and is a property of the table. That is the same shape as `check` printing
"All invariants hold" having checked none of them, and this project has hit it enough times to test for it
directly.
"""

import pytest

from ledger import COLUMNS, Row, compare, load, save, validate


def _row(**kw):
    base = dict(run_id="r1", date="2026-08-16", archagent_commit="abc1234",
                target_url="https://github.com/x/y", target_commit="deadbee", target_fresh="yes",
                run_kind="calibration", generating_model="opus", judge_model="opus",
                rubric_version="brief-v3", judged_mean="3.5")
    return Row(**{**base, **kw})


# --- what it refuses to store ---------------------------------------------------------------------

def test_a_duplicate_run_id_is_refused():
    assert any("already in the ledger" in b for b in validate(_row(), [_row()]))

def test_an_unpinned_target_is_refused():
    """A target is a repository *at a revision*. A row naming only the repository can neither be
    reproduced nor compared with anything, and it looks exactly like a row that can."""
    assert any("target_commit" in b for b in validate(_row(target_commit=""), []))
    assert any("target_commit" in b for b in validate(_row(target_commit="unknown"), []))

def test_an_unknown_run_kind_is_refused():
    assert any("run_kind" in b for b in validate(_row(run_kind="vibes"), []))

def test_a_predecessor_that_is_not_in_the_ledger_is_refused():
    """An update evaluation is two runs and a link between them (§16). A dangling link is a chain that
    silently starts in the middle."""
    assert any("predecessor" in b for b in validate(_row(predecessor_run_id="nope"), []))
    assert not validate(_row(run_id="r2", predecessor_run_id="r1"), [_row()])

def test_a_row_with_no_scores_is_accepted():
    """Deliberately lenient here. A run that partly failed is worth recording; strictness about scores
    would push the failures out of the record, which is where they matter most."""
    assert validate(_row(judged_mean="", deterministic_score=""), []) == []


# --- what it refuses to compare -------------------------------------------------------------------

def test_rows_from_different_rubric_versions_are_not_a_trend():
    """The mistake this file exists to prevent. The first three calibration rounds scored 3.0, 4.0 and
    4.17 — a clean rising line, across three different review briefs, and nothing recorded that."""
    c = compare([_row(run_id="a", rubric_version="brief-v1"),
                 _row(run_id="b", rubric_version="brief-v2")], "judged_mean")
    assert c.differs_on == ["rubric_version"] and not c.sound

def test_rows_from_different_judges_are_not_a_trend():
    c = compare([_row(run_id="a", judge_model="opus"),
                 _row(run_id="b", judge_model="sonnet")], "judged_mean")
    assert c.differs_on == ["judge_model"] and not c.sound

def test_an_unrecorded_key_is_a_caveat_not_a_refusal():
    """The distinction that makes the ledger usable at all. Nobody wrote down which model generated the
    obstudio artifact and that is unrecoverable — excluding those rows would throw away the only history
    there is, while presenting them as sound would turn an unknown into a trend."""
    c = compare([_row(run_id="a", generating_model="unknown"),
                 _row(run_id="b", generating_model="unknown")], "judged_mean")
    assert c.unverifiable_on == ["generating_model"]
    assert c.differs_on == [] and c.sound          # shown, with the gap named

def test_a_key_that_is_unknown_on_one_row_and_differs_on_others_is_both():
    c = compare([_row(run_id="a", judge_model="unknown"),
                 _row(run_id="b", judge_model="opus"),
                 _row(run_id="c", judge_model="sonnet")], "judged_mean")
    assert c.unverifiable_on == ["judge_model"] and c.differs_on == ["judge_model"]

def test_rows_missing_the_metric_are_excluded_and_named():
    c = compare([_row(run_id="a"), _row(run_id="b", judged_mean="")], "judged_mean")
    assert len(c.rows) == 1 and c.excluded[0][0].run_id == "b"

def test_a_comparison_over_nothing_is_not_sound():
    """An empty selection must not read as agreement. Same rule as the checklist scorer refusing to call
    an unanswered worksheet perfect."""
    assert not compare([], "judged_mean").sound
    assert not compare([_row(judged_mean="")], "judged_mean").sound


# --- round-tripping -------------------------------------------------------------------------------

def test_rows_survive_a_write_and_a_read(tmp_path):
    p = tmp_path / "ledger.csv"
    save(p, [_row(run_id="a", notes="a note, with a comma\nand a newline")])
    back = load(p)
    assert len(back) == 1 and back[0].notes == "a note, with a comma\nand a newline"

def test_a_missing_ledger_reads_as_empty_not_an_error(tmp_path):
    assert load(tmp_path / "nope.csv") == []

def test_a_drifted_schema_fails_loudly(tmp_path):
    """A CSV read under the wrong header does not error — it produces plausible rows with values in the
    wrong columns, which is the worst available outcome for a file whose purpose is comparison."""
    p = tmp_path / "ledger.csv"
    p.write_text("run_id,date\nr1,2026-08-16\n")
    with pytest.raises(ValueError, match="schema mismatch"):
        load(p)


# --- the ledger on record -------------------------------------------------------------------------

def _real():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from evalhome import eval_home
    return eval_home() / "ledger.csv"


@pytest.mark.skipif(not _real().is_file(), reason="no evaluation data repo — set ARCHAGENT_EVAL_HOME")
def test_the_real_ledger_loads_and_every_row_is_valid():
    rows = load(_real())
    assert rows
    for i, r in enumerate(rows):
        assert validate(r, rows[:i]) == [], f"{r.run_id}: {validate(r, rows[:i])}"


@pytest.mark.skipif(not _real().is_file(), reason="no evaluation data repo — set ARCHAGENT_EVAL_HOME")
def test_the_three_calibration_means_are_not_offered_as_a_series():
    """A live check on the real data, not a fixture. 3.0 → 4.0 → 4.17 across the three calibration rounds
    is the most tempting series in the record and the least valid one."""
    rows = [r for r in load(_real()) if r.run_kind == "calibration" and r.judge_model == "human"]
    assert len(rows) >= 3
    assert compare(rows, "judged_mean").differs_on == ["rubric_version"]


# --- two archagents in one run (issue #13) ----------------------------------------------------------

def test_a_run_reviewed_against_a_different_build_says_so():
    """Round 4's row. The artifact was generated by the working tree and reviewed against a build six
    weeks older that was missing four of the commands `describe` tells agents to run. The problem was not
    that they differed — it was that nothing recorded it, so a reviewer reasonably read a missing command
    as a stale document."""
    from ledger import tool_skew
    r = _row(archagent_commit="53c8c23", reviewing_tool="0.2.0-or-earlier")
    assert "53c8c23" in tool_skew(r) and "0.2.0-or-earlier" in tool_skew(r)


def test_the_same_build_on_both_sides_is_silent():
    from ledger import tool_skew
    assert tool_skew(_row(archagent_commit="abc1234", reviewing_tool="abc1234")) == ""


def test_a_run_with_no_review_is_silent():
    """A scoring run has no reviewer, and an empty column there means not applicable rather than lost."""
    from ledger import tool_skew
    assert tool_skew(_row(archagent_commit="abc1234", reviewing_tool="")) == ""


def test_the_reviewing_tool_is_not_a_comparability_key():
    """Two rows reviewed against different builds are still comparable — the scores are the artifact's,
    not the reviewing tool's. It is recorded to be legible, not to gate."""
    from ledger import COMPARABILITY_KEYS, compare
    assert "reviewing_tool" not in COMPARABILITY_KEYS
    c = compare([_row(run_id="a", reviewing_tool="x"), _row(run_id="b", reviewing_tool="y")],
                "judged_mean")
    assert c.sound
