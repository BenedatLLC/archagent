"""End-to-end: run the checkers on the bundled Python example.

Exercises the real import-linter + ast-grep path (both are archagent deps, so this runs
without any extra tools). The TS example needs Node, so it isn't covered here.
"""

from pathlib import Path

from archagent.check import run_checks
from archagent.config import Config, PythonConfig, TSConfig, load_config
from archagent.generate import generate
from archagent.invariants import Invariant, parse_invariants

SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample_py"


def test_run_checks_skip_pbt_reports_skip(tmp_path):
    # --skip-pbt must report property tests as SKIP (not run, not silently dropped)
    cfg = Config(project_root=tmp_path, languages=["python"],
                 python=PythonConfig(root_package="pkg", source_paths=["src"]), ts=TSConfig())
    inv = Invariant(id="QSET-1", type="DATAFLOW", tier="pbt", applies_to="python",
                    rule="property tests/test_props.py::test_sorted", severity="error", why="", status="active")
    results = run_checks([inv], cfg, [], [], [], ["QSET-1"], skip_pbt=True)
    assert len(results) == 1
    r = results[0]
    assert r.invariant_id == "QSET-1" and r.checker == "pbt"
    assert r.passed is True and r.skipped_reason and "skip-pbt" in r.skipped_reason


def test_sample_py_boundary_and_structural_violations():
    cfg = load_config(SAMPLE)
    invs = parse_invariants(cfg.invariants_path)
    gen = generate(invs, cfg)
    results = run_checks(
        invs, cfg, gen.importlinter_ids, gen.depcruiser_ids, gen.astgrep_ids, gen.pbt_ids
    )
    by = {r.invariant_id: r for r in results}

    # BND-001: domain imports web -> import-linter FAIL
    assert by["BND-001"].checker == "import-linter"
    assert by["BND-001"].passed is False
    # STR-002: print() in the domain -> ast-grep flags it (a warn-severity violation)
    assert by["STR-002"].checker == "ast-grep"
    assert by["STR-002"].passed is False


# --- a coloured tool must not read as a clean run ---------------------------------------------------

def test_a_broken_contract_is_still_detected_when_the_tool_colourises(monkeypatch):
    """`FORCE_COLOR` in the environment made `check` report every invariant as passing.

    import-linter honours `FORCE_COLOR` even when its output is a pipe, so `BND-001 BROKEN` arrives
    wrapped in SGR escapes, the status regex matches nothing, and the "the tool errored before checking"
    branch returns `passed=True` for every rule — a genuinely broken contract rendering as a clean run.
    The environment variable is set in plenty of developer shells and CI images, and this was found by the
    suite failing on a machine that had it.
    """
    monkeypatch.setenv("FORCE_COLOR", "3")
    monkeypatch.setenv("CLICOLOR_FORCE", "1")
    cfg = load_config(SAMPLE)
    invs = parse_invariants(cfg.invariants_path)
    gen = generate(invs, cfg)
    by = {r.invariant_id: r for r in run_checks(
        invs, cfg, gen.importlinter_ids, gen.depcruiser_ids, gen.astgrep_ids, gen.pbt_ids)}

    assert by["BND-001"].passed is False, "a broken import contract was reported as passing"
    assert by["BND-001"].skipped_reason is None, "a broken contract was reported as skipped"
    assert by["STR-002"].passed is False


def test_unreadable_tool_output_is_reported_as_skipped_not_passed(tmp_path, monkeypatch):
    """The other half of the same rule: output we cannot parse must not mean "no violations".

    ast-grep's JSON decode failure previously fell through to an empty match list, which reported every
    rule as passing. "Nothing was checked" must never render as "everything passed" (ADR 0002).
    """
    import subprocess as sp

    from archagent import check as check_mod

    class _Unparseable:
        stdout, stderr, returncode = "not json at all", "ast-grep: config error", 2

    monkeypatch.setattr(check_mod.subprocess, "run", lambda *a, **k: _Unparseable())
    monkeypatch.setattr(check_mod, "_tool_path", lambda name, required=True: "/bin/true")
    cfg = Config(project_root=tmp_path, languages=["python"],
                 python=PythonConfig(root_package="pkg", source_paths=["src"]), ts=TSConfig())
    inv = Invariant(id="STR-9", type="STRUCTURE", tier="ast-grep", applies_to="python",
                    rule="no print", severity="error", why="", status="active")
    (r,) = check_mod._run_ast_grep(["STR-9"], cfg, {"STR-9": inv})
    assert r.skipped_reason and "config error" in r.skipped_reason
    assert sp  # keep the import meaningful for readers of the monkeypatch above
