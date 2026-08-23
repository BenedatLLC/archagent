"""archagent, run against archagent.

The README says this repository's artifact is "checked by `archagent check` on every commit". Until this
file existed, that was false: CI ran `pytest -q` and nothing else, no pre-commit hook was installed, and
no test pointed any of the three checks at this repo's own architecture directory.

The cost of that was demonstrated rather than argued. Planting a real STR-004 violation — `graph.py`
shelling out to `git` directly, which ADR 0003 forbids — left the suite at **815 passed** while
`archagent check` reported the violation. CI would have shipped it. It was caught by hand, and only
because somebody happened to run `check` while verifying something unrelated.

**Why a test and not only a CI step.** Both exist now; the CI steps are the integration this tool tells
its users to adopt, and running them here as well is what puts the failure in front of a contributor
before they push instead of after a round trip. All three take under a second against this repository.

These assert the *result*, not the mechanism. A test that mocked the checkers would pass on a build where
they no longer run, which is the failure this file is guarding against in the first place.
"""

from pathlib import Path

import pytest

from archagent.check import run_checks
from archagent.config import load_config
from archagent.docscan import lint_docs
from archagent.drift import find_drift
from archagent.generate import generate
from archagent.invariants import parse_invariants

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def config():
    return load_config(ROOT)


def test_archagent_holds_its_own_invariants(config):
    """The gate that would have caught STR-004.

    `--skip-pbt` is not passed: every rule in this repo's table is structural, so nothing is skipped and
    the assertion below is over the whole table rather than a subset of it.
    """
    invariants = parse_invariants(config.invariants_path)
    assert invariants, "no invariants parsed — an empty table would make every assertion here vacuous"

    gen = generate(invariants, config)
    results = run_checks(invariants, config, gen.importlinter_ids, gen.depcruiser_ids,
                         gen.astgrep_ids, gen.pbt_ids)

    # A checker that could not run reports `skipped_reason` and `passed=True`. Counting that as a pass is
    # exactly how `check` once printed "All invariants hold" having checked none of them, so the skips are
    # asserted separately from the failures.
    skipped = [r for r in results if r.skipped_reason]
    assert not skipped, [f"{r.invariant_id}: {r.skipped_reason}" for r in skipped]

    failed = [r for r in results if not r.passed and r.severity == "error"]
    assert not failed, [f"{r.invariant_id}: {r.findings[:2]}" for r in failed]

    assert len(results) == len(invariants), "every invariant must produce a result"


def test_archagents_own_documents_match_its_code(config):
    """`drift --exit-code`, as a gate.

    Stricter than what the README asks of users, where drift is informational and its output is a
    work-list. For this repository it is a gate because the artifact is offered as the worked example —
    "not a sample … this repository's own artifact" — and a worked example that has drifted teaches the
    wrong thing. The cost is real: a code change has to land with its doc update in the same commit.

    **`stale` is checked in CI and deliberately not here.** It compares the last *commit* touching a file
    against the last touching its document, so a working tree cannot answer it: the fix — editing the doc
    — does not move a commit timestamp, and the assertion stays red until it is committed. That makes it
    un-greenable locally and forces the loop backwards, committing to satisfy a test rather than testing
    before committing. CI runs on committed state, which is where the question is answerable, so
    `archagent drift --exit-code` gates it there.
    """
    result = find_drift(config)
    assert result.covers_declared, "no **Covers:** declared — the undocumented-code check would be silent"
    problems = {
        "dangling references": result.dangling,
        "undocumented modules": result.undocumented,
        "undeclared dependencies": result.undeclared_deps,
        "stale dependencies": result.stale_deps,
        "undocumented entry points": result.undocumented_entrypoints,
        "config declared but never read": result.dangling_config,
        "config read but never declared": result.undocumented_config,
        "connector-kind mismatches": result.connector_mismatches,
        "mis-tiered subsystems": result.mistiered,
    }
    assert not any(problems.values()), {k: v for k, v in problems.items() if v}


def test_archagents_own_diagrams_and_invariant_citations_are_sound(config):
    """`lint-docs --exit-code`, as a gate. Deterministic, needs no Node, and a malformed diagram is
    invisible until a human renders it — or, for an invariant ID, until a reader chases a citation that
    resolves nowhere."""
    assert lint_docs(config) == []
