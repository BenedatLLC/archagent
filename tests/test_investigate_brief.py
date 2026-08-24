"""`investigate` briefs must ask questions that belong to their finding.

The brief used to take its header, evidence and triage reason from the finding and its *questions* from
a single global list written for the value-set signs. So a `change-prone-file` brief reported churn and
complexity correctly and then asked the reader to find duplicated enum declarations and compare them
member by member. Round 1's user tester named it the most useless thing the tool told them (#34).

The shape of that bug is what these tests guard: sign-correct in its evidence, sign-wrong in its
questions, and nothing anywhere noticed.
"""

import pytest

from archagent.cli import _BRIEF_QUESTIONS, _BRIEF_RATINGS


def _triaged_signs() -> set[str]:
    """Every sign that can be flagged for investigation, read from the source rather than restated.

    A restated list would drift: the failure this guards is a *new* triaged sign quietly inheriting
    another sign's questions, and a hand-maintained copy would be updated in the same commit that
    forgets the questions.
    """
    import re
    from pathlib import Path
    src = Path(__file__).resolve().parents[1] / "src" / "archagent" / "evaluate.py"
    return set(re.findall(r'_triage\(\s*"([a-z-]+)"', src.read_text()))


def test_every_triaged_sign_has_its_own_questions():
    """The gap this closes: a sign gains `investigate=True` and silently borrows the previous sign's
    questionnaire, which reads as authoritative and sends the reader looking for something not there."""
    missing = _triaged_signs() - set(_BRIEF_QUESTIONS)
    assert not missing, (
        f"{sorted(missing)} can be flagged for investigation but has no questions in _BRIEF_QUESTIONS. "
        f"Write them — printing another sign's is worse than printing none.")


def test_every_sign_with_questions_has_matching_ratings():
    """The ratings describe what minor/moderate/critical *mean* for this sign, so they cannot be shared
    across signs either: the value-set ratings talk about 'the duplication'."""
    assert set(_BRIEF_QUESTIONS) == set(_BRIEF_RATINGS)


def test_change_prone_questions_are_about_churn_not_enums():
    """The specific regression. `change-prone-file` measures churn against complexity; nothing about it
    concerns duplicated value sets."""
    text = " ".join(q + " " + d for q, d in _BRIEF_QUESTIONS["change-prone-file"]).lower()
    for foreign in ("enum", "literal type", "typeddict", "value set", "member by member"):
        assert foreign not in text, f"{foreign!r} belongs to the value-set signs"
    assert "churn" in text and "commits" in text


def test_the_value_set_signs_kept_their_questions():
    """The fix must not have moved the correct questions off the signs they were written for."""
    for sign in ("scattered-source-of-truth", "enum-value-escape"):
        text = " ".join(q for q, _ in _BRIEF_QUESTIONS[sign]).lower()
        assert "declared" in text


def test_a_sign_with_no_questions_prints_nothing_rather_than_borrowing():
    """There is no default, on purpose — the same reasoning as METRIC_KEYS in the ledger."""
    assert _BRIEF_QUESTIONS.get("god-component") is None
