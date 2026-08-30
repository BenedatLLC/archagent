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
