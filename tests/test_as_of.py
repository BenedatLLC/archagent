"""Running as of a past commit — the prerequisite for every evaluation in
`docs/designs/evaluating-archagent.md`.

Three separate paths read the repository and each one reads the present unless told otherwise: the
co-change miner, the commit-wording profile, and `drift`'s staleness comparison. A fourth — the file
contents themselves — cannot be bounded by a flag at all and is the caller's job, which is why the
mismatch warning exists.
"""

import subprocess

from archagent.cochange import mine_cochange, resolve_as_of, tree_newer_than
from archagent.config import Config, PythonConfig, TSConfig
from archagent.drift import find_drift
from archagent.evaluate import evaluate
from archagent.history import HistoryProfile, history_profile, save_profile

EARLY = "2020-01-01T00:00:00 +0000"
LATE = "2024-01-01T00:00:00 +0000"
CUTOFF = "2022-01-01"


def _git(root, *args, date=None):
    env = None
    if date:
        import os
        env = {**os.environ, "GIT_AUTHOR_DATE": date, "GIT_COMMITTER_DATE": date}
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True, env=env)


def _repo(tmp):
    _git(tmp, "init", "-q")
    _git(tmp, "config", "user.email", "t@example.com")
    _git(tmp, "config", "user.name", "t")
    (tmp / "architecture" / "subsystems").mkdir(parents=True)
    return Config(
        project_root=tmp, languages=["python"],
        python=PythonConfig(root_package="pkg", source_paths=["src"]),
        ts=TSConfig(source_paths=["src"]),
    )


def _commit(cfg, msg, files, date):
    for rel, content in files.items():
        p = cfg.project_root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    _git(cfg.project_root, "add", "-A")
    _git(cfg.project_root, "commit", "-q", "-m", msg, date=date)


def _two_era_repo(tmp):
    """Three commits in 2020, three in 2024 — so a 2022 cutoff must halve everything."""
    cfg = _repo(tmp)
    for i in range(3):
        _commit(cfg, f"old change {i}", {"src/pkg/a.py": f"old{i}\n"}, EARLY)
    for i in range(3):
        _commit(cfg, f"fix: new change {i}", {"src/pkg/a.py": f"new{i}\n"}, LATE)
    return cfg


# --- the miner ----------------------------------------------------------------------------

def test_until_bounds_the_commit_window(tmp_path):
    cfg = _two_era_repo(tmp_path)
    assert mine_cochange(tmp_path, {}).commits_seen == 6
    assert mine_cochange(tmp_path, {}, until=CUTOFF).commits_seen == 3


def test_until_bounds_per_file_churn(tmp_path):
    cfg = _two_era_repo(tmp_path)
    assert mine_cochange(tmp_path, {}, until=CUTOFF).file_commits["src/pkg/a.py"] == 3


def test_since_and_until_compose(tmp_path):
    cfg = _two_era_repo(tmp_path)
    assert mine_cochange(tmp_path, {}, since="2019-01-01", until=CUTOFF).commits_seen == 3


# --- the commit-wording profile -----------------------------------------------------------

def test_until_bounds_the_subject_sample(tmp_path):
    """The leakage that is easy to miss: without this the recogniser is learned from commits made after
    the cutoff and then used to label commits from before it."""
    cfg = _two_era_repo(tmp_path)
    full = history_profile(tmp_path)
    bounded = history_profile(tmp_path, until=CUTOFF)
    assert full.subjects_sampled == 6 and bounded.subjects_sampled == 3
    # only the 2024 commits say "fix:", so a bounded run must not learn that convention
    assert full.fix_patterns and not bounded.fix_patterns


def test_a_bounded_run_ignores_a_full_history_cache(tmp_path):
    """A cached profile carries no record of the window it was learned over, so reusing one in a bounded
    run silently reintroduces the leakage the bound exists to prevent."""
    cfg = _two_era_repo(tmp_path)
    save_profile(tmp_path, HistoryProfile(style="cached-from-full", fix_patterns=[r"^fix"],
                                          subjects_sampled=999))
    assert history_profile(tmp_path).style == "cached-from-full"          # unbounded: cache wins
    assert history_profile(tmp_path, until=CUTOFF).style != "cached-from-full"


def test_the_window_is_recorded_on_the_profile(tmp_path):
    cfg = _two_era_repo(tmp_path)
    assert history_profile(tmp_path, until=CUTOFF).until == CUTOFF
    assert history_profile(tmp_path).until is None


# --- resolving a revision, and the tree/history mismatch ----------------------------------

def test_as_of_reads_a_revisions_own_date(tmp_path):
    cfg = _two_era_repo(tmp_path)
    _git(tmp_path, "tag", "v1")
    assert resolve_as_of(tmp_path, "v1").startswith("2024-01-01")


def test_as_of_passes_a_plain_date_through(tmp_path):
    _two_era_repo(tmp_path)
    assert resolve_as_of(tmp_path, "2021-06-01") == "2021-06-01"


def test_tree_newer_than_detects_the_mismatch(tmp_path):
    cfg = _two_era_repo(tmp_path)
    assert tree_newer_than(tmp_path, CUTOFF)          # HEAD is 2024, window ends 2022
    assert not tree_newer_than(tmp_path, "2025-01-01")


def test_evaluate_warns_when_the_tree_is_newer_than_the_window(tmp_path):
    """Bounding history without checking out the matching code is the one mistake this option invites,
    and it produces no visible symptom — the complexity numbers simply describe the wrong files."""
    cfg = _two_era_repo(tmp_path)
    caution = evaluate(cfg, until=CUTOFF).history_cautions[0]
    assert "checked-out tree is newer" in caution
    assert "git worktree add" in caution
    assert not any("checked-out tree is newer" in c for c in evaluate(cfg).history_cautions)


def test_evaluate_passes_the_window_to_the_miner(tmp_path):
    cfg = _two_era_repo(tmp_path)
    assert evaluate(cfg).commits_seen == 6
    assert evaluate(cfg, until=CUTOFF).commits_seen == 3


# --- drift ---------------------------------------------------------------------------------

def test_drift_staleness_respects_the_window(tmp_path):
    """The doc was written after the code in 2020 and the code changed again in 2024. Bounded to 2022 the
    doc is current; unbounded it is stale."""
    cfg = _repo(tmp_path)
    _commit(cfg, "code", {"src/pkg/a.py": "v0\n"}, EARLY)
    _commit(cfg, "doc", {"architecture/subsystems/pkg.md": "# Pkg\n\n**Covers:** `src/pkg/*.py`\n"}, EARLY)
    _commit(cfg, "later code change", {"src/pkg/a.py": "v1\n"}, LATE)

    assert find_drift(cfg).stale
    assert not find_drift(cfg, until=CUTOFF).stale


# --- a failed history walk must not look like a clean repository --------------------------

def test_a_failed_git_walk_is_reported_not_silently_empty(tmp_path, monkeypatch):
    """Found by the corpus harness: on a large repo the `git log --name-only` walk exceeded the miner's
    timeout, `_git` returned None, and `mine_cochange` returned all-zero counts. Every history signal went
    quiet and the run read as clean — and that run was recorded as a regression baseline before anyone
    noticed."""
    import archagent.cochange as cochange

    cfg = _two_era_repo(tmp_path)
    monkeypatch.setattr(cochange, "_git", lambda *a, **kw: None)

    cc = cochange.mine_cochange(tmp_path, {})
    assert cc.mining_failed and cc.commits_seen == 0

    result = evaluate(cfg)
    assert result.mining_failed
    assert "history walk FAILED" in result.history_cautions[0]
    assert any("history walk failed" in reason for _, reason in result.inactive)


def test_a_healthy_walk_is_not_flagged_as_failed(tmp_path):
    cfg = _two_era_repo(tmp_path)
    result = evaluate(cfg)
    assert not result.mining_failed
    assert not any("history walk FAILED" in c for c in result.history_cautions)


# --- references that are real but unanalysable (found on signalfx/obstudio) ------------------------

def _repo_with_go(tmp_path):
    """A repo whose core is Go, with archagent configured for Python only."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src/app.py").write_text("x = 1\n")
    (tmp_path / "svc").mkdir()
    (tmp_path / "svc/main.go").write_text("package main\n")
    (tmp_path / "svc/store.go").write_text("package main\n")
    (tmp_path / "archagent.toml").write_text(
        '[project]\nlanguages = ["python"]\n\n[python]\nsource_paths = ["src"]\n')
    arch = tmp_path / "architecture/subsystems"
    arch.mkdir(parents=True)
    (tmp_path / "architecture/constitution.md").write_text("# C\n")
    (tmp_path / "architecture/index.md").write_text("# I\n")
    (tmp_path / "architecture/invariants.md").write_text("# Inv\n")
    return tmp_path


def test_a_glob_in_backticks_is_not_a_missing_file(tmp_path):
    """`**Covers:** `svc/*.go`` is a pattern; a literal exists() on it is always false. Every wildcard
    Covers line in a repo that uses them was reported as naming code that no longer exists."""
    from archagent.config import load_config
    from archagent.drift import find_drift
    root = _repo_with_go(tmp_path)
    (root / "architecture/subsystems/svc.md").write_text("# svc\n\n**Covers:** `svc/*.go`\n")
    assert find_drift(load_config(root)).dangling == []


def test_a_file_in_an_unanalysed_language_is_not_reported_as_missing(tmp_path):
    """archagent analyses Python and TS. Citing `main.go` in a Go repo is accurate, and saying it 'no
    longer exists' is a confident false claim about code sitting in the tree."""
    from archagent.config import load_config
    from archagent.drift import find_drift
    root = _repo_with_go(tmp_path)
    (root / "architecture/subsystems/svc.md").write_text(
        "# svc\n\n**Covers:** `src/app.py`\n\nThe entry point is `svc/main.go` and state is `store.go`.\n")
    assert find_drift(load_config(root)).dangling == []


def test_a_genuinely_missing_reference_is_still_reported(tmp_path):
    """The fixes must not turn the check off."""
    from archagent.config import load_config
    from archagent.drift import find_drift
    root = _repo_with_go(tmp_path)
    (root / "architecture/subsystems/svc.md").write_text(
        "# svc\n\n**Covers:** `src/app.py`\n\nSee `svc/deleted.go` and `nope/*.go`.\n")
    dangling = {ref for _, ref in find_drift(load_config(root)).dangling}
    assert "svc/deleted.go" in dangling and "nope/*.go" in dangling


def test_a_wrapped_config_declaration_is_read_whole(tmp_path):
    """A manifest of a dozen keys gets wrapped by whoever writes it. Reading only the first line honours
    half the declaration and reports the rest as undeclared — a confident wrong finding against a document
    that does declare them. Found on signalfx/obstudio; the same shape as the rubric's line-scoped fields."""
    from archagent.configscan import declared_config_keys
    doc = ("# Deployment\n\n"
           "**Config:** `ALPHA`, `BETA`,\n"
           "`GAMMA`, `DELTA`,\n"
           "`EPSILON`\n\n"
           "Some prose that is not config.\n\n"
           "**Services:** web\n")
    keys = declared_config_keys(tmp_path, doc)
    assert keys == {"ALPHA", "BETA", "GAMMA", "DELTA", "EPSILON"}


def test_a_wrapped_config_declaration_stops_at_the_blank_line(tmp_path):
    from archagent.configscan import declared_config_keys
    doc = "**Config:** `ALPHA`\n\nNOT_A_KEY prose here.\n"
    assert declared_config_keys(tmp_path, doc) == {"ALPHA"}


def test_no_history_does_not_claim_a_family_it_still_reported(tmp_path):
    """The coverage report exists so "no findings" is never read as "clean". It must not do the reverse
    either: a --no-history run reports enum escapes (a pure code scan) while calling family F skipped,
    so the output contradicted its own findings list."""
    import json
    import subprocess
    import sys
    from pathlib import Path
    src = tmp_path / "src/pkg"
    src.mkdir(parents=True)
    (src / "e.py").write_text('from enum import Enum\n\n\nclass Status(Enum):\n'
                              '    ACTIVE = "active"\n    PAUSED = "paused"\n    DONE = "done"\n')
    for n in "abcd":
        (src / f"{n}.py").write_text('def f(s):\n    if s == "active": return 1\n'
                                     '    if s == "paused": return 2\n    if s == "done": return 3\n')
    (tmp_path / "archagent.toml").write_text(
        '[project]\nlanguages = ["python"]\n\n[python]\nsource_paths = ["src"]\n')
    arch = tmp_path / "architecture/subsystems"
    arch.mkdir(parents=True)
    for name, body in (("constitution.md", "# C\n"), ("index.md", "# I\n"), ("invariants.md", "# Inv\n")):
        (tmp_path / "architecture" / name).write_text(body)
    (arch / "a.md").write_text("# A\n\n**Covers:** `src/**/*.py`\n**Tier:** domain\n")
    exe = Path(sys.executable).with_name("archagent")
    out = subprocess.run([str(exe), "evaluate", "--project", str(tmp_path), "--no-history", "--json"],
                         capture_output=True, text=True)
    data = json.loads(out.stdout)
    signs = {f["sign"] for f in data["findings"]}
    assert "enum-value-escape" in signs, "the pure code scan must run without git"
    for fam, _reason in ((i["family"], i["reason"]) for i in data.get("inactive", [])):
        assert fam != "B/E/F — git history", "family F was reported inactive while F produced a finding"
