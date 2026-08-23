"""The end-to-end user-test kit: what it must ship, and what it must never destroy."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import importlib.util

_spec = importlib.util.spec_from_file_location(
    "usertest", Path(__file__).resolve().parents[1] / "scripts" / "usertest.py")
usertest = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(usertest)


def test_the_kit_withholds_the_configuration_step(tmp_path):
    """The whole design: the tester must work out how to set the tool up. Shipping an `archagent.toml`
    would hand them the step most likely to fail, and the kit would then measure something else."""
    assert "archagent.toml" in usertest.WITHHOLD
    assert "architecture" in usertest.WITHHOLD


def test_a_filled_in_worksheet_is_never_rebuilt_over(tmp_path):
    """`spotcheck.py kit` once rebuilt over a completed review and destroyed it. This is worse: a
    findings capture can be regenerated, but a worksheet records one person's first contact with the
    tool and that cannot be re-run on the same person."""
    sheet = tmp_path / "worksheet-httpx-b5addb6.md"
    sheet.write_text("- score: 4\n- why: it worked\n")
    with pytest.raises(SystemExit, match="filled-in worksheet"):
        usertest.do_kit(tmp_path)


def test_an_untouched_worksheet_does_not_block_a_rebuild(tmp_path):
    """The placeholder must not read as an answer, or the kit could never be rebuilt after a dry run."""
    (tmp_path / "worksheet-httpx-b5addb6.md").write_text(usertest._worksheet("b5addb6ff"))
    assert not usertest._is_filled_in(tmp_path / "worksheet-httpx-b5addb6.md")


def test_the_target_is_disjoint_from_every_tuning_and_heldout_repository():
    """A tool measured on a repository it was tuned against reports its best-fit performance.
    `heldout_manifest.toml` states the rule; this asserts the user test obeys it too — litellm was the
    first proposal for this kit and is named there as disqualified."""
    root = Path(__file__).resolve().parents[1]
    corpus = (root / "tests" / "corpus_manifest.toml").read_text()
    heldout = (root / "tests" / "heldout_manifest.toml").read_text()
    name = usertest.TARGET["name"]
    assert f'name = "{name}"' not in corpus, f"{name} is a tuning repository"
    assert f'name = "{name}"' not in heldout, f"{name} is reserved for the defect study"


def test_the_instructions_pin_the_docs_to_the_version_under_test():
    """PyPI had 0.3.0 while the repository's docs described unreleased behaviour. A tester reading the
    default branch against an older wheel measures the skew, not the tool."""
    text = usertest._instructions("b5addb6ff", "a commit")
    assert usertest.TAG in text
    assert f"tree/{usertest.TAG}" in text, "the docs link must be pinned, not point at the default branch"
    assert usertest.VERSION in text


def test_the_worksheet_asks_whether_the_silent_failure_was_noticed():
    """A wrong source path makes every check examine nothing and report that all is well. If a tester
    hits it, they would rate correctness on an artifact covering none of the code — so the worksheet has
    to ask directly rather than hoping it surfaces."""
    text = usertest._worksheet("b5addb6ff")
    assert "0%" in text
    assert "did the tool tell you, or did you notice yourself" in text


def test_the_worksheet_separates_verified_claims_from_impressions():
    """Round 5 showed a careful reviewer had to check findings one at a time, and that 6 of 19 plausible
    findings described nothing real. A correctness score from someone who checked nothing is an
    impression, and must not later be pooled with blind precision."""
    text = usertest._worksheet("b5addb6ff")
    assert "how many claims did you actually verify?" in text
