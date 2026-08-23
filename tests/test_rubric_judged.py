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
    """§20.2: judged scores inform proposals and never gate a decision. The record says so itself, so a
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


def test_two_reviewers_of_the_same_artifact_do_not_share_a_file():
    """A fixed judged.json meant the second parse overwrote the first. That is fatal for calibration
    specifically: the two records exist to be compared, so parsing the second destroyed the thing it was
    about to be compared against. Recovered from git that time."""
    import importlib.util
    import sys
    from pathlib import Path
    scripts = Path(__file__).resolve().parent.parent / "scripts"
    sys.path.insert(0, str(scripts))   # selfeval.py imports evalhome from beside itself
    spec = importlib.util.spec_from_file_location("selfeval_script", scripts / "selfeval.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules["selfeval_script"] = mod
    spec.loader.exec_module(mod)
    a = mod._slug("jeff (independent reviewer)")
    b = mod._slug("blind model judge")
    assert a != b and a and b
    assert "/" not in a and " " not in a, "the slug becomes a filename"
    assert mod._slug("") == "unrecorded", "an unnamed reviewer still gets a stable, non-empty file"


def test_a_score_in_the_heading_is_read():
    """`## accuracy — Score: 5` instead of a `score:` field. The second of three real reviews to be
    unreadable for a formatting reason, each time with the content perfectly fine. Where a number was
    typed is not what this rubric is trying to measure."""
    text = ("# review\n\n## accuracy — Score: 5\n\n"
            "**evidence:** checked five claims\n\n"
            "**why:** every one holds — `src/main.py:12` confirms the first\n")
    parsed = parse_brief(text)
    assert parsed["accuracy"]["score"] == 5
    assert "every one holds" in parsed["accuracy"]["why"]


def test_a_heading_score_does_not_override_a_field_score():
    text = ("## prose — Score: 5\n\nscore: 3\nevidence: `a.py:1`\nwhy: mixed\n")
    assert parse_brief(text)["prose"]["score"] == 3


def test_a_framework_name_is_not_a_missing_file(tmp_path):
    """"Next.js" ends in `.js` and is not a file. Reporting it as an invented citation is noise that
    teaches a reader to ignore the check."""
    from rubric_judged import unresolved_citations
    assert unresolved_citations("The Next.js route handler and the Node.js runtime.", tmp_path) == []
    assert unresolved_citations("See invented.js for details.", tmp_path) != []


# --- the evaluate section (design: findings judged as a report, not adjudicated) ---------------------

def _cap(findings=None, inactive=None, **kw):
    from findings import Capture
    base = dict(repo="demo", target_rev="v1.0", archagent="archagent 0.3.0", captured_at="2026-08-22",
                findings=findings or [], inactive=inactive or [])
    return Capture(**{**base, **kw})


def test_the_evaluate_section_is_absent_when_nothing_was_captured():
    """Omitted entirely rather than included and blank. An unanswered section is indistinguishable from
    one the reviewer skipped, and this instrument turns on that distinction everywhere else."""
    text = render_brief("architecture/", "demo")
    assert "finding_actionability" not in text and "archagent evaluate" not in text


def test_the_evaluate_section_appears_when_a_capture_is_passed():
    text = render_brief("architecture/", "demo", findings=_cap())
    for c in ("finding_actionability", "finding_restraint", "finding_coverage_honesty"):
        assert c in text


def test_no_evaluate_criterion_asks_whether_a_finding_is_true():
    """The blinding boundary, asserted rather than trusted to a comment. The brief shows every finding
    with its severity, so a question about correctness here would measure agreement with our own prior
    and return it as precision. That question belongs in the blinded spot-check."""
    from rubric_judged import EVALUATE_CRITERIA
    banned = ("is it correct", "is this correct", "true or false", "is it real", "precision",
              "do you agree")
    for c in EVALUATE_CRITERIA:
        blob = (c.question + " " + " ".join(c.anchors.values())).lower()
        for b in banned:
            assert b not in blob, f"{c.id} asks the blinded question: {b!r}"


def test_the_brief_says_the_reviewer_is_judging_the_report():
    text = render_brief("architecture/", "demo", findings=_cap())
    assert "judging the report, not adjudicating" in text


def test_an_empty_finding_set_is_not_presented_as_a_clean_result():
    """Zero findings is a result, not a blank — and it is only readable next to the list of families that
    never ran."""
    text = render_brief("architecture/", "demo", findings=_cap())
    assert "That is a result, not a blank" in text


def test_severity_is_labelled_mechanical_where_it_is_shown():
    """The reviewer is asked whether the report is restrained about severity; showing it unlabelled here
    would put the defect in the instrument rather than in what it measures."""
    f = {"sign": "god-component", "group": "C", "severity": "high", "title": "God component",
         "subjects": ["cli"], "detail": "", "recommendation": "", "id": "x:y:z"}
    text = render_brief("architecture/", "demo", findings=_cap(findings=[f]))
    assert "(mechanical)" in text


def test_a_failed_history_mine_is_stated_in_the_brief():
    text = render_brief("architecture/", "demo", findings=_cap(mining_failed=True))
    assert "History mining FAILED" in text


def test_the_two_means_are_computed_separately():
    """Folding the evaluate scores into `mean` would redefine what that number measures while leaving its
    name and its ledger column unchanged — the exact shape of the defect the ledger exists to prevent."""
    text = """
## accuracy — Accuracy
score: 4
evidence: src/a.py:10
why: fine

## finding_actionability — Finding actionability
score: 2
evidence: src/a.py:12
why: generic advice
"""
    r = review_from(text, "demo", "", "tester")
    assert r.mean == 4.0
    assert r.evaluate_mean == 2.0


def test_a_review_with_no_evaluate_section_reports_no_evaluate_mean():
    r = review_from("## accuracy — Accuracy\nscore: 4\nevidence: a.py:1\nwhy: ok\n", "demo", "", "t")
    assert r.evaluate_mean is None and r.evaluate_coverage == (0, 0)
    assert "evaluate_mean" not in r.to_dict()


def test_the_brief_records_its_own_rubric_versions():
    """`rubric_version` was hand-typed into the ledger until now, and a version key entered by hand can
    disagree with the brief it names without anything noticing."""
    from rubric_judged import ARTIFACT_RUBRIC_VERSION, EVALUATE_RUBRIC_VERSION
    text = render_brief("architecture/", "demo", findings=_cap())
    assert ARTIFACT_RUBRIC_VERSION in text and EVALUATE_RUBRIC_VERSION in text


# --- per-finding impact ratings (round 5) -----------------------------------------------------------

def _finding(fid="g:ui:0", sign="god-component"):
    return {"sign": sign, "group": "C", "severity": "high", "title": sign, "subjects": ["ui"],
            "detail": "70/122 files", "recommendation": "Split it.", "id": fid, "confidence": "med"}


def test_the_impact_scale_contains_the_investigate_ratings_verbatim():
    """2, 3 and 4 are `minor` / `moderate` / `critical`, the vocabulary `archagent investigate --record`
    already accepts, so a rating collected here can be written straight into the artifact and compared
    with one produced by a full investigation."""
    from archagent.investigations import RATINGS
    from rubric_judged import IMPACT_SCALE
    assert tuple(IMPACT_SCALE[n][0] for n in (2, 3, 4)) == RATINGS


def test_zero_is_not_a_finding_rather_than_the_bottom_of_the_scale():
    """"Wrong" and "unimportant" are different failures with different fixes, and collapsing them would
    let a false finding average in as a harmless one."""
    from rubric_judged import IMPACT_SCALE
    assert IMPACT_SCALE[0][0] == "not a finding"
    assert IMPACT_SCALE[1][0] == "trivial"


def test_each_finding_gets_its_own_impact_block():
    from rubric_judged import render_brief
    text = render_brief("architecture/", "demo", findings=_cap(findings=[_finding(), _finding("l:a:0")]))
    assert text.count("impact:") == 2


def test_impacts_are_read_back_against_their_finding_ids():
    from rubric_judged import parse_impacts
    text = ("### `god-component` — G\n**id** `g:ui:0`\n\n```\nimpact: 4\nwhy: three teams edit it\n```\n"
            "### `layer-skip` — L\n**id** `l:a:0`\n\n```\nimpact: 0\nwhy: no such layer\n```\n")
    got = parse_impacts(text)
    assert got["g:ui:0"]["impact"] == 4 and "three teams" in got["g:ui:0"]["why"]
    assert got["l:a:0"]["impact"] == 0


def test_an_unanswered_finding_is_absent_not_zero():
    """A missing rating is missing data. Defaulting it to 0 would read every skipped item as "not a
    finding" — the strongest verdict on the scale and the least likely to be meant."""
    from rubric_judged import parse_impacts
    assert parse_impacts("### `x` — X\n**id** `g:ui:0`\n\n```\nimpact:\nwhy:\n```\n") == {}


def test_a_long_why_does_not_swallow_the_next_findings_rating():
    from rubric_judged import parse_impacts
    text = ("### `a` — A\n**id** `a:1:0`\n\n```\nimpact: 2\nwhy: several\nlines\nof reasoning\n```\n"
            "### `b` — B\n**id** `b:2:0`\n\n```\nimpact: 5\nwhy: bad\n```\n")
    got = parse_impacts(text)
    assert got["a:1:0"]["impact"] == 2 and got["b:2:0"]["impact"] == 5


def test_the_summary_reports_a_distribution_not_a_mean():
    """A mean over a scale whose zero means "not a finding" is meaningless: one wrong finding and one
    project-threatening one do not average to "moderate"."""
    from rubric_judged import impact_summary
    s = impact_summary({"a": {"impact": 0}, "b": {"impact": 1}, "c": {"impact": 4}}, total=5)
    assert "mean" not in s
    assert s["not_a_finding"] == 1 and s["noise"] == 2 and s["worth_acting_on"] == 1
    assert s["rated"] == 3 and s["unrated"] == 2
