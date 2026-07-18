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
