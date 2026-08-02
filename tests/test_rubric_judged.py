"""The judged rubric — the rules that stop it measuring fluency instead of quality."""

import pytest

from rubric_judged import CRITERIA, parse_brief, render_brief, review_from


def _filled(**answers) -> str:
    """A completed brief with the given per-criterion answers."""
    text = render_brief("architecture/", "demo", second_run=True)
    for cid, (score, evidence, why) in answers.items():
        marker = f"## {cid} —"
        head, _, tail = text.partition(marker)
        tail = tail.replace("score:\nevidence:\nwhy:",
                            f"score: {score}\nevidence: {evidence}\nwhy: {why}", 1)
        text = head + marker + tail
    return text


# --- the criteria themselves --------------------------------------------------------------------

def test_every_criterion_is_anchored_at_1_3_and_5():
    """A bare 1-5 scale measures the judge's mood; two runs disagree and neither can say why."""
    for c in CRITERIA:
        assert set(c.anchors) == {1, 3, 5}
        assert all(len(a) > 40 for a in c.anchors.values()), f"{c.id} anchors are too thin to check against"


def test_the_criteria_cover_what_was_asked_for():
    ids = {c.id for c in CRITERIA}
    assert {"prose", "diagrams", "invariant_strength", "invariant_criticality",
            "completeness", "accuracy"} <= ids


def test_invariant_strength_and_criticality_are_separate():
    """A rule can be logically airtight and protect nothing that matters, or guard the crown jewels
    while being trivially evadable. One score would hide both cases."""
    assert "invariant_strength" != "invariant_criticality"
    strength = next(c for c in CRITERIA if c.id == "invariant_strength")
    crit = next(c for c in CRITERIA if c.id == "invariant_criticality")
    assert "vacuous" in strength.anchors[1].lower()
    assert "harm" in crit.anchors[5].lower()


def test_the_update_criterion_is_second_run_only():
    assert "update_quality" not in render_brief("a", "b", second_run=False)
    assert "update_quality" in render_brief("a", "b", second_run=True)


# --- the citation rule ----------------------------------------------------------------------------

def test_a_score_without_a_citation_is_discarded():
    """The failure mode is fluent, confident, unfalsifiable prose — what a language model produces most
    readily. A number with nothing behind it must not be averaged in."""
    parsed = parse_brief(_filled(prose=(5, "the documents read well", "they are clear and well written")))
    assert parsed["prose"]["score"] is None
    assert parsed["prose"]["discarded"] == "no file:line citation"


def test_a_cited_score_is_kept():
    parsed = parse_brief(_filled(prose=(4, "architecture/subsystems/api.md:12", "grounded and concrete")))
    assert parsed["prose"]["score"] == 4


def test_a_citation_in_the_why_field_also_counts():
    parsed = parse_brief(_filled(accuracy=(2, "checked the router", "src/router.py:88 contradicts it")))
    assert parsed["accuracy"]["score"] == 2


def test_zero_means_unsure_and_is_excluded_not_counted_as_failure():
    """An honest gap is more useful than a guessed number, and scoring it 0 would punish the artifact for
    the reviewer's uncertainty."""
    r = review_from(_filled(diagrams=(0, "", "could not tell without running it"),
                            prose=(4, "architecture/x.md:3", "clear")), "demo", "v1", "judge")
    assert r.scores["diagrams"]["score"] is None
    assert r.mean == pytest.approx(4.0)


def test_an_unanswered_criterion_is_absent_rather_than_guessed():
    assert "accuracy" not in parse_brief(render_brief("a", "b"))


# --- the review record ------------------------------------------------------------------------------

def test_the_mean_ignores_discarded_scores():
    r = review_from(_filled(prose=(5, "no citation here", "just vibes"),
                            accuracy=(3, "src/a.py:1", "mostly right")), "demo", "v1", "judge")
    assert r.mean == pytest.approx(3.0) and "prose" in r.discarded


def test_a_review_carries_its_own_uncalibrated_caveat():
    """§13.2: judged scores inform proposals and never gate a decision. The record says so itself, so a
    number cannot be quoted apart from the caveat."""
    d = review_from(_filled(prose=(5, "architecture/a.md:1", "clear")), "demo", "v1", "judge").to_dict()
    assert d["calibrated"] is False
    assert "unknown meaning" in d["caveat"] and "gates nothing" in d["caveat"]


def test_a_review_with_nothing_usable_has_no_mean():
    """"Could not be scored" and "scored badly" are different claims."""
    r = review_from(_filled(prose=(5, "no citation", "vibes")), "demo", "v1", "judge")
    assert r.mean is None


def test_the_brief_names_the_artifact_relative_to_the_repo():
    """The brief is committed and read on another machine, so an absolute path from whoever generated it
    is noise at best and wrong at worst."""
    brief = render_brief("docs/architecture", "archagent")
    assert "docs/architecture/" in brief
    assert "/Users/" not in brief and "/home/" not in brief
