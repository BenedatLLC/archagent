"""Human spot-check and calibration — the properties that decide whether the labels mean anything."""

import pytest

from spotcheck import (
    Label,
    LabelStore,
    agreement,
    finding_key,
    parse_worksheet,
    precision_by_sign,
    render_worksheet,
    stratified_sample,
    values_of,
    wilson,
)


def _item(key, repo="litellm", sign="scattered-source-of-truth", conf="low", claim=None):
    return {"key": key, "repo": repo, "rev": "v1", "sign": sign, "confidence": conf,
            "evidence": f"- owner: `{key}.py`\n- churn: 40", "tool_claim": claim or {"severity": "med"}}


# --- identity ---------------------------------------------------------------------------------

def test_the_key_survives_things_that_move_between_runs():
    """Labels are the expensive input; a key that changed with churn counts would spend each one once."""
    a = finding_key("change-prone-file", ["src/a.py"], None)
    b = finding_key("change-prone-file", ["src/a.py"], None)
    assert a == b


def test_the_key_distinguishes_different_value_sets():
    a = finding_key("scattered-source-of-truth", ["src/a.py"], ["paid", "shipped"])
    b = finding_key("scattered-source-of-truth", ["src/a.py"], ["red", "green"])
    assert a != b


def test_value_order_does_not_change_the_key():
    assert (finding_key("s", ["a.py"], ["b", "a"]) == finding_key("s", ["a.py"], ["a", "b"]))


def test_values_are_read_out_of_the_detail_text():
    assert values_of("in x: {paid, shipped, +3 more} branched on") == ["paid", "shipped"]
    assert values_of("40 commits; mean indent 9.1") is None


# --- blinding ---------------------------------------------------------------------------------

def test_the_tools_claim_is_absent_from_the_worksheet():
    """Shown up front, severity and confidence anchor the reviewer and the exercise measures agreement
    with our own prior instead of with the code."""
    sheet, withheld = render_worksheet([_item("k1", claim={"severity": "high", "confidence": "med",
                                                           "recommendation": "Split this file"})])
    assert "high" not in sheet and "Split this file" not in sheet
    assert withheld["k1"]["severity"] == "high"


def test_the_worksheet_still_carries_the_evidence():
    sheet, _ = render_worksheet([_item("k1")])
    assert "owner: `k1.py`" in sheet and "churn: 40" in sheet


# --- parsing ----------------------------------------------------------------------------------

def test_a_filled_sheet_round_trips():
    sheet, _ = render_worksheet([_item("k1"), _item("k2")])
    filled = sheet.replace("verdict:\nwhy:", "verdict: confirm\nwhy: real duplication", 1)
    parsed = parse_worksheet(filled)
    assert parsed["k1"] == {"verdict": "confirm", "why": "real duplication"}
    assert "k2" not in parsed, "unanswered items are skipped, never guessed at"


def test_the_parser_is_lenient_about_how_people_write():
    sheet, _ = render_worksheet([_item("k1")])
    filled = sheet.replace("verdict:\nwhy:", "Verdict:  Dismiss — intended family\nwhy: adapters", 1)
    assert parse_worksheet(filled)["k1"]["verdict"] == "dismiss"


def test_an_unrecognised_verdict_is_skipped_rather_than_guessed():
    sheet, _ = render_worksheet([_item("k1")])
    assert parse_worksheet(sheet.replace("verdict:", "verdict: maybe?", 1)) == {}


# --- the store --------------------------------------------------------------------------------

def _label(store, key, verdict, reviewer="jf", **kw):
    return store.record(Label(key=key, repo="litellm", sign="s", verdict=verdict, why="because",
                              reviewer=reviewer, dated="2026-08-01", **kw))


def test_labels_persist_and_reload(tmp_path):
    store = LabelStore(tmp_path)
    _label(store, "k1", "confirm")
    assert store.load("litellm")["k1"].verdict == "confirm"


def test_changing_a_verdict_requires_a_note(tmp_path):
    """Otherwise labels drift toward whatever the tool currently claims and the calibration they feed
    becomes circular."""
    store = LabelStore(tmp_path)
    _label(store, "k1", "confirm")
    with pytest.raises(ValueError, match="requires a note"):
        _label(store, "k1", "dismiss")


def test_a_changed_verdict_keeps_the_one_it_replaced(tmp_path):
    store = LabelStore(tmp_path)
    _label(store, "k1", "confirm")
    store.record(Label(key="k1", repo="litellm", sign="s", verdict="dismiss", why="on reflection",
                       reviewer="jf", dated="2026-08-02"), note="re-read the code; adapters by design")
    kept = store.load("litellm")["k1"]
    assert kept.verdict == "dismiss"
    assert kept.history[0]["verdict"] == "confirm"
    assert "adapters" in kept.history[0]["changed_because"]


def test_relabelling_the_same_verdict_needs_no_note(tmp_path):
    store = LabelStore(tmp_path)
    _label(store, "k1", "confirm")
    _label(store, "k1", "confirm")            # must not raise


def test_evidence_that_changed_marks_the_label_stale(tmp_path):
    """The verdict was about the evidence as it stood; silently reusing it against different evidence
    would be inventing a judgement nobody made."""
    store = LabelStore(tmp_path)
    _label(store, "k1", "confirm", evidence="5 files, 40 churn")
    assert store.stale("litellm", {"k1": "12 files, 400 churn"}) == ["k1"]
    assert store.stale("litellm", {"k1": "5 files, 40 churn"}) == []


# --- sampling ---------------------------------------------------------------------------------

def test_sampling_spreads_across_strata_rather_than_taking_the_biggest():
    items = [_item(f"a{i}", sign="change-prone-file") for i in range(50)] + \
            [_item(f"b{i}", sign="enum-value-escape") for i in range(3)]
    picked = stratified_sample(items, cap=10)
    signs = {p["sign"] for p in picked}
    assert signs == {"change-prone-file", "enum-value-escape"}


def test_sampling_is_reproducible():
    items = [_item(f"a{i}") for i in range(40)]
    assert [p["key"] for p in stratified_sample(items, cap=8)] == \
           [p["key"] for p in stratified_sample(items, cap=8)]


def test_sampling_respects_the_cap():
    assert len(stratified_sample([_item(f"a{i}") for i in range(40)], cap=7)) == 7


# --- statistics -------------------------------------------------------------------------------

def test_wilson_stays_inside_zero_and_one_at_small_n():
    """The normal approximation runs past the ends at the sample sizes this exercise produces."""
    lo, hi = wilson(5, 5)
    assert 0.0 <= lo <= hi <= 1.0 and lo > 0.4


def test_wilson_of_nothing_is_the_whole_interval():
    assert wilson(0, 0) == (0.0, 1.0)


def test_precision_excludes_unsure_from_the_denominator():
    """`unsure` is missing data, not a dismissal — counting it either way invents a judgement."""
    labels = [Label("k1", "r", "sX", "confirm", "", "jf", "d"),
              Label("k2", "r", "sX", "dismiss", "", "jf", "d"),
              Label("k3", "r", "sX", "unsure", "", "jf", "d")]
    out = precision_by_sign(labels)["sX"]
    assert out["n"] == 2 and out["precision"] == pytest.approx(0.5) and out["unsure"] == 1


def test_agreement_reports_the_direction_of_disagreement():
    """A single rate would hide a judge that systematically over-confirms."""
    human = {"a": "dismiss", "b": "dismiss", "c": "confirm"}
    judge = {"a": "confirm", "b": "confirm", "c": "confirm"}
    out = agreement(human, judge)
    assert out["n"] == 3 and out["judge_over_confirms"] == 2 and out["judge_over_dismisses"] == 0


def test_agreement_ignores_items_only_one_side_rated():
    assert agreement({"a": "confirm"}, {"b": "confirm"})["n"] == 0
