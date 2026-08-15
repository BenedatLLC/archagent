"""The leave-one-out threshold check — does it actually detect a value fitted to one repository?

Synthetic step functions, deliberately. A detector validated only against real sweeps proves nothing: you
cannot tell a true negative from a detector that never fires. Here the ground truth is constructed, so a
miss is visible.
"""

import pytest

from thresholds import Sweep, leave_one_out, measure, plateau

VALUES = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)


def _sweep(name, chosen, counts):
    return Sweep(name=name, chosen=chosen, values=VALUES,
                 counts={k: tuple(v) for k, v in counts.items()})


# --- the shape we want to catch ------------------------------------------------------------------

def test_a_value_pinned_by_one_repository_is_named():
    """alpha's count changes right at 0.6; beta and gamma are flat across the whole range. Drop alpha and
    any value would have done — which is the definition of a value chosen for alpha."""
    v = _sweep("COHESION", 0.6, {
        "alpha": [9, 9, 9, 9, 9, 4, 4, 4, 4],     # steps exactly at the chosen value
        "beta":  [2, 2, 2, 2, 2, 2, 2, 2, 2],
        "gamma": [3, 3, 3, 3, 3, 3, 3, 3, 3],
    })
    verdict = leave_one_out(v)
    assert verdict.pinned_by == ["alpha"]
    assert not verdict.ok
    assert "PINNED BY THIS REPO" in verdict.report()


def test_a_value_every_repository_agrees_on_is_clean():
    """All three step in the same place, so no single repo is holding the value there."""
    v = _sweep("COHESION", 0.6, {
        "alpha": [9, 9, 9, 9, 9, 4, 4, 4, 4],
        "beta":  [6, 6, 6, 6, 6, 3, 3, 3, 3],
        "gamma": [5, 5, 5, 5, 5, 2, 2, 2, 2],
    })
    verdict = leave_one_out(v)
    assert verdict.pinned_by == [] and verdict.ok
    assert "no repository is doing the work alone" in verdict.report()


def test_a_repository_on_a_cliff_alone_is_named():
    """Everyone is flat around the chosen value except one, whose count falls off a step there. The
    number is doing delicate work for exactly one repository."""
    v = _sweep("MIN_FILES_PER_VALUE", 0.5, {
        "alpha": [7, 7, 7, 7, 7, 1, 1, 1, 1],     # cliff between 0.5 and 0.6
        "beta":  [4, 4, 4, 4, 4, 4, 4, 4, 4],
        "gamma": [2, 2, 2, 2, 2, 2, 2, 2, 2],
    })
    verdict = leave_one_out(v)
    assert verdict.on_a_cliff_for == ["alpha"]
    assert "ON A CLIFF" in verdict.report()


# --- the silence problem (§18) --------------------------------------------------------------------

def test_a_repository_that_never_fires_supports_nothing():
    """A repo producing zero findings at every value agrees with everything, and must not be counted as
    agreement. This is the opportunity-denominator rule: 12 of 14 corpus repos had no HTTP server, so
    their silence about permissive-origin was not evidence."""
    v = _sweep("COHESION", 0.6, {
        "alpha": [9, 9, 9, 9, 9, 4, 4, 4, 4],
        "quiet": [0, 0, 0, 0, 0, 0, 0, 0, 0],
    })
    verdict = leave_one_out(v)
    assert verdict.silent == ["quiet"]
    assert verdict.opportunity["quiet"] == 0
    assert "supports nothing" in verdict.report()
    # and alpha is still correctly identified as the only voice
    assert verdict.pinned_by == ["alpha"]


def test_silence_does_not_mask_a_pinned_value():
    """Two silent repos plus one that pins the value must still report the pin, not average it away."""
    v = _sweep("COHESION", 0.6, {
        "alpha": [9, 9, 9, 9, 9, 4, 4, 4, 4],
        "q1":    [0] * 9,
        "q2":    [0] * 9,
    })
    assert leave_one_out(v).pinned_by == ["alpha"]


# --- plateau mechanics ----------------------------------------------------------------------------

def test_the_plateau_is_the_range_where_nothing_changes():
    v = _sweep("X", 0.4, {"a": [5, 5, 3, 3, 3, 3, 1, 1, 1]})
    assert plateau(v, ["a"], 0.4) == pytest.approx((0.3, 0.6))


def test_an_empty_repo_list_gives_the_whole_range():
    """Dropping the last speaking repository leaves nothing to constrain the value."""
    v = _sweep("X", 0.4, {"a": [5, 5, 3, 3, 3, 3, 1, 1, 1]})
    assert plateau(v, [], 0.4) == (0.1, 0.9)


def test_measure_builds_the_grid_by_calling_the_counter():
    seen = []

    def count(repo, value):
        seen.append((repo, value))
        return 1 if value < 0.5 else 0

    s = measure("T", 0.5, [0.3, 0.5, 0.7], count, ["r1", "r2"])
    assert s.values == (0.3, 0.5, 0.7)
    assert s.counts["r1"] == (1, 0, 0)
    assert len(seen) == 6


# --- guarding the detector itself -----------------------------------------------------------------

def test_a_flat_world_reports_nothing_rather_than_everything():
    """If no repository responds to the threshold at all, there is nothing to pin and the check must not
    manufacture a finding — the value is simply unconstrained by this evidence."""
    v = _sweep("X", 0.5, {"a": [3] * 9, "b": [4] * 9})
    verdict = leave_one_out(v)
    assert verdict.pinned_by == [] and verdict.on_a_cliff_for == []
    assert verdict.agreed == (0.1, 0.9)


# --- reading the verdict with the right amount of confidence ---------------------------------------

def test_a_threshold_nothing_responds_to_is_unconstrained_not_agreed():
    """TIGHTNESS = 0.6 produced an identical count at every value on all three corpus repositories. That
    is not three repositories agreeing on 0.6; it is no evidence about 0.6 at all, and the two must not
    print the same way."""
    v = _sweep("TIGHTNESS", 0.6, {"a": [2] * 9, "b": [1] * 9})
    verdict = leave_one_out(v)
    assert verdict.unconstrained
    assert "UNCONSTRAINED" in verdict.report()
    assert "no repository is doing the work alone" not in verdict.report()


def test_a_verdict_resting_on_two_findings_says_so():
    """"Pinned by django" on 2 findings and on 200 are different claims. The check cannot tell them
    apart, so the report must."""
    v = _sweep("COHESION", 0.6, {
        "alpha": [2, 2, 2, 2, 2, 1, 1, 1, 1],
        "beta":  [1, 1, 1, 1, 1, 1, 1, 1, 1],
    })
    verdict = leave_one_out(v)
    assert set(verdict.thin) == {"alpha", "beta"}
    assert "THIN" in verdict.report()


def test_plenty_of_findings_is_not_flagged_thin():
    v = _sweep("COHESION", 0.6, {
        "alpha": [90, 90, 90, 90, 90, 40, 40, 40, 40],
        "beta":  [60, 60, 60, 60, 60, 30, 30, 30, 30],
    })
    assert leave_one_out(v).thin == []


def test_a_threshold_everything_responds_to_endorses_nothing():
    """PCTILE_BAR: all three repos' counts change at every step, so the plateau is a single point however
    many you drop — "not pinned" is then guaranteed by the arithmetic rather than earned. The check asks
    who holds a value in place, never whether the value is right, and must not read as endorsement."""
    v = _sweep("PCTILE_BAR", 0.5, {
        "alpha": [90, 80, 70, 60, 50, 40, 30, 20, 10],
        "beta":  [45, 40, 35, 30, 25, 20, 15, 10, 5],
    })
    verdict = leave_one_out(v)
    assert verdict.unranked and verdict.pinned_by == []
    assert "UNRANKED" in verdict.report()
    assert "no repository is doing the work alone" not in verdict.report()


def test_a_genuinely_agreed_value_is_still_reported_as_agreed():
    """Shared plateaus with a shared step: not unranked, because the value range is actually constrained."""
    v = _sweep("X", 0.6, {
        "alpha": [9, 9, 9, 9, 9, 4, 4, 4, 4],
        "beta":  [6, 6, 6, 6, 6, 3, 3, 3, 3],
    })
    verdict = leave_one_out(v)
    assert not verdict.unranked
    assert "no repository is doing the work alone" in verdict.report()
