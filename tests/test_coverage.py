"""What an extractor could not see (issue #46).

The failure this guards recurred from 0.3.0 to 1.0.0: a condition rendering as a plausible clean result.
A wrong source path made every rule scope to nothing and `check` reported that all invariants held; a
generated glob ast-grep silently ignored made a rule match 0 of 154 sites and report PASS; a timed-out
`git log` made every history check go quiet.
"""

import tempfile
from pathlib import Path

import pytest

from archagent.config import Config, PythonConfig, TSConfig
from archagent.coverage import Coverage, Counter
from archagent.drift import _source_files, import_coverage
from archagent.generate import generate
from archagent.invariants import Invariant


# --- the record refuses to be quietly clean ------------------------------------------------

def test_nothing_examined_is_not_sound():
    """The property the whole module exists for. "I resolved all zero of them" is the sentence being
    refused — and the first prototype of the import counter emitted exactly that over an empty file set,
    on its first run, committing the error it was written to detect."""
    c = Coverage("relative imports", seen=0, resolved=0)
    assert c.examined_nothing
    assert not c.sound
    assert c.ratio == 0.0, "never 1.0, which would read as perfect"


def test_nothing_examined_can_be_declared_normal_but_must_be_declared():
    """A repository with no relative imports is fine; one where the scanner could not run is not. The
    difference is a decision the extractor's author makes, not a default."""
    assert Coverage("relative imports", seen=0, resolved=0, empty_is_normal=True).sound
    assert not Coverage("relative imports", seen=0, resolved=0).sound


def test_the_three_states_read_differently_in_words_alone():
    """A caveat that depends on colour loses to a coloured number, so the words have to carry it."""
    nothing = Coverage("globs", seen=0, resolved=0).describe()
    clean = Coverage("globs", seen=5, resolved=5).describe()
    gaps = Coverage("globs", seen=5, resolved=3, examples=("a.yml",)).describe()
    assert len({nothing, clean, gaps}) == 3
    assert "examined no" in nothing and "not the same as" in nothing
    assert "all 5" in clean
    assert "2 of 5" in gaps and "40%" in gaps and "a.yml" in gaps


def test_a_counter_carries_a_bounded_number_of_examples():
    c = Counter("things")
    for i in range(50):
        c.site(False, f"f{i}.py:1")
    cov = c.finish()
    assert cov.seen == 50 and cov.resolved == 0
    assert 0 < len(cov.examples) <= 5, "enough to start looking, few enough to print"


# --- the import graph counter --------------------------------------------------------------

def _repo(tmp, files, source_paths=("src",), root_package="pkg"):
    for rel, text in files.items():
        p = tmp / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)
    return Config(project_root=tmp, languages=["python"],
                  python=PythonConfig(root_package=root_package, source_paths=list(source_paths)),
                  ts=TSConfig(source_paths=list(source_paths)))


def test_a_resolvable_repository_reports_sound(tmp_path):
    cfg = _repo(tmp_path, {"src/pkg/__init__.py": "", "src/pkg/a.py": "from . import b\n",
                           "src/pkg/b.py": "x = 1\n"})
    cov = import_coverage(tmp_path, cfg, _source_files(cfg))
    assert cov.sound and cov.seen == 1


def test_an_unresolvable_relative_import_is_counted_and_located(tmp_path):
    """A relative import cannot legitimately point outside its own package — unlike `import numpy`,
    which resolves to nothing internal for good reason. That exactness is what makes the counter safe to
    report loudly: it has no false-positive mode."""
    cfg = _repo(tmp_path, {"src/pkg/__init__.py": "", "src/pkg/a.py": "from .gone import thing\n"})
    cov = import_coverage(tmp_path, cfg, _source_files(cfg))
    assert not cov.sound
    assert cov.seen == 1 and cov.resolved == 0
    assert cov.examples == ("src/pkg/a.py:1",), "the offending site must be nameable"


def test_the_counter_counts_statements_not_module_candidates(tmp_path):
    """`from .config import Config` emits both `pkg.config` and `pkg.config.Config`, and only the first
    is a module. Counting candidates would report a false gap on the most ordinary import in Python."""
    cfg = _repo(tmp_path, {"src/pkg/__init__.py": "", "src/pkg/config.py": "class Config: pass\n",
                           "src/pkg/a.py": "from .config import Config\n"})
    cov = import_coverage(tmp_path, cfg, _source_files(cfg))
    assert cov.seen == 1 and cov.sound


def test_absolute_imports_of_third_party_packages_are_not_counted(tmp_path):
    """`import numpy` resolving to nothing internal is correct, not a gap. Only relative imports carry
    the guarantee this counter depends on."""
    cfg = _repo(tmp_path, {"src/pkg/__init__.py": "", "src/pkg/a.py": "import numpy\nimport os\n"})
    cov = import_coverage(tmp_path, cfg, _source_files(cfg))
    assert cov.seen == 0 and cov.sound, "no relative imports is a legitimate answer here"


def test_the_counter_and_the_extractor_share_one_resolution_rule():
    """A counter measuring a different rule than the extractor uses would report a gap nobody can act
    on, or hide one. Both call `_relative_targets`."""
    import inspect
    from archagent import drift
    assert "_relative_targets" in inspect.getsource(drift.import_coverage)
    assert "_relative_targets" in inspect.getsource(drift._imports_of)


def test_the_counter_would_have_named_the_package_initialiser_defect(tmp_path):
    """The measurement the design rests on, reproduced in miniature: with the pre-#41 rule the httpx
    shape reported 18 of 88 unresolved. Here the same shape is checked against the current rule, so this
    test fails if that regression ever returns."""
    cfg = _repo(tmp_path, {"src/pkg/__init__.py": "from ._api import *\nfrom . import _auth\n",
                           "src/pkg/_api.py": "x = 1\n", "src/pkg/_auth.py": "x = 1\n"})
    cov = import_coverage(tmp_path, cfg, _source_files(cfg))
    assert cov.seen == 2 and cov.sound, cov.describe()


# --- the generated-glob precondition -------------------------------------------------------

def _inv(id, rule):
    return Invariant(id=id, type="STRUCTURAL", tier="structural", applies_to="python",
                     rule=rule, severity="error", why="x", status="active")


def test_a_scope_matching_no_files_is_skipped_not_generated(tmp_path):
    """The highest-severity case, because it currently reports a *passing* check over nothing. On dspy a
    scope compiled to `./dspy/**`, ast-grep silently ignored it, the rule matched 0 of 154 `print(` sites
    and `check` said the invariant held (#44)."""
    cfg = _repo(tmp_path, {"pkg/a.py": "print('x')\n"}, source_paths=(".",))
    res = generate([_inv("STR-1", "forbid-pattern print($$$) in nosuchpkg")], cfg)
    assert res.astgrep_ids == []
    assert len(res.skipped) == 1
    _, why = res.skipped[0]
    assert "matches no files" in why and "passing vacuously" in why


def test_a_scope_that_matches_still_generates(tmp_path):
    """The precondition must not make scoped rules unusable — the failure mode of an over-strict guard."""
    cfg = _repo(tmp_path, {"pkg/a.py": "print('x')\n"}, source_paths=(".",))
    res = generate([_inv("STR-1", "forbid-pattern print($$$) in pkg")], cfg)
    assert res.astgrep_ids == ["STR-1"] and not res.skipped


def test_an_unscoped_rule_is_unaffected(tmp_path):
    cfg = _repo(tmp_path, {"pkg/a.py": "print('x')\n"}, source_paths=(".",))
    res = generate([_inv("STR-1", "forbid-pattern print($$$)")], cfg)
    assert res.astgrep_ids == ["STR-1"]


# --- the remaining extractors (step 6) ------------------------------------------------------

def test_a_route_whose_path_is_computed_is_counted(tmp_path):
    """`@app.get(PREFIX + "/x")` is a route the scanner knows is there and cannot name."""
    from archagent.webapi import route_coverage
    (tmp_path / "api.py").write_text(
        'PREFIX = "/v1"\n'
        '@app.get("/health")\n'
        'def health(): ...\n'
        '@app.get(PREFIX + "/users")\n'
        'def users(): ...\n')
    cov = route_coverage(tmp_path, {"api.py"})
    assert cov.seen == 2 and cov.resolved == 1
    assert cov.examples == ("api.py:4",)


def test_a_verb_named_decorator_that_is_not_a_route_is_not_counted(tmp_path):
    """The line between a counter worth reporting loudly and one worth ignoring. `@cache.get("key")`
    has a verb-shaped name and a literal that is not a path — counting it would make this a guess about
    whether code is a route rather than a fact about what could be read."""
    from archagent.webapi import route_coverage
    (tmp_path / "svc.py").write_text('@cache.get("session-key")\ndef f(): ...\n')
    cov = route_coverage(tmp_path, {"svc.py"})
    assert cov.seen == 0 and cov.sound


def test_a_table_name_that_is_computed_is_counted(tmp_path):
    """`__tablename__ = _prefix + "orders"` is unambiguously a table declaration whose name cannot be
    read. Exact, not a guess about whether the code defines a table."""
    from archagent.datamap import table_coverage
    (tmp_path / "m.py").write_text(
        'class A:\n    __tablename__ = "orders"\n'
        'class B:\n    __tablename__ = PREFIX + "items"\n')
    cov = table_coverage(tmp_path, {"m.py"})
    assert cov.seen == 2 and cov.resolved == 1
    assert not cov.sound


def test_a_repository_with_no_tables_or_routes_is_sound(tmp_path):
    """`empty_is_normal` where it genuinely is: most files declare no tables and serve no routes, and a
    library serves none at all. The counter must not cry wolf on every ordinary repository."""
    from archagent.datamap import table_coverage
    from archagent.webapi import route_coverage
    (tmp_path / "a.py").write_text("x = 1\n")
    assert table_coverage(tmp_path, {"a.py"}).sound
    assert route_coverage(tmp_path, {"a.py"}).sound


# --- the evaluate report (step 7) -----------------------------------------------------------

def _evaluable(tmp, extra=""):
    (tmp / "architecture" / "subsystems").mkdir(parents=True)
    (tmp / "src" / "pkg").mkdir(parents=True)
    (tmp / "src" / "pkg" / "__init__.py").write_text("")
    (tmp / "src" / "pkg" / "a.py").write_text("x = 1\n" + extra)
    (tmp / "architecture" / "subsystems" / "a.md").write_text("# A\n\n**Covers:** `src/pkg/**`\n")
    return Config(project_root=tmp, languages=["python"],
                  python=PythonConfig(root_package="pkg", source_paths=["src"]),
                  ts=TSConfig(source_paths=["src"]))


def test_a_partial_scan_is_reported_next_to_the_findings(tmp_path):
    """The case an `Inactive` entry cannot express. An inactive family never ran; this family *did* run,
    over a view it could not fully read — so it produces findings and looks like a working result."""
    from archagent.evaluate import evaluate
    cfg = _evaluable(tmp_path, "import os\nv = os.getenv(NAME)\n")
    got = evaluate(cfg, history=False).extraction
    assert any("environment reads" in c.describe() for c in got)


def test_a_complete_scan_is_not_listed(tmp_path):
    """Sound extractors are dropped. The report has to earn its length, and listing everything that went
    right is how the part that went wrong gets skipped."""
    from archagent.evaluate import evaluate
    cfg = _evaluable(tmp_path, "import os\nv = os.getenv('REAL')\n")
    assert evaluate(cfg, history=False).extraction == []


def test_incomplete_extraction_is_not_confusable_with_an_inactive_family(tmp_path):
    """Two different statements about the same run: 'this never ran' and 'this ran over a partial view'.
    Rendering them alike would collapse the distinction the whole coverage report exists to draw."""
    import inspect
    from archagent import cli
    src = inspect.getsource(cli.evaluate_cmd if hasattr(cli, "evaluate_cmd") else cli.evaluate)
    assert "Incomplete extraction" in src and "Inactive signals" in src
    assert "a floor rather than a census" in src


def test_a_configured_language_that_yields_no_edges_at_all_is_reported(tmp_path):
    """The wardrowbe failure, generalised (#49). `tsconfig` path aliases resolved to nothing, so the
    frontend graph held 3 edges across 119 TypeScript files where it should hold 356 — and the report
    said nothing, because "no findings" and "nothing to find" are the same output.

    A per-language check catches that class whole, without anyone having to anticipate the idiom that
    caused it. Here the imports are unresolvable because the target files do not exist."""
    from archagent.evaluate import _language_coverage
    from archagent.drift import _source_files
    files = {f"src/m{i}.ts": f"import {{ x }} from '@/nowhere/{i}';\n" for i in range(12)}
    cfg = _repo(tmp_path, files, source_paths=("src",))
    cfg = Config(project_root=tmp_path, languages=["ts"],
                 python=PythonConfig(root_package="pkg", source_paths=["src"]),
                 ts=TSConfig(source_paths=["src"]))
    got = _language_coverage(cfg, _source_files(cfg))
    assert len(got) == 1 and not got[0].sound
    assert "ts files" in got[0].describe() and "12" in got[0].describe()


def test_a_language_that_parses_is_silent(tmp_path):
    """The check must not fire on every repository, or it stops meaning anything."""
    from archagent.evaluate import _language_coverage
    from archagent.drift import _source_files
    files = {f"src/m{i}.ts": "import { x } from './shared';\n" for i in range(12)}
    files["src/shared.ts"] = "export const x = 1;\n"
    _repo(tmp_path, files, source_paths=("src",))
    cfg = Config(project_root=tmp_path, languages=["ts"],
                 python=PythonConfig(root_package="pkg", source_paths=["src"]),
                 ts=TSConfig(source_paths=["src"]))
    assert _language_coverage(cfg, _source_files(cfg)) == []


def test_a_handful_of_files_is_not_enough_to_conclude_anything(tmp_path):
    """A three-file package with no internal imports is ordinary, not a parser failure."""
    from archagent.evaluate import _language_coverage
    from archagent.drift import _source_files
    files = {f"src/m{i}.ts": "export const x = 1;\n" for i in range(3)}
    _repo(tmp_path, files, source_paths=("src",))
    cfg = Config(project_root=tmp_path, languages=["ts"],
                 python=PythonConfig(root_package="pkg", source_paths=["src"]),
                 ts=TSConfig(source_paths=["src"]))
    assert _language_coverage(cfg, _source_files(cfg)) == []
