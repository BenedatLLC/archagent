"""Properties of the shipped agent prompts.

The prompts are data, not code — nothing imports them and no test exercised their content, so a wrong
instruction survived until someone read it. These are the few claims worth asserting: that the hand-off
between two skills is an instruction rather than an allusion, and that no prompt tells a reader to distort
the architecture model in order to quiet a signal.
"""

from pathlib import Path

import pytest

PHASES = Path(__file__).resolve().parents[1] / "src" / "archagent" / "templates" / "agent" / "phases"


def _prompt(name: str) -> str:
    return (PHASES / f"{name}.md").read_text()


def test_describe_invokes_the_evaluate_skill_by_name():
    """`describe` runs `archagent evaluate` and the raw output is candidates, not conclusions. It used to
    say "the `evaluate` skill judges the candidates" without naming the slash command, which left the
    hand-off to chance — and a user who lands on raw signals at the end of a long describe run has the
    interpretation guide nowhere in front of them."""
    text = _prompt("describe")
    assert "/archagent-evaluate" in text
    # in the main flow, not only in a parenthesis further down
    step7 = text[text.index("7. **Evaluate health.**"):text.index("8. **Index + log.**")]
    assert "/archagent-evaluate" in step7


def test_no_prompt_advises_re_tiering_to_silence_a_finding():
    """`describe` used to suggest modelling flat peers as a single tier "rather than forcing a strict
    ladder" — advice to distort the model to quiet a false positive that has since been fixed twice, and
    the opposite of what issue #26 established. The artifact has to keep describing the system."""
    for name in ("describe", "evaluate"):
        text = _prompt(name).lower()
        assert "rather than forcing a strict" not in text, name
        assert "as a single `domain` tier" not in text, name


def test_the_layering_guidance_lives_in_the_evaluate_prompt():
    """Reading a signal is `evaluate`'s job. The `layer-skip` caveats used to sit in `describe` while
    `evaluate` — the skill whose entire purpose is interpreting signals — did not mention the sign at
    all."""
    assert "layer-skip" in _prompt("evaluate")


def test_the_layering_guidance_does_not_overclaim_when_a_skip_fires():
    """It used to say a shared kernel "will always show layer-skip" and that flat peers show skips
    "whenever the orchestrator calls a capability directly". Neither survives the narrowing: a skip needs
    the intermediate tier to be occupied, so `app -> domain` reports nothing at all."""
    text = _prompt("evaluate")
    assert "always show `layer-skip`" not in text
    assert "only when some subsystem actually occupies the tier being skipped" in text


def test_the_non_layered_tier_tokens_are_offered_where_a_tier_is_chosen():
    """A reader deciding a subsystem's tier needs to know that "not a layer" is available; otherwise
    `infra` is the natural pick for tests, which is exactly how the false positives arose."""
    text = _prompt("describe")
    assert "`test` / `migration` / `ops`" in text


@pytest.mark.parametrize("name", ["describe", "evaluate", "check", "invariant", "help"])
def test_every_shipped_phase_prompt_is_non_empty(name):
    """A guard on the packaging rather than the wording: these ship as package data, and an empty one
    would silently give an agent no instructions at all."""
    assert len(_prompt(name).split()) > 50


def test_nothing_still_refers_to_the_artifact_index_as_index_md():
    """Issue #28 renamed the artifact's index to `README.md`. The rename touched the tool, the spec and
    the prompts and missed `tests/rubric.py`, where the deterministic rubric scored a correct artifact
    0.00 on "Artifact is enterable" and failed its `adl.required` gate — on dspy, in round 5, after the
    artifact was written.

    The gates in `tests/test_self.py` could not catch it: the rubric is evaluation harness, not shipped
    code, so nothing exercised it."""
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    # Scoped to the modules that *decide* what the artifact's index is called. A fixture elsewhere may
    # legitimately create a file called `index.md` — that is an arbitrary document name in a test project,
    # not a claim about the format.
    for name in ("rubric.py", "rubric_judged.py", "findings.py"):
        f = root / "tests" / name
        if f.is_file():
            assert "index.md" not in f.read_text(), name
    for f in (root / "scripts").glob("*.py"):
        assert "index.md" not in f.read_text(), f.name
