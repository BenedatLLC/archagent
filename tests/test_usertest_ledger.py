"""The user-test ledger's refusals — the parts that exist to prevent a wrong number."""

import importlib.util
from pathlib import Path

import pytest

from usertest_ledger import DIMENSIONS, UserTestRow, comparable, refuse_join, scores

_spec = importlib.util.spec_from_file_location(
    "usertest", Path(__file__).resolve().parents[1] / "scripts" / "usertest.py")
usertest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(usertest)


def _row(**kw):
    base = dict(run_id="r", date="2026-08-23", archagent_version="1.0.0rc1", archagent_commit="abc1234",
                target_url="u", target_commit="b5addb6", rubric_version="usertest-v1",
                docs_path="published")
    return UserTestRow(**{**base, **kw})


def test_there_is_no_mean_over_the_four_dimensions():
    """Averaging ease-of-use with correctness produces a number with no referent: the first is a direct
    observation this design supports, the second a spot check whose weight is `claims_verified` alone.
    Round 1 would read 1.75, which says less than "1" and "2" do separately."""
    import usertest_ledger
    assert not hasattr(usertest_ledger, "mean")
    assert set(scores(_row(ease_of_use="2", correctness="1"))) == set(DIMENSIONS)


def test_a_blank_score_stays_distinct_from_a_zero():
    """"Could not judge" and "judged it terrible" are different results, and the worksheet says so:
    'A blank is data; a guess is not.'"""
    assert scores(_row(ease_of_use="", correctness="1"))["ease_of_use"] is None


def test_an_undeclared_docs_path_is_refused():
    with pytest.raises(ValueError, match="docs_path must be one of"):
        _row(docs_path="probably read them")


def test_a_fallback_round_is_not_comparable_with_a_published_one():
    """Round 1's tester could not fetch the pinned tree and worked from `--help` and the installed
    skills, so it did not measure the question the kit asks. A later round read against it as a series
    would be comparing two different experiments."""
    ok, why = comparable(_row(docs_path="published"), _row(docs_path="fallback"))
    assert not ok and "docs_path differs" in why


def test_the_two_ledgers_cannot_be_joined():
    """They share a 1-5 scale and no subject."""
    with pytest.raises(NotImplementedError, match="not joinable"):
        refuse_join()


def test_out_of_range_scores_are_refused():
    with pytest.raises(ValueError, match="must be 1-5"):
        _row(impact="7")


# --- the parser, against the real returned worksheet ---------------------------------------

SHEET = Path("/tmp/archagent-usertest-2026-08-23/worksheet-httpx-b5addb6.md")


@pytest.mark.skipif(not SHEET.exists(), reason="round 1 worksheet not present")
def test_scores_are_anchored_to_their_section_not_to_order():
    """A rating assigned to the wrong dimension is invisible once it reaches the CSV, and the worksheet
    cannot be re-run to catch it."""
    text = SHEET.read_text()
    assert usertest._score_after(text, "Ease of use") == "2"
    assert usertest._score_after(text, "Correctness") == "1"
    assert usertest._score_after(text, "Completeness") == "2"
    assert usertest._score_after(text, "Impact") == "2"


@pytest.mark.skipif(not SHEET.exists(), reason="round 1 worksheet not present")
def test_the_reordered_worksheet_does_not_reassign_ratings():
    """Guard on the anchoring itself: swap two sections and the scores must follow their headings."""
    text = SHEET.read_text()
    i, j = text.index("### Correctness"), text.index("### Completeness")
    swapped = text[:i] + text[j:] + text[i:j]
    assert usertest._score_after(swapped, "Correctness") == "1"
    assert usertest._score_after(swapped, "Ease of use") == "2"


def test_bundled_and_published_are_not_the_same_round():
    """Rendering, cross-link navigation and in-page search are part of whether documentation is usable,
    and a kit reader has none of them. Collapsing the two would let a bundled round stand as evidence
    about the GitHub experience, which is the one most actual users will have."""
    ok, why = comparable(_row(docs_path="bundled"), _row(docs_path="published"))
    assert not ok and "docs_path differs" in why


def test_every_docs_path_the_worksheet_offers_is_a_legal_value():
    """The worksheet's tick-boxes and the ledger's accepted values must not drift apart: a tester could
    otherwise tick an option that `ingest` then refuses."""
    from usertest_ledger import DOCS_PATHS
    text = usertest._worksheet("b5addb6ff")
    for p in DOCS_PATHS:
        assert f"`{p}`" in text, f"{p} is accepted by the ledger but not offered in the worksheet"


def test_the_ingest_cli_offers_exactly_the_legal_docs_paths():
    """`bundled` was added to the ledger and the worksheet and not to argparse's `choices`, so the
    ledger accepted it, the worksheet offered it, and `ingest` refused it — found while ingesting round
    2. One vocabulary declared in three places is the shape group F exists to find."""
    import argparse
    from unittest.mock import patch
    from usertest_ledger import DOCS_PATHS
    captured = {}
    real = argparse.ArgumentParser.add_argument

    def spy(self, *a, **kw):
        if a and a[0] == "--docs-path":
            captured["choices"] = list(kw.get("choices", []))
        return real(self, *a, **kw)

    with patch.object(argparse.ArgumentParser, "add_argument", spy), \
         patch("sys.argv", ["usertest.py", "kit"]):
        try:
            usertest.main()
        except SystemExit:
            pass
    assert captured.get("choices") == list(DOCS_PATHS)
