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


# --- the bundled documentation (round 1's failure) -----------------------------------------

def test_the_kit_bundles_the_whole_doc_set_not_a_selection():
    """Choosing three pages a tester "needs" would replace the question *which page do I need?* — a real
    part of onboarding — with a curated answer. Round 1 failed the other way: it shipped no docs at all
    and told the tester to fetch a URL, the fetch failed, and they reverse-engineered the tool from
    `--help`."""
    assert usertest.BUNDLE == ("README.md", "docs")


def test_the_instructions_no_longer_depend_on_fetching_a_url():
    """The URL may remain as an alternative; it may not be the only way in."""
    text = usertest._instructions("b5addb6ff", "a commit")
    assert f"docs-{usertest.VERSION}/README.md" in text
    assert "should not need the network" in text
    i_local = text.index(f"docs-{usertest.VERSION}/README.md")
    i_url = text.index("https://github.com/BenedatLLC/archagent/tree/")
    assert i_local < i_url, "the offline path must be given before the URL, not as a fallback to it"


def test_the_worksheet_asks_which_documentation_was_read():
    """`docs_path` is a comparability key, and the answer that matters most for comparability is the one
    a busy tester is likeliest to skip — so it is a tick-box in the log, not a question at the end."""
    text = usertest._worksheet("b5addb6ff")
    for option in ("`bundled`", "`published`", "`mixed`", "`fallback`"):
        assert option in text, option


def test_a_ticked_docs_path_is_read_back_for_cross_checking():
    sheet = usertest._worksheet("b5addb6ff").replace("- [ ] `published`", "- [x] `published`")
    assert usertest._ticked_docs_path(sheet) == "published"


def test_two_ticks_are_treated_as_no_answer():
    """An ambiguous answer must not silently become the first one."""
    sheet = (usertest._worksheet("b5addb6ff")
             .replace("- [ ] `published`", "- [x] `published`")
             .replace("- [ ] `bundled`", "- [x] `bundled`"))
    assert usertest._ticked_docs_path(sheet) == ""


# --- the version the docs name must be the version that ships ------------------------------

def _declared() -> str:
    import re
    from pathlib import Path
    t = (Path(__file__).resolve().parents[1] / "pyproject.toml").read_text()
    return re.search(r'^version\s*=\s*"([^"]+)"', t, re.M).group(1)


def test_the_readme_pins_the_version_that_is_actually_declared():
    """Round 1's tester followed the Quickstart, got 0.3.0, and read documentation describing behaviour
    it did not have — because PyPI does not treat a pre-release as "latest" and the README named no
    version. Naming a *stale* version is the same failure with an extra step, and it is the one a
    release bump introduces if the README is not part of the bump."""
    from pathlib import Path
    import re
    readme = (Path(__file__).resolve().parents[1] / "README.md").read_text()
    pinned = set(re.findall(r"archagent==([0-9][^\s`]*)", readme))
    assert pinned, "the README must pin a version while the current release is a pre-release"
    assert pinned == {_declared()}, (
        f"README pins {sorted(pinned)} but pyproject declares {_declared()}. A tester told to install "
        f"one version and handed another version's documentation measures the skew, not the tool.")


def test_the_kit_reads_the_version_rather_than_restating_it():
    """Two copies of the version is the same defect one level down: the kit would tell a tester to
    install one version and bundle another version's docs, and nothing would say so."""
    assert usertest.VERSION == _declared()
    assert usertest.TAG == f"v{_declared()}"
