"""Generating checker configs from invariants (single source -> generate)."""

from archagent.config import Config, PythonConfig, TSConfig
from archagent.generate import generate
from archagent.invariants import Invariant


def _cfg(tmp, langs=("python",)):
    return Config(
        project_root=tmp,
        languages=list(langs),
        python=PythonConfig(root_package="app", source_paths=["src"]),
        ts=TSConfig(source_paths=["src"]),
    )


def _inv(**kw):
    base = dict(id="X", type="BOUNDARY", tier="structural", applies_to="python",
                rule="", severity="error", why="", status="active")
    base.update(kw)
    return Invariant(**base)


def test_boundary_python_importlinter(tmp_path):
    cfg = _cfg(tmp_path)
    res = generate([_inv(id="BND-1", rule="forbid app.domain -> app.web, rich")], cfg)
    assert res.importlinter_ids == ["BND-1"]
    text = (cfg.generated_dir / ".importlinter").read_text()
    assert "include_external_packages = True" in text   # so external deps can be forbidden
    assert "allow_indirect_imports = True" in text       # BOUNDARY = direct import only
    assert "name = BND-1" in text
    for token in ("app.domain", "app.web", "rich"):
        assert token in text


def test_tier_prose_is_not_generated(tmp_path):
    # issue #2: a real forbid-pattern with Tier `prose` is documentation, not enforced — skip it uniformly
    cfg = _cfg(tmp_path)
    res = generate([_inv(id="STR-P", type="STRUCTURAL", tier="prose",
                         rule="forbid-pattern print($$$)")], cfg)
    assert res.astgrep_ids == []
    assert any(inv_id == "STR-P" for inv_id, _ in res.skipped)


def test_structural_astgrep_scoped_in(tmp_path):
    cfg = _cfg(tmp_path)
    res = generate([_inv(id="STR-2", type="STRUCTURAL",
                         rule="forbid-pattern print($$$) in app.workflow")], cfg)
    assert res.astgrep_ids == ["STR-2"]
    y = (cfg.generated_dir / "sgrules" / "STR-2.yml").read_text()
    assert "pattern: 'print($$$)'" in y
    assert "files:" in y and "src/app/workflow.py" in y   # dotted module -> path glob


def test_structural_astgrep_scoped_outside(tmp_path):
    cfg = _cfg(tmp_path)
    generate([_inv(id="D", type="STRUCTURAL", rule="forbid-pattern foo() outside app.config")], cfg)
    y = (cfg.generated_dir / "sgrules" / "D.yml").read_text()
    assert "ignores:" in y and "src/app/config.py" in y


def test_boundary_ts_dependency_cruiser(tmp_path):
    cfg = _cfg(tmp_path, langs=("ts",))
    res = generate([_inv(id="B10", applies_to="ts", rule="forbid src/domain -> src/ui")], cfg)
    assert res.depcruiser_ids == ["B10"]
    js = (cfg.generated_dir / ".dependency-cruiser.cjs").read_text()
    assert '"B10"' in js and "src/domain" in js and "src/ui" in js


def test_property_scaffolds_stub(tmp_path):
    cfg = _cfg(tmp_path)
    res = generate([_inv(id="P1", type="INVARIANT", tier="pbt",
                         rule="property tests/p.py::test_p")], cfg)
    assert res.pbt_ids == ["P1"]
    stub = (tmp_path / "tests" / "p.py").read_text()
    assert "def test_p(" in stub and "NotImplementedError" in stub


def test_property_stateful_scaffolds_state_machine(tmp_path):
    cfg = _cfg(tmp_path)
    res = generate([_inv(id="ST1", type="DATAFLOW", tier="pbt",
                         rule="property stateful tests/sp.py::TestWorkflow")], cfg)
    assert res.pbt_ids == ["ST1"]
    stub = (tmp_path / "tests" / "sp.py").read_text()
    assert "class WorkflowMachine(RuleBasedStateMachine):" in stub
    assert "@rule()" in stub and "@invariant()" in stub
    assert "TestWorkflow = WorkflowMachine.TestCase" in stub


def test_property_ts_scaffolds_fastcheck(tmp_path):
    cfg = _cfg(tmp_path, langs=("ts",))
    res = generate([_inv(id="TP1", type="INVARIANT", tier="pbt", applies_to="ts",
                         rule="property tests/props.test.ts::sorted")], cfg)
    assert res.pbt_ids == ["TP1"]
    stub = (tmp_path / "tests" / "props.test.ts").read_text()
    assert "fast-check" in stub
    assert "fc.assert(" in stub and "fc.property(" in stub
    assert 'test("sorted"' in stub


def test_property_ts_stateful_scaffolds_commands(tmp_path):
    cfg = _cfg(tmp_path, langs=("ts",))
    generate([_inv(id="TP2", type="INVARIANT", tier="pbt", applies_to="ts",
                   rule="property stateful tests/state.test.ts::machine")], cfg)
    stub = (tmp_path / "tests" / "state.test.ts").read_text()
    assert "fc.commands(" in stub and 'test("machine"' in stub


def test_unsupported_is_skipped_not_guessed(tmp_path):
    cfg = _cfg(tmp_path)
    res = generate([_inv(id="Q", type="PURPOSE", tier="prose", rule="just prose")], cfg)
    assert res.skipped and res.skipped[0][0] == "Q"
    assert res.importlinter_ids == [] and res.astgrep_ids == []


# --- rules nothing checked must not read as rules that passed ------------------------------------

def _repo_with_invariants(tmp_path, rows: str):
    arch = tmp_path / "architecture"
    arch.mkdir(parents=True)
    (arch / "invariants.md").write_text(
        "# Invariants\n\n| ID | Type | Tier | Applies-to | Rule | Severity | Why | Status |\n"
        "|----|------|------|-----------|------|----------|-----|--------|\n" + rows)
    (tmp_path / "archagent.toml").write_text(
        '[project]\nlanguages = ["python"]\n\n[python]\nsource_paths = ["src"]\n')
    (tmp_path / "src").mkdir()
    (tmp_path / "src/a.py").write_text("x = 1\n")
    return tmp_path


def test_prose_rows_are_reported_as_skipped_not_dropped(tmp_path):
    """obstudio's artifact had eight prose-tier rules, two of them demonstrably false, and `check`
    printed an empty table and "All invariants hold." A rule the tool never looked at must not be
    indistinguishable from one that passed (ADR 0002)."""
    from archagent.config import load_config
    from archagent.generate import generate
    from archagent.invariants import parse_invariants
    root = _repo_with_invariants(
        tmp_path,
        "| GO-001 | BOUNDARY | prose | go | `forbid a -> b` | error | x | active |\n"
        "| GO-002 | BOUNDARY | prose | go | `forbid c -> d` | error | y | active |\n")
    cfg = load_config(root)
    res = generate(parse_invariants(cfg.invariants_path), cfg)
    skipped = {i for i, _ in res.skipped}
    assert skipped == {"GO-001", "GO-002"}
    assert all("prose" in why for _, why in res.skipped)


def test_an_all_prose_artifact_enforces_nothing(tmp_path):
    """The count that matters: zero enforceable rules from a non-empty table."""
    from archagent.config import load_config
    from archagent.generate import generate
    from archagent.invariants import parse_invariants
    root = _repo_with_invariants(
        tmp_path, "| GO-001 | BOUNDARY | prose | go | `forbid a -> b` | error | x | active |\n")
    cfg = load_config(root)
    res = generate(parse_invariants(cfg.invariants_path), cfg)
    assert not (res.importlinter_ids or res.depcruiser_ids or res.astgrep_ids or res.pbt_ids)
    assert len(res.skipped) == 1


def test_a_prose_row_asserted_active_without_evidence_is_detectable(tmp_path):
    """`Status: active` on a prose row claims the rule is in force while nothing can confirm it. Twice a
    rule in that state was simply false — obstudio's SKILL-002 and wardrowbe's SVC-001 — and in both the
    `Why` held rationale with no citation. That is the separator between a verified assertion and an
    unverified one, and it is mechanically checkable."""
    import re
    from archagent.config import load_config
    from archagent.invariants import parse_invariants
    cites = re.compile(r"[\w/.-]+\.[A-Za-z]{1,5}(?::\d+)?")
    root = _repo_with_invariants(
        tmp_path,
        "| A-1 | STRUCTURAL | prose | python | one place to rate-limit | error | keeps copies from diverging | active |\n"
        "| A-2 | STRUCTURAL | prose | python | the same rule | error | verified at `app/svc.py:31` | active |\n"
        "| A-3 | STRUCTURAL | prose | python | a third rule | error | no evidence, but honest | proposed |\n")
    invs = parse_invariants(load_config(root).invariants_path)
    flagged = [i.id for i in invs
               if i.tier == "prose" and i.status == "active" and not cites.search(i.why or "")]
    assert flagged == ["A-1"], "only the unevidenced *active* row should flag"


# --- a scoped rule must actually scope to something (found on dspy) ----------------------------------

def test_a_module_scope_under_a_root_source_path_has_no_dot_slash():
    """**ast-grep silently ignores any glob with a `./` prefix.** With `source_paths = ["."]` — a package
    at the repository root — the generated scope was `./dspy/**`, which matched 0 of 154 `print(` sites in
    dspy and reported PASS.

    A scoped structural rule that enforces nothing while reporting a pass is precisely the failure this
    tool exists to prevent, arriving through its own code generator."""
    from archagent.config import Config, PythonConfig, TSConfig
    from archagent.generate import _scope_to_globs
    from archagent.invariants import Invariant
    from pathlib import Path
    cfg = Config(project_root=Path("/tmp"), languages=["python"],
                 python=PythonConfig(root_package="dspy", source_paths=["."]), ts=TSConfig())
    inv = Invariant(id="X", type="STRUCTURAL", tier="structural", applies_to="python",
                    rule="forbid-pattern print($$$) in dspy", severity="warn", why="", status="active")
    globs = _scope_to_globs("dspy", inv, cfg)
    assert not any(g.startswith("./") for g in globs), globs
    assert "dspy/**" in globs


def test_a_module_scope_under_a_nested_source_path_is_unchanged():
    """The common layout must keep working: `src` + `archagent.cli` -> `src/archagent/cli.py`."""
    from archagent.config import Config, PythonConfig, TSConfig
    from archagent.generate import _scope_to_globs
    from archagent.invariants import Invariant
    from pathlib import Path
    cfg = Config(project_root=Path("/tmp"), languages=["python"],
                 python=PythonConfig(root_package="archagent", source_paths=["src"]), ts=TSConfig())
    inv = Invariant(id="X", type="STRUCTURAL", tier="structural", applies_to="python",
                    rule="forbid-pattern print($$$) in archagent.cli", severity="warn", why="",
                    status="active")
    assert "src/archagent/cli.py" in _scope_to_globs("archagent.cli", inv, cfg)
