"""End-to-end: run the checkers on the bundled Python example.

Exercises the real import-linter + ast-grep path (both are archagent deps, so this runs
without any extra tools). The TS example needs Node, so it isn't covered here.
"""

from pathlib import Path

from archagent.check import run_checks
from archagent.config import load_config
from archagent.generate import generate
from archagent.invariants import parse_invariants

SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "sample_py"


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
