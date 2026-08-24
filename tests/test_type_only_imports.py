"""`if TYPE_CHECKING:` imports are not runtime dependencies (#37).

From user test round 2. The evaluator reported a high-confidence five-node tangle whose back-edges were
type-only; on httpx, `_exceptions.py`'s only internal import is
`if typing.TYPE_CHECKING: from ._models import Request, Response`, and the graph reported an
`_exceptions ↔ _models` cycle that does not exist when the program runs.

The idiom is what makes this systematic rather than incidental: a type-only back-edge is *how* a Python
project breaks a real import cycle, so the graph was most wrong exactly where the code was most careful.
"""

from archagent.config import Config, PythonConfig, TSConfig
from archagent.drift import _import_graph, _imports_of, _source_files
from archagent.evaluate import evaluate


def _cfg(tmp):
    (tmp / "architecture" / "subsystems").mkdir(parents=True)
    return Config(project_root=tmp, languages=["python"],
                  python=PythonConfig(root_package="pkg", source_paths=["src"]),
                  ts=TSConfig(source_paths=["src"]))


def _src(cfg, rel, text):
    p = cfg.project_root / "src" / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)


def _sub(cfg, name, text):
    (cfg.project_root / "architecture" / "subsystems" / f"{name}.md").write_text(text)


def _graphs(cfg):
    sf = _source_files(cfg)
    root = cfg.project_root
    return (_import_graph(root, cfg, sf), _import_graph(root, cfg, sf, type_only=True))


def test_a_type_only_back_edge_does_not_create_a_cycle(tmp_path):
    """The httpx shape, reduced: `b` imports `a` for real, `a` imports `b` only for annotations."""
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/a.py", "import typing\n"
                          "if typing.TYPE_CHECKING:\n"
                          "    from pkg import b\n"
                          "x = 1\n")
    _src(cfg, "pkg/b.py", "from pkg import a\n")
    _sub(cfg, "a", "# A\n\n**Covers:** `src/pkg/a.py`\n")
    _sub(cfg, "b", "# B\n\n**Covers:** `src/pkg/b.py`\n")

    runtime, type_only = _graphs(cfg)
    assert runtime["src/pkg/a.py"] == set(), "the type-only import is not a runtime edge"
    assert type_only["src/pkg/a.py"] == {"src/pkg/b.py"}, "but it is kept, not discarded"
    assert "cycle-subsystem" not in {f.sign for f in evaluate(cfg).findings}


def test_the_bare_name_form_is_recognised_too(tmp_path):
    """`from typing import TYPE_CHECKING` then `if TYPE_CHECKING:` — as common as the dotted form."""
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/a.py", "from typing import TYPE_CHECKING\n"
                          "if TYPE_CHECKING:\n"
                          "    from pkg import b\n")
    _src(cfg, "pkg/b.py", "y = 1\n")
    runtime, type_only = _graphs(cfg)
    assert runtime["src/pkg/a.py"] == set()
    assert type_only["src/pkg/a.py"] == {"src/pkg/b.py"}


def test_an_else_branch_stays_a_runtime_import(tmp_path):
    """`if TYPE_CHECKING: ... else: ...` puts the *runtime* import in the else. Treating the whole
    statement as type-only would drop a real edge to fix a false one."""
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/a.py", "from typing import TYPE_CHECKING\n"
                          "if TYPE_CHECKING:\n"
                          "    from pkg import c\n"
                          "else:\n"
                          "    from pkg import b\n")
    _src(cfg, "pkg/b.py", "y = 1\n")
    _src(cfg, "pkg/c.py", "z = 1\n")
    runtime, type_only = _graphs(cfg)
    assert runtime["src/pkg/a.py"] == {"src/pkg/b.py"}
    assert type_only["src/pkg/a.py"] == {"src/pkg/c.py"}


def test_a_negated_guard_is_treated_as_runtime(tmp_path):
    """`if not TYPE_CHECKING:` makes its body runtime code. Not matching it keeps the real edge, which
    is the safe direction: a missed exclusion costs a false positive, a wrong one drops a dependency."""
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/a.py", "from typing import TYPE_CHECKING\n"
                          "if not TYPE_CHECKING:\n"
                          "    from pkg import b\n")
    _src(cfg, "pkg/b.py", "y = 1\n")
    runtime, _ = _graphs(cfg)
    assert runtime["src/pkg/a.py"] == {"src/pkg/b.py"}


def test_a_declared_edge_backed_only_by_a_type_only_import_is_not_stale(tmp_path):
    """The fix must not trade one false positive for another. A `TYPE_CHECKING` import is real
    design-time coupling, so an artifact that declares it has not drifted — telling the author their
    accurate declaration is stale is the failure #41 describes from the other side."""
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/a.py", "from typing import TYPE_CHECKING\n"
                          "if TYPE_CHECKING:\n"
                          "    from pkg import b\n")
    _src(cfg, "pkg/b.py", "y = 1\n")
    _sub(cfg, "a", "# A\n\n**Covers:** `src/pkg/a.py`\n**Connects:** b via import\n")
    _sub(cfg, "b", "# B\n\n**Covers:** `src/pkg/b.py`\n")
    from archagent.drift import find_drift
    assert ("a", "b") not in find_drift(cfg).stale_deps


def test_a_type_only_import_never_demands_a_declaration(tmp_path):
    """The other direction. A type-only edge creates no runtime dependency, so requiring it to be
    documented would push authors to describe couplings the running system does not have."""
    cfg = _cfg(tmp_path)
    _src(cfg, "pkg/a.py", "from typing import TYPE_CHECKING\n"
                          "if TYPE_CHECKING:\n"
                          "    from pkg import b\n")
    _src(cfg, "pkg/b.py", "y = 1\n")
    _sub(cfg, "a", "# A\n\n**Covers:** `src/pkg/a.py`\n**Connects:** none\n")
    _sub(cfg, "b", "# B\n\n**Covers:** `src/pkg/b.py`\n")
    from archagent.drift import find_drift
    assert ("a", "b") not in find_drift(cfg).undeclared_deps


def test_imports_of_partitions_rather_than_filters(tmp_path):
    """Runtime and type-only together must equal everything imported — a filter that dropped edges from
    both sides would go quiet, which is this project's recurring failure shape."""
    f = tmp_path / "m.py"
    f.write_text("from typing import TYPE_CHECKING\n"
                 "import os\n"
                 "if TYPE_CHECKING:\n"
                 "    import json\n")
    runtime = set(_imports_of(tmp_path, "m.py", "m"))
    type_only = set(_imports_of(tmp_path, "m.py", "m", type_only=True))
    assert "os" in runtime and "json" not in runtime
    assert "json" in type_only and "os" not in type_only
    assert "typing" in runtime | type_only
