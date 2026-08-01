"""The deterministic rubric — and whether it can be gamed.

The point of the paired counter-criteria (design §13.3) is that a machine-checkable criterion becomes a
target the moment anyone optimises against it. These tests build the degenerate artifacts the design names
— one glob claiming everything, documents too vague to contradict — and require the rubric to mark them
down rather than award them a perfect score.
"""

import subprocess

import pytest

from rubric import (
    check_commands_clean,
    check_covers_resolve,
    check_coverage,
    check_drift,
    check_required_documents,
    check_specificity,
    check_update_captured,
    score_deterministic,
)


def _git(root, *args):
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _repo(tmp, files):
    for rel, text in files.items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    (tmp / "archagent.toml").write_text(
        '[project]\nlanguages = ["python"]\n\n[python]\nsource_paths = ["src"]\n')
    _git(tmp, "init", "-q")
    _git(tmp, "config", "user.email", "t@example.com")
    _git(tmp, "config", "user.name", "t")
    _git(tmp, "add", "-A")
    _git(tmp, "commit", "-q", "-m", "init")
    return tmp


SRC = {f"src/pkg/{n}.py": f"# {n}\nvalue = {i}\n" for i, n in enumerate(["a", "b", "c", "d"])}
CORE = {
    "architecture/constitution.md": "# Constitution\n\nConventions.\n",
    "architecture/index.md": "# Index\n",
    "architecture/invariants.md": (
        "# Invariants\n\n| ID | Type | Tier | Applies-to | Rule | Severity | Why | Status |\n"
        "|----|------|------|-----------|------|----------|-----|--------|\n"
        "| BND-001 | BOUNDARY | structural | python | `forbid pkg.a -> pkg.b` | error | x | active |\n"),
}


def _good(tmp):
    """Two subsystems, each claiming a real slice, with typed metadata."""
    files = {**SRC, **CORE,
             "architecture/subsystems/alpha.md":
                 "# Alpha\n\n**Covers:** `src/pkg/a.py`, `src/pkg/b.py`\n**Tier:** domain\n",
             "architecture/subsystems/beta.md":
                 "# Beta\n\n**Covers:** `src/pkg/c.py`, `src/pkg/d.py`\n**Tier:** infra\n"}
    return _repo(tmp, files)


def _gamed_coverage(tmp):
    """The §13.3 degenerate case: one glob claiming the entire codebase."""
    files = {**SRC, **CORE,
             "architecture/subsystems/everything.md": "# Everything\n\n**Covers:** `src/**/*.py`\n"}
    return _repo(tmp, files)


def _vague(tmp):
    """Documents too unspecific to contradict — perfect on drift, worthless as architecture."""
    files = {**SRC,
             "architecture/constitution.md": "# Constitution\n\nWe write good code.\n",
             "architecture/index.md": "# Index\n",
             "architecture/invariants.md": "# Invariants\n\nNone yet.\n",
             "architecture/subsystems/system.md": "# System\n\nIt does things well.\n"}
    return _repo(tmp, files)


# --- the anti-gaming pairs ------------------------------------------------------------------

def test_one_glob_claiming_everything_scores_full_coverage_but_fails_its_pair(tmp_path):
    """Coverage alone would award this a perfect score for describing nothing."""
    root = _gamed_coverage(tmp_path)
    share, concentration = check_coverage(root, "architecture", set(SRC))
    assert share.score == pytest.approx(1.0), "the gamed artifact does claim every file"
    assert concentration.score < 0.5, "and the counter-criterion must say so"


def test_a_real_artifact_passes_both_coverage_criteria(tmp_path):
    root = _good(tmp_path)
    share, concentration = check_coverage(root, "architecture", set(SRC))
    assert share.score == pytest.approx(1.0) and concentration.score == pytest.approx(1.0)


def test_documents_too_vague_to_drift_score_badly_on_specificity(tmp_path):
    """Drift near zero is maximised by saying nothing. Specificity is what stops that reading as success."""
    root = _vague(tmp_path)
    assert check_drift(root, "architecture").score == pytest.approx(1.0), "nothing to contradict"
    assert check_specificity(root, "architecture").score < 0.2


def test_a_real_artifact_makes_falsifiable_claims(tmp_path):
    assert check_specificity(_good(tmp_path), "architecture").score > 0.4


# --- ADL conformance ------------------------------------------------------------------------

def test_a_missing_artifact_fails_the_gate(tmp_path):
    root = _repo(tmp_path, SRC)
    c = check_required_documents(root, "architecture")
    assert c.score == 0.0 and c.gate


def test_core_documents_without_subsystems_fail_the_gate(tmp_path):
    root = _repo(tmp_path, {**SRC, **CORE})
    assert check_required_documents(root, "architecture").score == 0.0


def test_a_dangling_covers_glob_is_marked_down(tmp_path):
    files = {**SRC, **CORE,
             "architecture/subsystems/alpha.md":
                 "# Alpha\n\n**Covers:** `src/pkg/a.py`, `src/pkg/gone.py`\n"}
    root = _repo(tmp_path, files)
    c = check_covers_resolve(root, "architecture", set(SRC))
    assert c.score == pytest.approx(0.5) and "gone.py" in c.detail


def test_covers_is_not_applicable_when_none_is_declared(tmp_path):
    root = _repo(tmp_path, {**SRC, **CORE, "architecture/subsystems/a.md": "# A\n\nprose only\n"})
    assert check_covers_resolve(root, "architecture", set(SRC)).score is None


# --- the whole card -------------------------------------------------------------------------

def test_a_real_artifact_outscores_a_vague_one(tmp_path):
    good = score_deterministic(_good(tmp_path / "good"), set(SRC), arch_dir="architecture")
    vague = score_deterministic(_vague(tmp_path / "vague"), set(SRC), arch_dir="architecture")
    assert good.deterministic_score > vague.deterministic_score


def test_a_real_artifact_outscores_the_gamed_one(tmp_path):
    """The test that justifies the paired criteria existing at all."""
    good = score_deterministic(_good(tmp_path / "good"), set(SRC), arch_dir="architecture")
    gamed = score_deterministic(_gamed_coverage(tmp_path / "gamed"), set(SRC), arch_dir="architecture")
    assert good.deterministic_score > gamed.deterministic_score


def test_an_unscoreable_artifact_reports_none_not_zero(tmp_path):
    """"Could not be scored" and "scored badly" are different claims and must not be conflated."""
    card = score_deterministic(tmp_path, set(), arch_dir="architecture")
    assert card.get("adl.covers").score is None


def test_gates_are_reported_separately(tmp_path):
    card = score_deterministic(_repo(tmp_path, SRC), set(SRC), arch_dir="architecture")
    assert "adl.required" in card.gates_failed


# --- the update run ---------------------------------------------------------------------------

def test_changes_inside_a_documented_subsystem_count_as_captured(tmp_path):
    root = _good(tmp_path)
    c = check_update_captured(root, "architecture", {"src/pkg/a.py", "src/pkg/c.py"})
    assert c.score == pytest.approx(1.0)


def test_changes_outside_every_subsystem_do_not(tmp_path):
    root = _good(tmp_path)
    c = check_update_captured(root, "architecture", {"src/pkg/a.py", "src/other/new.py"})
    assert c.score == pytest.approx(0.5)
