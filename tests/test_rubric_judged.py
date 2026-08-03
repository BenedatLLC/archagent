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


# --- multi-line answers -----------------------------------------------------------------------------

def test_a_field_runs_to_the_next_key_not_to_the_end_of_its_line():
    """The first real review put a one-line summary after `why:` and the claim-by-claim evidence — with
    every citation in it — on the lines below. A line-scoped read discarded five of its six scores as
    uncited, and reported the mean of the sixth as if it were the artifact's score."""
    text = _filled(accuracy=(2, "See the five claims below.",
                             "Two of five load-carrying claims are stale.\n"
                             "  Claim 1 - entry point: PASS\n"
                             "    cite: src/archagent/__init__.py:22\n"
                             "  Claim 2 - cycle: FAIL\n"
                             "    cite: docs/architecture/decisions/0003.md:19"))
    parsed = parse_brief(text)
    assert parsed["accuracy"]["score"] == 2
    assert "Claim 2" in parsed["accuracy"]["why"]


def test_an_unrecognised_section_does_not_disturb_the_criteria_around_it():
    """Reviewers add sections the rubric did not ask for. They are not scores, but they must not swallow
    the next criterion's fields either."""
    text = _filled(prose=(4, "docs/architecture/index.md:1", "clear"))
    text += "\n## structural_observations — Organization\n\nNo entry point.\n"
    assert parse_brief(text)["prose"]["score"] == 4
    assert "structural_observations" not in parse_brief(text)


# --- citations must resolve -------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["LogsTab.tsx", "mcp.json", "App.jsx", "config.yaml", "run.mjs"])
def test_a_multi_character_extension_is_not_truncated(tmp_path, name):
    """Python's `|` is first-match, not longest-match, so `ts|tsx` clipped `LogsTab.tsx` to `LogsTab.ts`
    and `js|json` clipped `mcp.json` to `mcp.js`. The clipped path then does not exist, so a real citation
    was reported as invented — the precise opposite of what this check is for."""
    (tmp_path / name).write_text("x\n")
    parsed = parse_brief(_filled(accuracy=(3, f"{name}:1", "checked")), root=tmp_path)
    assert parsed["accuracy"]["score"] == 3
    assert not parsed["accuracy"]["unresolved"]


def test_a_citation_to_a_missing_file_does_not_count(tmp_path):
    """A well-formed citation is not a true one, and fabricated citations are exactly what this rubric
    exists to catch — the first review cited an ADR filename that has never existed."""
    (tmp_path / "real.py").write_text("x = 1\n")
    parsed = parse_brief(_filled(accuracy=(2, "invented.py:4", "contradicted")), root=tmp_path)
    assert parsed["accuracy"]["score"] is None
    assert "no such file" in parsed["accuracy"]["discarded"]


def test_a_citation_past_the_end_of_the_file_does_not_count(tmp_path):
    """`check.py line 1593`, in a 248-line file. It reads as diligence and was invented."""
    (tmp_path / "check.py").write_text("x = 1\n" * 10)
    parsed = parse_brief(_filled(accuracy=(2, "check.py:1593", "contradicted")), root=tmp_path)
    assert parsed["accuracy"]["score"] is None


def test_one_bad_citation_among_good_ones_is_flagged_not_fatal(tmp_path):
    """Miscopying one line number should not void a review that is otherwise grounded — but the reader
    must still be told which citation failed."""
    (tmp_path / "real.py").write_text("x = 1\n" * 10)
    parsed = parse_brief(_filled(accuracy=(3, "real.py:4", "and also invented.py:9")), root=tmp_path)
    assert parsed["accuracy"]["score"] == 3
    assert any("invented.py" in u for u in parsed["accuracy"]["unresolved"])


def test_citations_are_only_pattern_matched_when_no_root_is_given(tmp_path):
    parsed = parse_brief(_filled(accuracy=(3, "invented.py:9", "contradicted")))
    assert parsed["accuracy"]["score"] == 3


# --- a mean over a fraction of the review is not a score --------------------------------------------

def test_the_caveat_says_when_the_mean_covers_only_part_of_the_review():
    """2.0 from one surviving criterion and 2.0 from six read identically, and the first is not a
    judgement of the artifact at all."""
    r = review_from(_filled(prose=(5, "no citation", "vibes"),
                            accuracy=(2, "src/a.py:1", "stale")), "demo", "v1", "judge")
    assert r.coverage == (1, 2)
    assert "1 of 2" in r.to_dict()["caveat"]


def test_the_brief_states_the_rules_a_reviewer_would_otherwise_violate():
    brief = render_brief("docs/architecture", "archagent")
    assert "must exist" in brief and "next `score:`" in brief


def test_the_brief_names_the_artifact_relative_to_the_repo():
    """The brief is committed and read on another machine, so an absolute path from whoever generated it
    is noise at best and wrong at worst."""
    brief = render_brief("docs/architecture", "archagent")
    assert "docs/architecture/" in brief
    assert "/Users/" not in brief and "/home/" not in brief


def test_a_path_outside_the_repo_is_not_judged(tmp_path):
    """`~/.cursor/mcp.json` in a document about an installer is a real path at a real location. Resolving
    it against the checkout would report a true citation as invented."""
    parsed = parse_brief(_filled(accuracy=(3, "~/.cursor/mcp.json", "the installer writes here")),
                         root=tmp_path)
    assert parsed["accuracy"]["score"] == 3 and not parsed["accuracy"]["unresolved"]
