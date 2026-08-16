"""The deterministic rubric — and whether it can be gamed.

The point of the paired counter-criteria (design §20.3) is that a machine-checkable criterion becomes a
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
    check_evaluate_coverage,
    check_orientation,
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
    """The §20.3 degenerate case: one glob claiming the entire codebase."""
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

# --- evaluate coverage counts only what the artifact controls ----------------------------------------

def test_a_single_process_repo_is_not_charged_for_having_no_services(tmp_path):
    """Family A needs `**Service:**` on two subsystems. A CLI has none, and declaring some to satisfy the
    rubric would mean writing a false document to raise a score — the §20.3 failure mode by the front
    door. The excuse is named in the detail so it cannot be confused with not measuring."""
    root = _repo(tmp_path, {**SRC, **CORE, "architecture/subsystems/a.md": "# A\n\n**Covers:** `src/**`\n"})
    c = check_evaluate_coverage(root)
    assert "no services to declare" in c.detail and "not declarable" in c.detail
    # B and B/C stay counted — a missing **Tier:**/**Connects:** really is an under-specified artifact
    assert c.detail.startswith("2 family/families")


def test_a_repo_that_does_deploy_services_is_still_charged(tmp_path):
    """The excuse is about the repo having nothing to declare, not about family A being optional."""
    plain = check_evaluate_coverage(
        _repo(tmp_path / "plain", {**SRC, **CORE,
                                   "architecture/subsystems/a.md": "# A\n\n**Covers:** `src/**`\n"}))
    deployed = check_evaluate_coverage(
        _repo(tmp_path / "deployed", {**SRC, **CORE,
                                      "architecture/subsystems/a.md": "# A\n\n**Covers:** `src/**`\n",
                                      "docker-compose.yml": "services:\n  web:\n    image: nginx\n"}))
    assert deployed.score < plain.score
    assert "no services to declare" not in deployed.detail


# --- orientation ------------------------------------------------------------------------------------

def test_an_index_that_is_only_a_catalog_scores_badly_on_orientation(tmp_path):
    """`describe` step 8(b) mandates the system map and the shipped template pre-places its markers.
    archagent's own artifact had neither map nor entry prose, and every check passed — nothing looked."""
    root = _repo(tmp_path, {**SRC, **CORE})
    assert check_orientation(root, "architecture").score == 0.0


def test_an_index_that_orients_before_it_catalogs_passes(tmp_path):
    root = _repo(tmp_path, {**SRC, **CORE})
    (root / "architecture/index.md").write_text(
        "# Index\n\nThis is a widget service. It accepts orders and settles them nightly.\n"
        "Read `constitution.md` first, then `subsystems/alpha.md`.\n"
        "An ADR records why; an invariant row is enforced by `check`.\n\n"
        "```mermaid\nflowchart LR\n  a --> b\n```\n\n"
        "<!-- archagent:graph-caption -->\n_What to notice: b is reached only through a._\n"
        "<!-- /archagent:graph-caption -->\n\n| Document | What |\n|---|---|\n| x | y |\n")
    assert check_orientation(root, "architecture").score == 1.0


def test_prose_after_the_catalog_does_not_count_as_orientation(tmp_path):
    """A reader meets the table first, so notes below it arrive too late to orient anyone."""
    root = _repo(tmp_path, {**SRC, **CORE})
    (root / "architecture/index.md").write_text(
        "# Index\n\n```mermaid\nflowchart LR\n  a --> b\n```\n\n| Document | What |\n|---|---|\n| x | y |\n"
        "\nThis is a widget service.\nIt accepts orders.\nIt settles them nightly.\n")
    c = check_orientation(root, "architecture")
    assert c.score < 0.5 and "prose before the catalog" in c.detail


def test_diagram_source_is_not_counted_as_entry_prose(tmp_path):
    """Otherwise one flowchart above the table satisfies both halves at once, and the map alone tells a
    reader what connects to what but never what the system is for."""
    root = _repo(tmp_path, {**SRC, **CORE})
    (root / "architecture/index.md").write_text(
        "# Index\n\n```mermaid\nflowchart LR\n  a --> b\n  b --> c\n  c --> d\n```\n\n"
        "| Document | What |\n|---|---|\n| x | y |\n")
    assert check_orientation(root, "architecture").score < 0.5


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


# --- the specificity target scales with the codebase -------------------------------------------

def test_the_target_grows_with_the_codebase_but_sublinearly():
    """A flat constant asks the same of a 20-file project and a 10,000-file monorepo, so it is either
    trivial for one or negligible for the other. Subsystems aggregate, so the target grows with the
    square root rather than linearly."""
    from rubric import expected_claims
    small, medium, large = expected_claims(20), expected_claims(400), expected_claims(10_000)
    assert small < medium < large
    assert large < 500 * small, "linear growth would make a large repo's target absurd"


def test_the_target_has_a_floor_for_tiny_and_unknown_repositories():
    from rubric import expected_claims
    assert expected_claims(0) == expected_claims(1) >= 8


def test_the_target_is_capped():
    from rubric import expected_claims
    assert expected_claims(10_000) == expected_claims(200_000)


def test_the_same_artifact_scores_lower_against_a_larger_codebase(tmp_path):
    """The behaviour the scaling exists for: twelve claims is thorough for a handful of files and
    negligible for thousands."""
    root = _good(tmp_path)
    small = check_specificity(root, "architecture", n_source_files=4)
    large = check_specificity(root, "architecture", n_source_files=5000)
    assert small.score > large.score
    assert "target of" in large.detail and "5000 source file" in large.detail


def test_a_vague_artifact_still_scores_zero_at_any_size(tmp_path):
    root = _vague(tmp_path)
    assert check_specificity(root, "architecture", 10).score == 0.0
    assert check_specificity(root, "architecture", 10_000).score == 0.0


# --- no single kind of claim may carry the score ------------------------------------------------

def _metadata_only(tmp, n=20):
    """Twenty subsystems annotated with Tier and Service and nothing else: no Covers, no invariants.
    Cheap to type, and it says nothing about which code belongs where."""
    files = {**SRC, "architecture/constitution.md": "# C\n", "architecture/index.md": "# I\n",
             "architecture/invariants.md": "# Invariants\n\nNone.\n"}
    for i in range(n):
        files[f"architecture/subsystems/s{i}.md"] = f"# S{i}\n\n**Tier:** domain\n**Service:** api\n"
    return _repo(tmp, files)


def test_metadata_alone_cannot_reach_a_full_score(tmp_path):
    """The over-weighting this fixes: counting raw markers let one-line annotations carry the score."""
    c = check_specificity(_metadata_only(tmp_path), "architecture", n_source_files=200)
    assert c.score <= 0.5, "one kind of claim must not be able to satisfy the target alone"
    assert "capped" in c.detail


def test_a_balanced_artifact_beats_a_metadata_heavy_one(tmp_path):
    balanced = check_specificity(_good(tmp_path / "b"), "architecture", n_source_files=4)
    heavy = check_specificity(_metadata_only(tmp_path / "h"), "architecture", n_source_files=4)
    assert balanced.score > heavy.score


def test_config_keys_are_counted_individually(tmp_path):
    """`**Config:** A, B, C` is three claims — drift reports each key separately. Counting the line once
    made the granularity depend on how the author punctuated."""
    from rubric import claim_counts
    one = _repo(tmp_path / "one", {**SRC, **CORE,
                                   "architecture/subsystems/a.md": "# A\n\n**Config:** ONE_KEY\n"})
    many = _repo(tmp_path / "many", {**SRC, **CORE,
                                     "architecture/subsystems/a.md":
                                         "# A\n\n**Config:** ONE_KEY, TWO_KEY, THREE_KEY\n"})
    assert claim_counts(many, "architecture")["metadata"] > claim_counts(one, "architecture")["metadata"]


def test_connector_edges_are_counted_individually(tmp_path):
    from rubric import claim_counts
    root = _repo(tmp_path, {**SRC, **CORE, "architecture/subsystems/a.md":
                            "# A\n\n**Connects:** beta via sync-call, gamma via async-event\n"})
    assert claim_counts(root, "architecture")["metadata"] == 2


def test_an_unwritten_graph_caption_does_not_count_as_captioned(tmp_path):
    """`graph --write` seeds a placeholder so an artifact that never filled it in is visible. A slot
    still holding the placeholder is worse than no slot: it looks answered."""
    root = _repo(tmp_path, {**SRC, **CORE})
    body = ("# Index\n\nThis is a widget service. It accepts orders.\nIt settles them nightly.\n"
            "An ADR records why; an invariant row is enforced by `check`.\n\n"
            "```mermaid\nflowchart LR\n  a --> b\n```\n\n"
            "<!-- archagent:graph-caption -->\n{cap}\n<!-- /archagent:graph-caption -->\n\n"
            "| Document | What |\n|---|---|\n| x | y |\n")
    (root / "architecture/index.md").write_text(
        body.format(cap="_What to notice: (unwritten — say what this map shows about **this** system.)_"))
    c = check_orientation(root, "architecture")
    assert c.score < 1.0 and "caption" in c.detail

    (root / "architecture/index.md").write_text(
        body.format(cap="_What to notice: b is reached only through a._"))
    assert check_orientation(root, "architecture").score == 1.0
