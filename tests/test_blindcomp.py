"""Blind comparison — the mechanics that decide whether the comparison is fair."""

from pathlib import Path

import pytest

from blindcomp import (
    ARMS, Blinded, blind, build_input, dismissed_items, judged_dismissed, load_truth, score_objective,
    tells, unblind,
)

TRUTH = load_truth(Path(__file__).parent / "blindcomp_truth.toml")
BACKENDS = next(t for t in TRUTH if t.repo == "django")
PROVIDERS = next(t for t in TRUTH if "main.py" in t.subject)


# --- identical inputs -------------------------------------------------------------------------

def test_every_arm_receives_a_byte_identical_payload():
    """If the arms differ in their input, the comparison measures the input."""
    a = build_input([{"sign": "x", "subjects": ["a.py"]}], "repo")
    b = build_input([{"sign": "x", "subjects": ["a.py"]}], "repo")
    assert a["digest"] == b["digest"]


def test_a_different_payload_produces_a_different_digest():
    a = build_input([{"sign": "x", "subjects": ["a.py"]}], "repo")
    b = build_input([{"sign": "x", "subjects": ["b.py"]}], "repo")
    assert a["digest"] != b["digest"]


# --- blinding ---------------------------------------------------------------------------------

def test_blinding_separates_the_reports_from_which_arm_wrote_them():
    reports = {"A": "alpha report", "B": "beta report", "C": "gamma report"}
    blinded, manifest = blind(reports)
    assert {b.opaque for b in blinded} == {"report-1", "report-2", "report-3"}
    assert sorted(manifest.values()) == ["A", "B", "C"]
    assert all(b.opaque not in b.text for b in blinded)


def test_blinding_actually_shuffles():
    reports = {arm: f"{arm} text" for arm in ARMS}
    _, manifest = blind(reports, seed=7)
    assert list(manifest.values()) != ["A", "B", "C"], "seed 7 should not be the identity ordering"


def test_blinding_is_reproducible():
    reports = {arm: f"{arm} text" for arm in ARMS}
    assert blind(reports, seed=3)[1] == blind(reports, seed=3)[1]


def test_tells_catch_phrases_that_identify_an_arm():
    assert "group letter" in tells("This is a Group F finding")
    assert "internal sign name" in tells("the scattered-source-of-truth signal")
    assert "confidence tier" in tells("reported at low confidence")
    assert tells("The oracle backend branches on field types by design.") == []


# --- ground truth -------------------------------------------------------------------------------

def test_a_dismissal_near_the_finding_counts():
    text = ("## Database backends\n\nThe per-backend operations classes branch on the same field types "
            "by design — this is intended polymorphism, dismissed.")
    assert judged_dismissed(text, BACKENDS, TRUTH)


def test_a_dismissal_elsewhere_does_not_count_as_dismissing_this_one():
    """A report that dismisses something on page one and merely mentions this on page four has not
    dismissed this one."""
    text = ("We dismissed the keyboard-handling cluster as intended.\n\n" + ("filler. " * 400) +
            "\n\nSeparately, django/db/backends/oracle/operations.py duplicates the field-type set and "
            "should be consolidated.")
    assert not judged_dismissed(text, BACKENDS, TRUTH)


def test_scoring_rewards_dismissing_the_intended_family():
    report = Blinded("report-1",
                     "django/db/backends/oracle/operations.py — per-backend polymorphism, by design, "
                     "dismissed. litellm/main.py — a real provider list duplicated across five files, "
                     "consolidate. get_supported_openai_params.py — the same decision again, real.")
    s = score_objective(report, TRUTH, n_findings=6)
    assert s.ground_truth_correct == 3 and s.missed == []


def test_scoring_penalises_confirming_the_intended_family():
    """The failure mode the guidance exists to prevent: treating a designed family as a defect."""
    report = Blinded("report-1",
                     "django/db/backends/oracle/operations.py duplicates the field-type set across "
                     "backends and must be refactored urgently. litellm/main.py — real duplication. "
                     "get_supported_openai_params.py — real duplication.")
    s = score_objective(report, TRUTH, n_findings=6)
    assert s.ground_truth_correct == 2
    assert any("oracle/operations.py" in m for m in s.missed)


def test_a_dismissal_is_attributed_to_the_nearest_finding_not_every_nearby_one():
    """The failure this replaced: in a short report one dismissal sat within the window of all three
    findings and was credited against each."""
    text = ("django/db/backends/oracle/operations.py — per-backend polymorphism, by design, dismissed. "
            "litellm/main.py — a real provider list duplicated across five files, consolidate it.")
    assert dismissed_items(text, TRUTH) == {BACKENDS.finding_id}


def test_a_finding_never_mentioned_is_missed_not_credited():
    s = score_objective(Blinded("report-1", "Nothing to report."), TRUTH, n_findings=6)
    assert s.ground_truth_correct == 0 and len(s.missed) == 3


# --- report hygiene -------------------------------------------------------------------------------

def test_evidence_citation_requires_real_file_references():
    cited = Blinded("r", "See src/a.py:12, src/b.py and pkg/c.ts:44 for the pattern.")
    bare = Blinded("r", "Several files are affected by this pattern.")
    assert score_objective(cited, [], 3).cites_evidence
    assert not score_objective(bare, [], 3).cites_evidence


def test_a_heading_per_finding_does_not_count_as_clustered():
    per_finding = Blinded("r", "\n".join(f"## Finding {i}\ntext" for i in range(6)))
    clustered = Blinded("r", "## One root cause\ntext\n\n## Another\ntext")
    assert not score_objective(per_finding, [], 6).clustered
    assert score_objective(clustered, [], 6).clustered


def test_unblinding_attaches_arms_only_after_scoring():
    reports = {arm: f"{arm} text" for arm in ARMS}
    blinded, manifest = blind(reports)
    scores = [score_objective(b, [], 3) for b in blinded]
    assert all(s.arm is None for s in scores), "scoring must not see the arm"
    assert {s.arm for s in unblind(scores, manifest)} == set(ARMS)
