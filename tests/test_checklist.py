"""Per-repository checklists — the worksheet, the parser, and the checklists themselves.

The instrument's whole claim is that it is *more reproducible* than open scoring, so the tests are about
the places reproducibility leaks: a verdict the parser reads differently than the judge meant, an
unanswered worksheet reading as a clean one, and a checklist that has quietly become a list of past
defects and therefore measures nothing the recurrence suite does not.
"""

import pytest

from checklist import Item, load, parse, render, score


def _item(**kw):
    base = dict(id="i1", target="t", rev="r", ground_truth="Store holds four locks.")
    return Item(**{**base, **kw})


def _answer(item_id, verdict="", quote="", why=""):
    return f"## {item_id}\n\n```\nverdict: {verdict}\nquote: {quote}\nwhy: {why}\n```\n"


# --- the worksheet --------------------------------------------------------------------------------

def test_the_worksheet_states_the_answer():
    """The distinction from the open rubric. A worksheet that asks 'is the concurrency description
    correct?' is a research task and re-runs the error the checklist exists to prevent."""
    text = render([_item()], "architecture", "t")
    assert "Store holds four locks." in text

def test_the_worksheet_keeps_items_in_the_order_given():
    text = render([_item(id="a"), _item(id="b"), _item(id="c")], "architecture", "t")
    assert text.index("## a") < text.index("## b") < text.index("## c")

def test_a_custom_question_overrides_the_default_framing():
    """Count items are phrased conditionally — 'if the artifact states a count, is it 57?' — so that not
    stating a number is `absent` rather than a failure. An artifact must not be pushed toward inventing
    numbers in order to score."""
    text = render([_item(question="If the artifact states a count, is it 57?")], "architecture", "t")
    assert "If the artifact states a count, is it 57?" in text
    assert "Does the artifact convey this?" not in text


# --- the parser -----------------------------------------------------------------------------------

@pytest.mark.parametrize("written", ["correct", "Correct", "**correct**", "correct — see below"])
def test_a_verdict_reads_however_it_is_written(written):
    items = [_item()]
    assert parse(_answer("i1", written, quote="a passage"), items)["i1"].verdict == "correct"

def test_a_quote_may_run_over_several_lines():
    """Same lesson as the review parser, where a line-scoped read reported the best-evidenced review
    received as uncited. A quote from an artifact is a paragraph, not a phrase."""
    text = ("## i1\n\n```\nverdict: wrong\nquote: The store sits\nbehind one sync.Mutex,\n"
            "which bounds memory.\nwhy: four locks\n```\n")
    a = parse(text, [_item()])["i1"]
    assert "bounds memory" in a.quote and a.why == "four locks"

def test_wrong_without_a_quote_is_discarded():
    """The rule that holds the wrong/absent boundary — §14's stated weak point. Without it `wrong` becomes
    the verdict for any artifact that is merely vague, and a vague artifact scores like a lying one."""
    a = parse(_answer("i1", "wrong", why="it seemed off"), [_item()])["i1"]
    assert a.verdict is None and "no quote" in a.discarded

def test_absent_needs_no_quote():
    assert parse(_answer("i1", "absent"), [_item()])["i1"].verdict == "absent"

def test_an_unreadable_verdict_is_discarded_not_guessed():
    a = parse(_answer("i1", "hmm, hard to say"), [_item()])["i1"]
    assert a.verdict is None and a.discarded

def test_answers_for_unknown_items_are_ignored():
    assert parse(_answer("not-an-item", "correct", quote="x"), [_item()]) == {}


# --- scoring --------------------------------------------------------------------------------------

def test_severity_weighting_separates_a_false_security_claim_from_a_file_count():
    items = [_item(id="sec", severity="serious"), _item(id="count", severity="minor")]
    s = score(parse(_answer("sec", "wrong", quote="q") + _answer("count", "correct", quote="q"), items),
              items)
    assert s.accuracy == 0.5
    assert s.weighted_accuracy == pytest.approx(1 / 4)     # 1 of 3+1

def test_a_skipped_item_is_reported_skipped_not_passed():
    items = [_item(id="a"), _item(id="b")]
    s = score(parse(_answer("a", "correct", quote="q"), items), items)
    assert s.skipped == ["b"] and s.answered == 1

def test_an_unanswered_worksheet_does_not_score_perfect():
    """An empty worksheet reading as 1.0 is the silent-failure shape this project keeps hitting: a
    condition that renders as a plausible clean result."""
    s = score({}, [_item()])
    assert s.accuracy is None and s.weighted_accuracy is None

def test_a_discarded_answer_counts_as_neither_right_nor_wrong():
    items = [_item(id="a")]
    s = score(parse(_answer("a", "wrong"), items), items)
    assert s.answered == 0 and s.discarded and s.accuracy is None


# --- the checklists on record -----------------------------------------------------------------------

def _files():
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
    from evalhome import eval_home
    d = eval_home() / "checklists"
    return [pytest.param(f, id=f.stem) for f in sorted(d.glob("*.toml"))] if d.is_dir() else []


_FILES = _files()


@pytest.mark.skipif(not _FILES, reason="no evaluation data repo — set ARCHAGENT_EVAL_HOME")
@pytest.mark.parametrize("path", _FILES)
def test_every_item_carries_a_citation_and_a_source(path):
    """Ground truth with nothing behind it is an opinion, and the judge is told to treat the key as
    authoritative — so an uncited key would launder an assumption into an answer.

    Two forms count. A **path**, with or without a line: some facts are counts over a directory, and
    demanding a line number there would only produce an arbitrary one. Or a **command**, which is what a
    count actually comes from — the same rule `describe` is given, since a bare number with a path beside
    it is how "64 Go files" got written twice.
    """
    import re
    cited = re.compile(r"[\w.-]+/[\w.-]+|\b[\w-]+\.\w{2,4}:\d+|`\s*(?:find|rg|grep|git|ls|wc)\b")
    bad = [i.id for i in load(path) if not cited.search(i.ground_truth)]
    assert not bad, f"items with no citation in the ground truth: {bad}"
    assert not [i.id for i in load(path) if not i.source]


@pytest.mark.skipif(not _FILES, reason="no evaluation data repo — set ARCHAGENT_EVAL_HOME")
@pytest.mark.parametrize("path", _FILES)
def test_a_checklist_is_not_only_a_list_of_past_defects(path):
    """§14's third caution, mechanised. A checklist made entirely of known defects measures what the
    recurrence suite already measures, its score can only fall, and the suite stops growing. At least a
    quarter of the items must come from a reading rather than from a finding."""
    items = load(path)
    fresh = [i for i in items if "checklist" in i.source]
    assert len(fresh) >= len(items) / 4, (
        f"{len(fresh)} of {len(items)} items came from reading the code rather than from a past defect")


@pytest.mark.skipif(not _FILES, reason="no evaluation data repo — set ARCHAGENT_EVAL_HOME")
@pytest.mark.parametrize("path", _FILES)
def test_ids_are_unique_and_the_revision_is_pinned(path):
    items = load(path)
    ids = [i.id for i in items]
    assert len(set(ids)) == len(ids)
    assert len({i.rev for i in items}) == 1, "a checklist is answers about one revision"


@pytest.mark.skipif(not _FILES, reason="no evaluation data repo — set ARCHAGENT_EVAL_HOME")
@pytest.mark.parametrize("path", _FILES)
def test_the_worksheet_renders_without_leaking_the_verdict_template(path):
    items = load(path)
    text = render(items, "architecture", items[0].target, items[0].rev)
    assert text.count("verdict:") == len(items)
    assert all(f"## {i.id}" in text for i in items)
