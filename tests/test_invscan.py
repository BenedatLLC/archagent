"""invscan — deterministic candidate scanner for stated invariants (issue #3, stage 2)."""

from archagent.config import Config, PythonConfig, TSConfig
from archagent.invscan import scan_invariants


def _cfg(tmp):
    return Config(
        project_root=tmp, languages=["python"],
        python=PythonConfig(root_package="pkg", source_paths=["src"]),
        ts=TSConfig(source_paths=["src"]),
    )


def _src(cfg, rel, text):
    p = cfg.project_root / "src" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _doc(cfg, rel, text):
    p = cfg.project_root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _by_source(cands):
    return {c.source.split("/")[-1]: c for c in cands}


def test_code_markers_and_assert_messages(tmp_path):
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/a.py",
         "def f(xs):\n"
         "    # INVARIANT: the query set is always sorted\n"
         '    assert xs == sorted(xs), "query set must be sorted"\n'
         "    return xs\n")
    cands = scan_invariants(cfg)
    texts = [c.text for c in cands]
    assert any("INVARIANT: the query set is always sorted" in t for t in texts)
    assert any("query set must be sorted" in t for t in texts)   # from the assert message
    assert all(c.kind == "marker" and c.confidence == "high" for c in cands)


def test_doc_markers_and_modal(tmp_path):
    cfg = _cfg(tmp_path)
    _doc(cfg, "designs/state.md",
         "# State machine\n"
         "Invariant: a new session always starts in the initial state.\n"
         "The summary must never be empty.\n"
         "This paragraph is ordinary prose with no rule.\n")
    cands = scan_invariants(cfg)
    kinds = {c.kind for c in cands}
    assert "marker" in kinds        # "Invariant:" label
    assert "modal" in kinds         # "must never" / "always"
    assert not any("ordinary prose with no rule" in c.text for c in cands)


def test_boundary_and_structural_guesses(tmp_path):
    cfg = _cfg(tmp_path)
    _doc(cfg, "designs/layers.md",
         "The domain layer must not import the UI.\n"
         "Only the config module may read os.environ.\n")
    guesses = {c.text[:20]: c.guess for c in scan_invariants(cfg)}
    # a dependency rule -> BOUNDARY; an env-access shape -> STRUCTURAL
    assert any(g == "BOUNDARY" for g in guesses.values())
    assert any(g == "STRUCTURAL" for g in guesses.values())


def test_scans_root_index_files(tmp_path):
    cfg = _cfg(tmp_path)
    _doc(cfg, "CLAUDE.md", "Notes.\nThe workflow must never import chat.\n")
    assert any(c.source.startswith("CLAUDE.md") for c in scan_invariants(cfg))


def test_skips_architecture_dir(tmp_path):
    cfg = _cfg(tmp_path)
    _doc(cfg, "architecture/subsystems/x.md", "The store must always be validated.\n")
    assert not any("architecture/" in c.source for c in scan_invariants(cfg))


def test_clean_repo_no_candidates(tmp_path):
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/a.py", "def add(a, b):\n    return a + b\n")
    _doc(cfg, "README.md", "# My project\n\nA calculator.\n")
    assert scan_invariants(cfg) == []
