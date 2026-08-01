"""The held-out defect study's machinery, on synthetic data where the answer is known.

The study's whole value is that its number is not our opinion, which puts the weight on the arithmetic
being right. These tests check the three parts that could be quietly wrong: rename following, the
stratification that stops churn explaining the result by itself, and the interval.
"""

import random
import re

import pytest

from defect_study import (
    Stratum,
    analyse,
    bootstrap_interval,
    build_strata,
    churn_deciles,
    measure_outcomes,
    parse_name_status,
    rate_ratio,
    read_flagged,
    write_flagged,
)

FIX = re.compile(r"^fix", re.IGNORECASE)


def _log(*commits):
    """A `--name-status --reverse` stream: each commit is (subject, [(status, *paths)])."""
    out = []
    for subject, entries in commits:
        out.append("@@@" + subject)
        out += ["\t".join(e) for e in entries]
    return "\n".join(out)


# --- outcome measurement -------------------------------------------------------------------

def test_counts_only_defect_fixing_commits():
    log = _log(("fix: a crash", [("M", "a.py")]),
               ("feat: something", [("M", "a.py")]),
               ("fix: another", [("M", "a.py"), ("M", "b.py")]))
    out = measure_outcomes(log, FIX)
    assert out.defects == {"a.py": 2, "b.py": 1}
    assert out.commits == {"a.py": 3, "b.py": 1}
    assert (out.fix_commits, out.total_commits) == (2, 3)


def test_renames_are_followed_back_to_the_name_at_the_cutoff():
    """A file flagged at T that later moves would otherwise lose its subsequent fixes — deflating the
    signal exactly for churny files, which biases toward a null result that looks honest."""
    log = _log(("fix: before the move", [("M", "old.py")]),
               ("refactor: move it", [("R100", "old.py", "new.py")]),
               ("fix: after the move", [("M", "new.py")]))
    out = measure_outcomes(log, FIX)
    assert out.defects == {"old.py": 2}
    assert "new.py" not in out.defects


def test_a_rename_chain_is_followed_through_several_hops():
    log = _log(("refactor: one", [("R100", "a.py", "b.py")]),
               ("refactor: two", [("R100", "b.py", "c.py")]),
               ("fix: at the end", [("M", "c.py")]))
    assert measure_outcomes(log, FIX).defects == {"a.py": 1}


def test_deleted_files_are_recorded():
    log = _log(("fix: patch it", [("M", "gone.py")]),
               ("chore: remove it", [("D", "gone.py")]))
    out = measure_outcomes(log, FIX)
    assert out.deleted == {"gone.py"} and out.defects == {"gone.py": 1}


def test_a_file_re_added_after_deletion_is_not_counted_as_deleted():
    log = _log(("chore: remove", [("D", "x.py")]), ("feat: bring back", [("A", "x.py")]))
    assert measure_outcomes(log, FIX).deleted == set()


def test_two_histories_collapsing_into_one_path_are_flagged_ambiguous():
    log = _log(("refactor: one", [("R100", "a.py", "merged.py")]),
               ("refactor: two", [("R100", "b.py", "merged.py")]))
    assert measure_outcomes(log, FIX).ambiguous


def test_no_recogniser_means_no_defect_counts():
    log = _log(("fix: a crash", [("M", "a.py")]))
    assert measure_outcomes(log, None).defects == {}


def test_parse_tolerates_commits_that_touch_nothing():
    assert list(parse_name_status(_log(("chore: empty", []), ("fix: x", [("M", "a.py")])))) == [
        ("chore: empty", []), ("fix: x", [("M", ["a.py"])])]


# --- stratification -------------------------------------------------------------------------

def test_deciles_split_the_churn_distribution():
    churn = {f"f{i}.py": i for i in range(100)}
    d = churn_deciles(churn)
    assert d["f0.py"] == 0 and d["f99.py"] == 9
    assert sorted({v for v in d.values()}) == list(range(10))


def test_churn_alone_does_not_produce_a_ratio_above_one():
    """The trap the whole design is built around. Flagged files are high-churn by construction, so if
    defects merely track churn, an unstratified comparison would report a large effect. Within strata it
    must come out at 1."""
    rng = random.Random(7)
    churn = {f"f{i}.py": i % 40 for i in range(400)}
    # defects track churn and nothing else; the noise is what a real repository always has and what the
    # bootstrap needs in order to say anything
    defects = {f: max(0, c // 4 + rng.randint(-1, 1)) for f, c in churn.items()}
    flagged = {f for f, c in churn.items() if c >= 30}          # the top of the churn distribution
    result = analyse("churn-only", defects, churn, flagged, deleted=set())
    assert result.rate_ratio == pytest.approx(1.0, abs=0.35)
    assert not result.predicts, "stratification failed to absorb churn"


def test_a_zero_width_interval_is_not_treated_as_evidence():
    """Every file in a stratum carrying the same count leaves the bootstrap nothing to resample. The
    ratio may still exceed 1, but a point interval is arithmetic, not confidence."""
    churn = {f"f{i}.py": i for i in range(200)}
    defects = {f: c // 10 for f, c in churn.items()}           # deterministic: no within-stratum spread
    flagged = {f for f, c in churn.items() if c >= 150}
    result = analyse("degenerate", defects, churn, flagged, deleted=set())
    assert result.degenerate and result.rate_ratio > 1 and not result.predicts


def test_a_real_effect_is_detected():
    """Same churn distribution, but flagged files carry genuinely more defects than their decile peers."""
    rng = random.Random(11)
    churn = {f"f{i}.py": i % 20 for i in range(400)}
    flagged = {f"f{i}.py" for i in range(0, 400, 4)}
    defects = {f: max(0, c // 5 + rng.randint(-1, 1) + (6 if f in flagged else 0))
               for f, c in churn.items()}
    result = analyse("real-effect", defects, churn, flagged, deleted=set())
    assert result.rate_ratio > 1.5 and result.predicts and not result.degenerate


def test_thin_strata_are_dropped_and_reported():
    churn = {"a.py": 1, "b.py": 2}
    result = analyse("thin", {}, churn, {"a.py"}, deleted=set())
    assert result.strata_dropped and result.rate_ratio is None and not result.predicts


def test_deleted_files_are_excluded_and_counted():
    churn = {f"f{i}.py": i for i in range(50)}
    result = analyse("del", {}, churn, {"f49.py"}, deleted={"f10.py", "f11.py"})
    assert result.excluded_deleted == 2


def test_the_interval_is_reproducible():
    strata = [Stratum(decile=d, flagged=[2, 3, 1], unflagged=[1, 0, 1, 2, 0, 1]) for d in range(3)]
    assert bootstrap_interval(strata) == bootstrap_interval(strata)


def test_rate_ratio_ignores_unusable_strata():
    good = Stratum(decile=0, flagged=[4], unflagged=[1, 1, 1, 1, 1])
    thin = Stratum(decile=1, flagged=[99], unflagged=[0])       # too few controls to compare against
    assert rate_ratio([good, thin]) == rate_ratio([good])


def test_build_strata_places_every_scored_file():
    churn = {f"f{i}.py": i for i in range(30)}
    strata = build_strata({}, churn_deciles(churn), {"f29.py"})
    assert sum(len(s.flagged) + len(s.unflagged) for s in strata) == 30


# --- the ordering guard ----------------------------------------------------------------------

def test_outcomes_cannot_be_computed_before_the_flagged_set_exists(tmp_path):
    """Pre-registration made mechanical: deciding what counts as flagged after seeing which files turned
    out buggy is not a mistake anyone makes deliberately, so the harness refuses rather than trusting."""
    with pytest.raises(SystemExit, match="no flagged set"):
        read_flagged(tmp_path / "absent.json")


def test_a_written_flagged_set_round_trips(tmp_path):
    path = tmp_path / "flagged.json"
    write_flagged(path, {"files": ["a.py"], "cutoff": "2025-08-01"})
    assert read_flagged(path)["files"] == ["a.py"]


# --- power ------------------------------------------------------------------------------------

def test_run_ones_sample_size_could_not_have_seen_a_real_effect():
    """The check that should have run before run 1: at 10 flagged files against 12 controls, even a
    genuine 1.5x effect is missed almost every time. The null result carried no information."""
    from defect_study import detection_rate
    assert detection_rate(n_flagged=10, n_control=12, base_rate=0.4, true_rr=1.5, trials=60) < 0.35


def test_a_large_sample_does_see_the_same_effect():
    from defect_study import detection_rate
    assert detection_rate(n_flagged=120, n_control=240, base_rate=0.4, true_rr=1.5, trials=60) > 0.6


def test_power_is_near_the_false_positive_rate_when_there_is_no_effect():
    from defect_study import detection_rate
    assert detection_rate(n_flagged=120, n_control=240, base_rate=0.4, true_rr=1.0, trials=60) < 0.2
