"""Capturing and checking `evaluate` output — mostly tests that it refuses to overclaim.

Storing findings is the easy half. The half worth testing is everything that decides whether a later
reader is misled: a silence that reads as health, a determinism claim on a run that never repeated, a
subsystem name reported as a missing file.
"""

import pytest

from findings import (Capture, Problem, check, inactive_conflicts, load, nondeterminism, save,
                      silences, unresolved_subjects)


def _cap(**kw):
    base = dict(repo="demo", target_rev="v1.0", archagent="archagent 0.3.0 · commit abc1234",
                captured_at="2026-08-22", findings=[], inactive=[])
    return Capture(**{**base, **kw})


def _f(sign="god-component", subjects=None, fid=None):
    subjects = subjects or ["cli"]
    return {"sign": sign, "group": "C", "severity": "med", "title": sign, "subjects": subjects,
            "detail": "", "recommendation": "", "id": fid or f"{sign}:{subjects[0]}:deadbeef"}


# --- subjects that are and are not claims about the filesystem --------------------------------------

def test_a_finding_naming_a_missing_file_is_reported(tmp_path):
    cap = _cap(findings=[_f(sign="change-prone-file", subjects=["src/gone.py"])])
    assert unresolved_subjects(cap, tmp_path)[0].kind == "unresolved-subject"


def test_a_finding_naming_a_file_that_exists_is_silent(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "there.py").write_text("x = 1\n")
    cap = _cap(findings=[_f(sign="change-prone-file", subjects=["src/there.py"])])
    assert unresolved_subjects(cap, tmp_path) == []


def test_a_subsystem_name_is_not_reported_as_a_missing_file(tmp_path):
    """The false positive `drift` needed two rounds to stop producing. Most subjects are subsystem or
    service names, and a name that was never a path is not a dangling reference."""
    cap = _cap(findings=[_f(sign="god-component", subjects=["invariant-pipeline"]),
                         _f(sign="layer-inversion", subjects=["extraction", "drift"])])
    assert unresolved_subjects(cap, tmp_path) == []


def test_a_dotted_service_name_is_not_read_as_a_path(tmp_path):
    """`api.orders` is a service, not a file, and no extension in the list matches it."""
    cap = _cap(findings=[_f(sign="service-intimacy", subjects=["api.orders"])])
    assert unresolved_subjects(cap, tmp_path) == []


# --- determinism ------------------------------------------------------------------------------------

def test_two_identical_runs_agree():
    a, b = _cap(findings=[_f()]), _cap(findings=[_f()])
    assert nondeterminism(a, b) == []


def test_a_finding_that_appears_only_in_one_run_is_reported():
    a = _cap(findings=[_f(fid="a:x:1"), _f(fid="b:y:2")])
    b = _cap(findings=[_f(fid="a:x:1")])
    problems = nondeterminism(a, b)
    assert len(problems) == 1 and problems[0].finding_id == "b:y:2"


def test_captures_of_different_revisions_refuse_to_be_compared():
    """Not a determinism failure — a category error. Reporting it as flakiness would send someone
    hunting a bug that is not there."""
    p = nondeterminism(_cap(target_rev="v1.0"), _cap(target_rev="v1.1"))
    assert len(p) == 1 and "different revisions" in p[0].detail


def test_a_report_says_so_when_determinism_was_not_checked(tmp_path):
    """A second capture costs a full run on a large repo, so skipping it is legitimate. Silently
    omitting the line is not: an absent caveat reads as a passed check."""
    r = check(_cap(), tmp_path)
    assert not r.checked_determinism and "determinism not checked" in r.summary()


# --- the coverage report must not contradict the findings -------------------------------------------

def test_a_reported_sign_listed_as_inactive_is_a_conflict():
    """This actually happened: the git-history entry named the whole of family F while
    `enum-value-escape` — a pure code scan needing no git — produced a finding in the same run."""
    cap = _cap(findings=[_f(sign="enum-value-escape")],
               inactive=[{"family": "F — git history", "reason": "--no-history",
                          "signs": ["scattered-source-of-truth", "enum-value-escape"]}])
    assert len(inactive_conflicts(cap)) == 1


def test_a_degraded_family_with_no_signs_is_not_a_conflict():
    """`E — bug-fix weighting` still emits `change-prone-file`, ranked on total churn. `signs` is empty
    there on purpose, and treating an empty list as "all of them" would flag every degraded run."""
    cap = _cap(findings=[_f(sign="change-prone-file")],
               inactive=[{"family": "E — bug-fix weighting", "reason": "no convention learned",
                          "signs": []}])
    assert inactive_conflicts(cap) == []


# --- silence is recorded, and is not a defect -------------------------------------------------------

def test_an_inactive_family_is_recorded_but_is_not_a_problem(tmp_path):
    """Group A on a single-service repo is correct behaviour. It is recorded because unrecorded silence
    reaches a later reader as health."""
    cap = _cap(inactive=[{"family": "A — data & source-of-truth", "reason": "needs **Service:** on >=2 "
                                                                           "subsystems (0 declared)",
                          "signs": ["shared-persistency"]}])
    r = check(cap, tmp_path)
    assert r.clean                       # not a defect
    assert len(r.silent) == 1 and "Service" in r.silent[0]


def test_silences_names_the_reason_not_just_the_family():
    """"A was inactive" is not actionable; "A needs **Service:** on two subsystems" is."""
    cap = _cap(inactive=[{"family": "A", "reason": "needs **Service:**", "signs": []}])
    assert silences(cap) == ["A — needs **Service:**"]


# --- provenance -------------------------------------------------------------------------------------

def test_a_capture_records_the_archagent_that_produced_it():
    """For findings the tool build is a comparability key, which is the reverse of the artifact scores.
    An artifact is the model's output; findings are the tool's, so a threshold change makes two sets
    incomparable with identical models on both sides."""
    assert "0.3.0" in _cap().archagent


def test_an_unpinned_capture_is_refused(tmp_path):
    """Same rule the ledger applies to `target_commit`: a finding set that cannot be pinned can neither
    be reproduced nor compared, and looks exactly like one that can."""
    from findings import _rev_or_die
    with pytest.raises(ValueError, match="cannot be pinned"):
        _rev_or_die(tmp_path, None)


def test_a_capture_survives_a_write_and_a_read(tmp_path):
    cap = _cap(findings=[_f()], cautions=["history is bounded to v1.0 but the tree is newer"])
    back = load(save(tmp_path / "c.json", cap))
    assert back.ids == cap.ids and back.cautions == cap.cautions


# --- against this repository ------------------------------------------------------------------------

def test_capturing_this_repo_produces_findings_that_all_resolve():
    """A live check on real output rather than a fixture. If `capture` silently returned nothing, every
    test above would still pass and the instrument would be measuring an empty list forever."""
    from pathlib import Path

    from findings import capture
    root = Path(__file__).resolve().parents[1]
    cap = capture(root, repo="archagent", archagent="test", captured_at="2026-08-22")
    assert cap.findings, "evaluate produced nothing on archagent itself — the capture is not wired up"
    assert unresolved_subjects(cap, root) == []
