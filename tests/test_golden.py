"""Golden-output tests — the regression net for *aggregate* behaviour.

Every other test here checks one filter in isolation, and that is exactly what let a real regression
through: enabling enum-member branching made union-find bridge unrelated clusters, the cohesion bar then
dropped the over-merged blob, and a confirmed finding silently disappeared. Every unit test still passed.
The bug lived in the interaction, so the net has to be a snapshot of the whole output.

**What is pinned is a projection, not the raw JSON.** Recommendation prose is rewritten often and
deliberately; a golden file that breaks on wording gets regenerated reflexively and stops being a check.
So the snapshot keeps the machine-shaped fields — sign, group, severity, confidence, subjects, the value
set, and the coverage/profile summary — and drops the sentences. Finding *order* is preserved, because
for the ranked signals the order is part of the claim.

Regenerate deliberately, and read the diff:

    ARCHAGENT_UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py

A green run here means behaviour is *stable*, not that it is *right* on real code — the fixtures are
hand-shaped. Realism is the corpus pass in `research/architecture-agent/feedback/probe-results.md`, which
is periodic and manual. Keep both.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pytest

from archagent.evaluate import evaluate
from fixture_repos import main_repo, tracker_repo

GOLDEN_DIR = Path(__file__).parent / "golden"
_VALUES = re.compile(r"\{([^}]*)\}")


def _values_of(detail: str) -> list[str] | None:
    """The value set a group-F finding is about — the one part of `detail` that is data, not prose."""
    m = _VALUES.search(detail)
    if not m:
        return None
    return [v.strip() for v in m.group(1).split(",") if v.strip()]


def project(result) -> dict:
    return {
        "findings": [
            {
                "sign": f.sign,
                "group": f.group,
                "severity": f.severity,
                "confidence": f.confidence,
                "regime": f.regime,
                "subjects": f.subjects,
                "values": _values_of(f.detail),
            }
            for f in result.findings
        ],
        "inactive": [i.family for i in result.inactive],
        "truncated": [[fam, shown, found] for fam, shown, found in result.truncated],
        "history": {
            "commits_seen": result.commits_seen,
            "commits_analyzed": result.history_analyzed,
            "profile_style": result.history_profile.style if result.history_profile else None,
            "fix_matched": result.history_profile.fix_matched if result.history_profile else None,
            "subjects_sampled": (
                result.history_profile.subjects_sampled if result.history_profile else None),
        },
    }


def _check(name: str, actual: dict) -> None:
    path = GOLDEN_DIR / f"{name}.json"
    text = json.dumps(actual, indent=2, sort_keys=False) + "\n"
    if os.environ.get("ARCHAGENT_UPDATE_GOLDEN"):
        GOLDEN_DIR.mkdir(exist_ok=True)
        path.write_text(text)
        pytest.skip(f"golden updated: {path.name}")
    assert path.exists(), f"missing golden {path} — run with ARCHAGENT_UPDATE_GOLDEN=1"
    assert json.loads(text) == json.loads(path.read_text()), (
        f"{name} output changed.\n\nIf the change is intended, re-read the diff to confirm it is *only* "
        f"what you meant, then:\n  ARCHAGENT_UPDATE_GOLDEN=1 uv run pytest tests/test_golden.py"
    )


@pytest.fixture(scope="module")
def main_result(tmp_path_factory):
    return evaluate(main_repo(tmp_path_factory.mktemp("golden-main")))


@pytest.fixture(scope="module")
def tracker_result(tmp_path_factory):
    return evaluate(tracker_repo(tmp_path_factory.mktemp("golden-tracker")))


def test_main_fixture_output_is_unchanged(main_result):
    _check("main", project(main_result))


def test_tracker_fixture_output_is_unchanged(tracker_result):
    _check("tracker", project(tracker_result))


# --- the cases the fixture exists to hold, asserted by name -------------------------------
#
# The snapshot above catches *unanticipated* change; these say out loud what each case is for, so a
# regenerated golden cannot quietly bless the loss of one. They are the labelled verdicts from the
# evaluation pass, encoded.

def _subjects(result, sign):
    return {tuple(f.subjects) for f in result.findings if f.sign == sign}


def _all_subjects(result, sign):
    return {s for f in result.findings if f.sign == sign for s in f.subjects}


def test_the_confirmed_duplicated_decision_is_found(main_result):
    owned = _subjects(main_result, "scattered-source-of-truth")
    assert any(s[0] == "src/orders/state.py" for s in owned)


def test_the_intended_family_still_surfaces(main_result):
    """It is a dismissal, not a suppression — the reviewer decides. If that ever changes, this fails."""
    assert any(s[0] == "src/backends/base.py"
               for s in _subjects(main_result, "scattered-source-of-truth"))


def test_enum_member_dispatch_is_found(main_result):
    assert any(s[0] == "src/dispatch/router.py"
               for s in _subjects(main_result, "scattered-source-of-truth"))


def test_the_chain_grab_bag_is_rejected(main_result):
    """Cohesion. A ring of neighbour-sharing values is not one decision, however tight its owner looks."""
    assert not any("src/chain/" in s for s in _all_subjects(main_result, "scattered-source-of-truth"))


def test_keyboard_keys_are_rejected(main_result):
    assert not any("src/ui/" in s for s in _all_subjects(main_result, "scattered-source-of-truth"))


def test_vendored_and_generated_files_never_appear(main_result):
    everywhere = {s for f in main_result.findings for s in f.subjects}
    assert not any("src/vendor/" in s or "emitted" in s for s in everywhere)


def test_only_the_file_high_on_both_axes_is_a_hotspot(main_result):
    """Churny-but-flat and complex-but-stable must both stay out, or the product bar means nothing."""
    assert _all_subjects(main_result, "change-prone-file") == {"src/perf/hot.py"}


def test_all_three_enum_escape_variants_are_distinguished(main_result):
    """Each variant needs different advice, so each must be recognised separately: a Python enum has no
    checker, a TypeScript one is already guarded by tsc, and across the boundary no import exists."""
    by_owner = {f.subjects[0]: f for f in main_result.findings if f.sign == "enum-value-escape"}
    assert set(by_owner) == {"src/enums/workflow.py", "src/enums/mode.py", "src/web/kinds.ts"}

    same_language_python = by_owner["src/enums/workflow.py"]
    assert "Compare against the JobState member itself" in same_language_python.recommendation
    assert "TS2367" not in same_language_python.recommendation

    cross_language = by_owner["src/enums/mode.py"]
    assert "cannot import" in cross_language.recommendation
    assert cross_language.confidence == "med"      # nothing links the two sides, so no coincidence
    assert cross_language.title.endswith("across a language boundary")

    typescript_only = by_owner["src/web/kinds.ts"]
    assert "TS2367" in typescript_only.recommendation
    assert typescript_only.confidence == "low"     # the compiler is already the guard


def test_the_tracker_fixture_pins_the_issue_closing_trap(tracker_result):
    """`closes #N` / `resolves #N` trail features and docs here and must not be read as fixes — the bug
    that made datasette report a 17% fix rate against an actual 10%."""
    profile = tracker_result.history_profile
    assert profile.fix_matched == 5          # 4 `Fixed #NNN` + 1 `Fix the rounding error`
    assert profile.subjects_sampled == 15    # ... out of 15, 9 of which close an issue


def test_enum_members_do_not_bridge_the_two_mixed_clusters(main_result):
    """The regression this whole fixture exists for. `src/mixed` holds two unrelated string clusters whose
    files all branch on `RunMode.ACTIVE` as well. Cluster the two vocabularies together and that member
    bridges them into one incoherent blob, which the cohesion bar then drops — losing both real findings
    with no error anywhere."""
    owners = {f.subjects[0] for f in main_result.findings if f.sign == "scattered-source-of-truth"}
    assert {"src/mixed/auth0.py", "src/mixed/theme0.py"} <= owners
